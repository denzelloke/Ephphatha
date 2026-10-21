"""Train a five-flex-sensor classifier and export INT8 TFLite plus ESP32 headers."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import os
from pathlib import Path
import platform

# Set before importing TensorFlow. CPU training is sufficient for 555 parameters.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")

from data import DEFAULT_CONFIG, FEATURES, LABELS, OFFSET, SCALE, load_config, load_dataset, write_json


def build_model(tf, config):
    model = tf.keras.Sequential([
        tf.keras.layers.InputLayer(input_shape=(5,), batch_size=1, name="flex_inputs"),
        tf.keras.layers.Dense(config["hidden_units"], activation="relu",
                              kernel_regularizer=tf.keras.regularizers.l2(config["l2"])),
        tf.keras.layers.Dense(len(LABELS), activation="softmax", name="gesture_probabilities"),
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=config["learning_rate"]),
                  loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return model


def class_weights(y):
    import numpy as np
    counts = np.bincount(y, minlength=len(LABELS))
    if (counts == 0).any():
        raise ValueError("Training split must include all classes.")
    return {index: float(len(y) / (len(LABELS) * count)) for index, count in enumerate(counts)}


def quantize(tf, model, x):
    # Explicit fixed signature prevents accidental dynamic [N,5] firmware input.
    @tf.function(input_signature=[tf.TensorSpec([1, 5], tf.float32, name="flex_inputs")])
    def inference(values):
        return model(values, training=False)

    converter = tf.lite.TFLiteConverter.from_concrete_functions([inference.get_concrete_function()], model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = lambda: ([sample.reshape(1, 5)] for sample in x)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    return converter.convert()


def run(config, output, audit_only=False, overwrite=False):
    groups, audit = load_dataset(config)
    if not audit_only and not overwrite and any((output / name).exists()
                                               for name in ("model.keras", "model_int8.tflite", "manifest.json")):
        raise ValueError(f"Model artifacts already exist in {output}. Use --output NEW_DIR or --overwrite.")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "data_audit.json", audit)
    print(f"Data: {audit['rows']} rows, {len(LABELS)} classes, {len(FEATURES)} inputs", flush=True)
    for role, rows in groups.items():
        print(f"  {role}: {len(rows)} rows from {len(config[role + '_files'])} session(s)", flush=True)
    for warning in audit["warnings"]:
        print(f"Data note: {warning}", flush=True)
    if audit_only:
        print(f"Audit written to {output / 'data_audit.json'}", flush=True)
        return

    try:
        import numpy as np
        import tensorflow as tf
    except ImportError as error:
        raise ImportError("Install dependencies with .venv/Scripts/python.exe -m pip install -r requirements.txt") from error
    from evaluate import arrays, classification_metrics, tflite_predict, write_confusion
    from export_headers import export_headers, inspect_model

    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.threading.set_intra_op_parallelism_threads(1)
    tf.keras.utils.set_random_seed(config["seed"])
    tf.config.experimental.enable_op_determinism()
    data = {role: arrays(rows) for role, rows in groups.items()}
    x_train, y_train = data["train"]
    x_val, y_val = data["validation"]
    model = build_model(tf, config)
    print(f"Training 5 -> {config['hidden_units']} ReLU -> {len(LABELS)} Softmax; "
          f"{model.count_params()} parameters", flush=True)

    class Progress(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            if epoch == 0 or (epoch + 1) % 25 == 0:
                logs = logs or {}
                print(f"Epoch {epoch + 1}: loss={logs['loss']:.4f} "
                      f"accuracy={logs['accuracy']:.3f} val_loss={logs['val_loss']:.4f} "
                      f"val_accuracy={logs['val_accuracy']:.3f}", flush=True)

    stopping = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=config["patience"],
        min_delta=0.0001, restore_best_weights=True)
    history = model.fit(x_train, y_train, validation_data=(x_val, y_val),
        epochs=config["max_epochs"], batch_size=config["batch_size"],
        class_weight=class_weights(y_train), shuffle=True, verbose=0,
        callbacks=[stopping, Progress()])
    # Keras 2 may only restore automatically when patience stops training. Also
    # restore when the configured epoch cap is reached before patience expires.
    if stopping.best_weights is not None:
        model.set_weights(stopping.best_weights)
    # best_epoch tracks the checkpoint actually restored (min_delta included).
    best_epochs = int(stopping.best_epoch + 1)
    print(f"Best validation checkpoint: epoch {best_epochs}; converting to INT8", flush=True)
    evaluation = output / "evaluation"
    evaluation.mkdir(parents=True, exist_ok=True)
    model.save(evaluation / "model.keras")
    eval_content = quantize(tf, model, x_train)
    eval_details = inspect_model(eval_content)
    (evaluation / "model_int8.tflite").write_bytes(eval_content)
    metrics = {"evaluation_training_roles": ["train"], "best_epoch": best_epochs,
               "epochs_run": len(history.history["loss"]), "splits": {}}
    for role, (x, y) in data.items():
        float_scores = model(x, training=False).numpy()
        int_scores = tflite_predict(eval_content, x)
        float_report, _ = classification_metrics(y, float_scores, config["confidence_threshold"])
        int_report, confusion = classification_metrics(y, int_scores, config["confidence_threshold"])
        metrics["splits"][role] = {
            "scope": "training" if role == "train" else "early_stopping_validation" if role == "validation" else "held_out_test",
            "float": float_report, "int8": int_report,
            "quantization_top1_agreement": float(np.mean(float_scores.argmax(1) == int_scores.argmax(1))),
            "max_probability_difference": float(np.max(np.abs(float_scores - int_scores))),
        }
        write_confusion(evaluation / f"confusion_matrix_{role}.csv", confusion)
        if role == "test":
            write_confusion(output / "confusion_matrix.csv", confusion)
        print(f"{role}: float accuracy {float_report['accuracy']:.1%}; "
              f"INT8 accuracy {int_report['accuracy']:.1%}; "
              f"coverage at {config['confidence_threshold']:.0%} confidence {int_report['coverage']:.1%}", flush=True)
    write_json(output / "metrics.json", metrics)
    write_json(output / "history.json", history.history)
    # The evaluation model gets its own manifest so evaluate.py can reproduce held-out results.
    versions = dict(sorted((dist.metadata["Name"], dist.version)
                           for dist in importlib.metadata.distributions() if dist.metadata["Name"]))
    manifest = {
        "format_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(), "dependencies": versions,
        "config": config, "labels": list(LABELS), "tracks": list(range(len(LABELS))),
        "features": list(FEATURES), "preprocessing": {"offset": list(OFFSET), "scale": list(SCALE)},
        "dataset": audit, "parameter_count": model.count_params(), "best_epoch": best_epochs,
        "deployment_training_roles": ["train"],
        "deployment_training_sha256": [s["sha256"] for s in audit["sources"] if s["role"] == "train"],
        "deployment_model": eval_details,
        "evaluation_note": "metrics.json evaluates the train-only model; validation selects the checkpoint, test does not.",
    }
    write_json(evaluation / "manifest.json", manifest)
    content = eval_content
    if config["refit_all"]:
        print(f"Refitting all files for {best_epochs} epochs; held-out metrics remain those of evaluation/model_int8.tflite.", flush=True)
        tf.keras.backend.clear_session()
        tf.keras.utils.set_random_seed(config["seed"])
        model = build_model(tf, config)
        x_all = np.concatenate([value[0] for value in data.values()])
        y_all = np.concatenate([value[1] for value in data.values()])

        class RefitProgress(tf.keras.callbacks.Callback):
            def on_epoch_end(self, epoch, logs=None):
                if epoch == 0 or (epoch + 1) % 25 == 0:
                    print(f"Refit epoch {epoch + 1}/{best_epochs}", flush=True)

        model.fit(x_all, y_all, epochs=best_epochs, batch_size=config["batch_size"],
                  class_weight=class_weights(y_all), shuffle=True, verbose=0, callbacks=[RefitProgress()])
        content = quantize(tf, model, x_all)
        # Exercise the refitted artifact before writing deployable headers.
        tflite_predict(content, x_all)
        manifest["deployment_training_roles"] = list(data)
        manifest["deployment_training_sha256"] = [s["sha256"] for s in audit["sources"]]
        manifest["evaluation_note"] += " Deployment refit uses all files; it has no independent test score."
    model.save(output / "model.keras")
    model_path = output / "model_int8.tflite"
    model_path.write_bytes(content)
    manifest["deployment_model"] = export_headers(model_path, output / "include")
    (output / "labels.txt").write_text("\n".join(LABELS) + "\n", encoding="utf-8")
    # Raw reference vectors enable checking preprocessing/predictions on firmware.
    example_x, _ = arrays(groups["test"][:10])
    example_scores = tflite_predict(content, example_x)
    examples = []
    for (actual, values), scores in zip(groups["test"][:10], example_scores):
        predicted = int(scores.argmax())
        examples.append({"raw": list(values), "actual": actual, "predicted": LABELS[predicted],
                         "track": predicted, "confidence": float(scores[predicted])})
    write_json(output / "reference_predictions.json", examples)
    write_json(output / "manifest.json", manifest)
    accuracy = metrics["splits"]["test"]["int8"]["accuracy"]
    print(f"\nGenerated {len(content):,}-byte model and headers in {output / 'include'}", flush=True)
    print(f"Held-out INT8 accuracy (evaluation model): {accuracy:.1%}", flush=True)
    if accuracy < 0.8:
        print("Prototype result: collect more independent gestures and inspect confusion_matrix.csv before relying on playback.", flush=True)
    print("Board tensor arena, operator versions, latency and live playback still require hardware verification.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, help="Override output directory (relative to current directory)")
    parser.add_argument("--audit-only", action="store_true", help="Validate CSVs without TensorFlow")
    parser.add_argument("--refit-all", action="store_true", help="Refit all sessions after held-out evaluation")
    parser.add_argument("--overwrite", action="store_true", help="Replace model artifacts in the output directory")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.refit_all:
            config["refit_all"] = True
        if args.output:
            config["output_dir"] = str(args.output.resolve())
        run(config, Path(config["output_dir"]), args.audit_only, args.overwrite)
    except (OSError, ValueError, KeyError, ImportError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
