"""Data failures and exported-model contract checks; no board is needed."""

import csv
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data import FEATURES, LABELS, load_config, load_dataset, read_csv
from export_headers import render_headers


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.config = {"data_dir": str(self.directory)}
        for number, role in enumerate(("train", "validation", "test")):
            filename = f"{role}.csv"
            self.config[f"{role}_files"] = [filename]
            self.write(filename, [(label, [number * 500 + i * 10 + j for j in range(5)])
                                  for i, label in enumerate(LABELS)])

    def write(self, filename, rows):
        with (self.directory / filename).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Label", *FEATURES])
            for label, values in rows:
                writer.writerow([label, *values])

    def test_whole_sessions_and_fixed_order(self):
        groups, audit = load_dataset(self.config)
        self.assertEqual(audit["rows"], 81)
        self.assertEqual(audit["cross_split_identical_vectors"], 0)
        self.assertEqual([label for label, _ in groups["train"]], list(LABELS))
        self.assertEqual(groups["test"][1][1][0], 1010)

    def test_same_path_cannot_cross_splits(self):
        self.config["test_files"] = ["train.csv"]
        with self.assertRaisesRegex(ValueError, "more than once"):
            load_dataset(self.config)

    def test_renamed_duplicate_file_is_rejected(self):
        (self.directory / "test.csv").write_bytes((self.directory / "train.csv").read_bytes())
        with self.assertRaisesRegex(ValueError, "Duplicate CSV contents"):
            load_dataset(self.config)

    def test_missing_classes_fail_before_training(self):
        self.write("test.csv", [("!", [10] * 5)])
        with self.assertRaisesRegex(ValueError, "missing classes"):
            load_dataset(self.config)

    def test_bad_sensor_and_label_rows_fail(self):
        for label, values in (("a", [4096] * 5), ("A", [10] * 5), ("", [10] * 5),
                              ("a", ["NaN"] * 5), ("a", [10] * 4), ("a", [10] * 6)):
            with self.subTest(label=label, values=values):
                self.write("bad.csv", [(label, values)])
                with self.assertRaises(ValueError):
                    read_csv(self.directory / "bad.csv")

    def test_conflicting_labels_are_reported_without_silent_dedup(self):
        rows = read_csv(self.directory / "train.csv")
        rows.extend([("a", [123] * 5), ("b", [123] * 5), ("a", [123] * 5)])
        self.write("train.csv", rows)
        groups, audit = load_dataset(self.config)
        self.assertEqual(len(groups["train"]), 30)
        self.assertEqual(audit["conflicting_label_vectors"], 1)
        self.assertEqual(audit["duplicate_labelled_rows"], 1)

    def test_workspace_data_and_split_sizes(self):
        groups, audit = load_dataset(load_config())
        self.assertEqual([len(groups[k]) for k in ("train", "validation", "test")], [261, 87, 87])
        self.assertEqual(audit["rows"], 435)
        self.assertEqual(len(audit["sources"]), 5)

    def test_headers_have_matching_fixed_contract(self):
        model = b"\x00\x00\x00\x00TFL3test"
        header, settings = render_headers(model)
        self.assertEqual(bytes(int(s, 16) for s in re.findall(r"0x([0-9a-f]{2})", header)), model)
        self.assertIn('"!", "a", "b"', header)
        self.assertIn("kInputScale[5]", settings)
        self.assertEqual(settings.count("1.0f / 4095.0f"), 5)


