"""Optional desktop inspection. Run in your TensorFlow training environment.

python tools/inspect_model.py model.tflite --labels labels.txt
This checks tensor metadata and lists operators; it is not a microcontroller test.
"""
import argparse
from pathlib import Path
import numpy as np
import tensorflow as tf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("--labels", required=True, type=Path)
    args = parser.parse_args()
    labels = [x.strip() for x in args.labels.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    from tflite_to_header import render
    render(Path(args.model).read_bytes(), labels)  # Validate labels and basic file format.
    interpreter = tf.lite.Interpreter(model_path=args.model)
    interpreter.allocate_tensors()
    inputs, outputs = interpreter.get_input_details(), interpreter.get_output_details()
    if len(inputs) != 1 or len(outputs) != 1:
        raise SystemExit("Need exactly one input and one output.")
    for name, tensor, shape in [("input", inputs[0], [1, 5]), ("output", outputs[0], [1, len(labels)])]:
        print(name, "shape:", tensor["shape"], "dtype:", tensor["dtype"], "quantization:", tensor["quantization"])
        if list(tensor["shape"]) != shape:
            raise SystemExit(f"Wrong {name} shape; expected {shape}")
        if tensor["dtype"] not in (np.float32, np.int8, np.uint8):
            raise SystemExit(f"Unsupported {name} type.")
        if tensor["dtype"] != np.float32:
            if len(tensor["quantization_parameters"]["scales"]) != 1 or tensor["quantization"][0] <= 0:
                raise SystemExit("Need per-tensor quantization for input/output.")
    print("\nExact output index -> label -> track:")
    for i, label in enumerate(labels):
        print(i, label, 0 if label == "!" else ord(label) - ord("a") + 1)
    print("\nModel operators and tensor details:")
    tf.lite.experimental.Analyzer.analyze(model_path=args.model)
    print("Check operators against model_runner.cpp. Test predictions on held-out data separately.")


if __name__ == "__main__":
    main()
