"""Evaluate exported INT8 predictions or try five raw ADC readings on the PC."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

from data import DEFAULT_CONFIG, FEATURES, LABELS, OFFSET, SCALE, load_config, load_dataset, write_json
from export_headers import inspect_model


def arrays(rows):
    import numpy as np
    raw = np.asarray([values for _, values in rows], dtype=np.float32)
    x = (raw - np.asarray(OFFSET, dtype=np.float32)) * np.asarray(SCALE, dtype=np.float32)
    y = np.asarray([LABELS.index(label) for label, _ in rows], dtype=np.int64)
    return x, y


def tflite_predict(content, x):
    """Use reference kernels and the same rounding/clamping as model_runner.cpp."""
    import numpy as np
    import tensorflow as tf
    inspect_model(content)
    interpreter = tf.lite.Interpreter(model_content=content, num_threads=1,
        experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF)
    interpreter.allocate_tensors()
    input_info = interpreter.get_input_details()[0]
    output_info = interpreter.get_output_details()[0]
    in_scale, in_zero = input_info["quantization"]
    out_scale, out_zero = output_info["quantization"]
    probabilities = []
    for sample in np.asarray(x, dtype=np.float32):
        value = sample / np.float32(in_scale)
        # std::round uses ties away from zero; np.round uses ties to even.
        rounded = np.copysign(np.floor(np.abs(value) + np.float32(0.5)), value)
        quantized = np.clip(rounded + in_zero, -128, 127).astype(np.int8)
        interpreter.set_tensor(input_info["index"], quantized.reshape(1, 5))
        interpreter.invoke()
        output = interpreter.get_tensor(output_info["index"])[0]
        probabilities.append((output.astype(np.float32) - out_zero) * out_scale)
    scores = np.asarray(probabilities, dtype=np.float32)
    if (not np.isfinite(scores).all() or (scores < -0.01).any() or (scores > 1.01).any()
            or (np.abs(scores.sum(axis=1) - 1) > 0.15).any()):
        raise ValueError("Model outputs violate driver's softmax probability checks.")
    return scores


def classification_metrics(y, probabilities, threshold):
    import numpy as np
    predictions = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    accepted = confidence >= threshold
    correct = predictions == y
    confusion = np.zeros((len(LABELS), len(LABELS)), dtype=int)
    np.add.at(confusion, (y, predictions), 1)
    per_class = {}
    for index, label in enumerate(LABELS):
        support, predicted = int(confusion[index].sum()), int(confusion[:, index].sum())
        tp = int(confusion[index, index])
        recall = tp / support if support else None
        precision = tp / predicted if predicted else 0.0
        f1 = 2 * precision * recall / (precision + recall) if recall and precision else 0.0
        per_class[label] = {"support": support, "recall": recall, "precision": precision, "f1": f1}
    neutral = y == 0
    false_speech = neutral & accepted & (predictions != 0)
    metrics = {
        "rows": int(len(y)), "accuracy": float(correct.mean()),
        "macro_recall": float(np.mean([v["recall"] for v in per_class.values() if v["recall"] is not None])),
        "macro_f1": float(np.mean([v["f1"] for v in per_class.values() if v["support"]])),
        "per_class": per_class, "confidence_threshold": threshold,
        "accepted_rows": int(accepted.sum()), "coverage": float(accepted.mean()),
        "accepted_accuracy": float(correct[accepted].mean()) if accepted.any() else None,
        "neutral_false_speech_rows": int(false_speech.sum()),
        "neutral_false_speech_rate": float(false_speech.sum() / neutral.sum()) if neutral.any() else None,
        "note": "Single-row metrics; temporal stability/cooldown and confidence calibration are not tested.",
    }
    return metrics, confusion


def write_confusion(path, confusion):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["actual / predicted", *LABELS])
        for label, row in zip(LABELS, confusion.tolist()):
            writer.writerow([label, *row])


def load_manifest(model_path):
    model_path = Path(model_path)
    manifest = json.loads(model_path.with_name("manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("labels") != list(LABELS) or
            manifest.get("preprocessing") != {"offset": list(OFFSET), "scale": list(SCALE)} or
            manifest.get("deployment_model", {}).get("sha256") != hashlib.sha256(model_path.read_bytes()).hexdigest()):
        raise ValueError("Model/manifest label, preprocessing or SHA256 mismatch.")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model", type=Path, help="Defaults to config output_dir/model_int8.tflite")
    parser.add_argument("--split", choices=("train", "validation", "test"), default="test")
    parser.add_argument("--raw", type=int, nargs=5, metavar=tuple(FEATURES))
    parser.add_argument("--output", type=Path, help="Optional JSON evaluation report")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        path = args.model or Path(config["output_dir"]) / "model_int8.tflite"
        manifest = load_manifest(path)
        content = path.read_bytes()
        if args.raw is not None:
            if any(v < 0 or v > 4095 for v in args.raw):
                raise ValueError("Raw values must be in 0..4095.")
            x, _ = arrays([("!", args.raw)])
            probabilities = tflite_predict(content, x)[0]
            index = int(probabilities.argmax())
            threshold = manifest["config"]["confidence_threshold"]
            result = {"raw": args.raw, "label": LABELS[index], "track": index,
                      "confidence": float(probabilities[index]),
                      "passes_confidence_threshold": bool(probabilities[index] >= threshold),
                      "note": "Driver also requires stable predictions and applies repeat/cooldown rules."}
        else:
            groups, audit = load_dataset(config)
            # Identify held-out data by content hash, not just its configured role.
            trained_hashes = set(manifest["deployment_training_sha256"])
            sources = [s for s in audit["sources"] if s["role"] == args.split]
            overlap = any(s["sha256"] in trained_hashes for s in sources)
            known = {s["sha256"] for s in manifest["dataset"]["sources"]}
            result_scope = ("contains_training_data" if overlap else
                            "original_held_out" if all(s["sha256"] in known for s in sources) else
                            "new_data_not_used_for_training")
            x, y = arrays(groups[args.split])
            probabilities = tflite_predict(content, x)
            result, _ = classification_metrics(y, probabilities, config["confidence_threshold"])
            result.update({"split": args.split, "scope": result_scope, "sources": sources})
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, ImportError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