@unittest.skipUnless(importlib.util.find_spec("numpy"), "NumPy not installed")
class MetricTests(unittest.TestCase):
    def test_no_confident_predictions_and_neutral_false_speech(self):
        import numpy as np
        from evaluate import classification_metrics
        y = np.array([0, 1, 2])
        scores = np.full((3, 27), 1 / 27)
        report, confusion = classification_metrics(y, scores, 0.8)
        self.assertEqual(report["accepted_rows"], 0)
        self.assertIsNone(report["accepted_accuracy"])
        self.assertEqual(int(confusion.sum()), 3)
        scores[:] = 0
        scores[:, 1] = 1
        report, _ = classification_metrics(y, scores, 0.8)
        self.assertEqual(report["neutral_false_speech_rate"], 1)
        self.assertAlmostEqual(report["accuracy"], 1 / 3)
        self.assertEqual(report["per_class"]["b"]["recall"], 0)


@unittest.skipUnless((ROOT / "artifacts/manifest.json").exists() and importlib.util.find_spec("tensorflow"),
                     "Train the default artifacts with TensorFlow first")
class ArtifactTests(unittest.TestCase):
    def test_headers_embed_exact_model_bytes(self):
        content = (ROOT / "artifacts/model_int8.tflite").read_bytes()
        header = (ROOT / "artifacts/include/model_data.h").read_text()
        embedded = bytes(int(s, 16) for s in re.findall(r"0x([0-9a-f]{2})", header))
        self.assertEqual(embedded, content)
        from evaluate import load_manifest
        self.assertEqual(load_manifest(ROOT / "artifacts/model_int8.tflite")["labels"], list(LABELS))

    def test_reference_predictions_and_held_out_report_reproduce(self):
        import numpy as np
        from evaluate import arrays, classification_metrics, tflite_predict
        content = (ROOT / "artifacts/model_int8.tflite").read_bytes()
        examples = json.loads((ROOT / "artifacts/reference_predictions.json").read_text())
        x, _ = arrays([(example["actual"], example["raw"]) for example in examples])
        scores = tflite_predict(content, x)
        for example, probabilities in zip(examples, scores):
            self.assertEqual(example["predicted"], LABELS[int(probabilities.argmax())])
            self.assertAlmostEqual(example["confidence"], float(probabilities.max()), places=6)
        groups, _ = load_dataset(load_config())
        x, y = arrays(groups["test"])
        evaluation = (ROOT / "artifacts/evaluation/model_int8.tflite").read_bytes()
        scores = tflite_predict(evaluation, x)
        result, _ = classification_metrics(y, scores, 0.8)
        saved = json.loads((ROOT / "artifacts/metrics.json").read_text())["splits"]["test"]["int8"]
        self.assertAlmostEqual(result["accuracy"], saved["accuracy"])
        self.assertTrue(np.all(np.abs(scores.sum(axis=1) - 1) <= 0.15))


@unittest.skipUnless(importlib.util.find_spec("tensorflow"), "TensorFlow not installed")
class RefitTests(unittest.TestCase):
    def test_refit_keeps_evaluation_separate_and_can_export_again(self):
        # Short subprocess exercises both conversions and manifests without
        # changing the real run or its held-out results.
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = load_config()
            config.update({"output_dir": str(directory / "output"), "max_epochs": 2,
                           "patience": 1, "refit_all": True})
            config_path = directory / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "train.py"), "--config", str(config_path)],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = directory / "output"
            deployment = json.loads((output / "manifest.json").read_text())
            evaluation = json.loads((output / "evaluation/manifest.json").read_text())
            self.assertEqual(deployment["deployment_training_roles"], ["train", "validation", "test"])
            self.assertEqual(len(deployment["deployment_training_sha256"]), 5)
            self.assertEqual(evaluation["deployment_training_roles"], ["train"])
            self.assertEqual(len(evaluation["deployment_training_sha256"]), 3)
            self.assertNotEqual(deployment["deployment_model"]["sha256"], evaluation["deployment_model"]["sha256"])
            result = subprocess.run([sys.executable, str(ROOT / "export_headers.py"),
                                     str(output / "model_int8.tflite"), "--output", str(output / "reexport")],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((output / "include/model_data.h").read_bytes(),
                             (output / "reexport/model_data.h").read_bytes())


if __name__ == "__main__":
    unittest.main()
