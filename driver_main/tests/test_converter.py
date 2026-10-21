"""Tests byte embedding and class order, not inference."""
import re
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tflite_to_header import render


class ConverterTests(unittest.TestCase):
    def setUp(self):
        # Synthetic byte fixture; deliberately NOT a runnable neural network.
        self.data = struct.pack("<I", 8) + b"TFL3" + bytes(range(256))

    def test_exact_bytes_and_class_order(self):
        header = render(self.data, ["z", "!", "a"])
        embedded = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", header))
        self.assertEqual(self.data, embedded)
        self.assertIn('kLabels[] = {"z", "!", "a"}', header)
        self.assertIn('kTracks[] = {26, 0, 1}', header)
        self.assertIn('alignas(16)', header)

    def test_bad_file(self):
        for data in [b"", b"not a model file", struct.pack("<I", 9000) + b"TFL3" + b"abcd"]:
            with self.assertRaises(ValueError):
                render(data, ["!", "a"])

    def test_bad_labels(self):
        for labels in [["a", "b"], ["!", "!"], ["!", "A"], ["!"], ["!", "hello"]]:
            with self.assertRaises(ValueError):
                render(self.data, labels)


if __name__ == "__main__":
    unittest.main()
