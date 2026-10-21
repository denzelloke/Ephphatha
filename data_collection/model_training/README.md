# Flex sensor model training

Train a small classifier on the five selected CSV sessions and generate the two
headers used by `Ephphatha/driver_main`. Training runs on your computer; inference
runs on the ESP32-S3. Speaker audio remains on the DFPlayer's SD card.

Open `model_training.code-workspace` in VS Code, or open this directory directly.
Run the commands below from **this directory** in PowerShell.

## 1. Create the Python environment

Use 64-bit **Python 3.10 or 3.11**. The project deliberately pins TensorFlow 2.15.1
and NumPy 1.26.4 as its conversion baseline; these are not claims about the newest
releases. CPU training is sufficient. Keep this environment separate from ESP-IDF.

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If starting in `data_collection`, first run `cd model_training`. Calling the venv
executable directly avoids PowerShell activation/execution-policy issues. Initial
installation downloads TensorFlow and its dependencies and can take several minutes.

TensorFlow installation reference: <https://www.tensorflow.org/install/pip>.

## 2. Audit and train

```powershell
.\.venv\Scripts\python.exe train.py --audit-only
.\.venv\Scripts\python.exe train.py --config config.json
```

The audit also runs with plain `python train.py --audit-only`, before dependencies
are installed. Config paths resolve relative to `config.json`, so training can be
launched from any directory. `--output`, when supplied, resolves relative to your
terminal's current directory.

`config.json` explicitly selects these sessions; other CSVs are not included:

| Split | CSV suffixes | Rows | Purpose |
| --- | --- | ---: | --- |
| Train | `163349_498883`, `163605_782766`, `163833_153376` | 261 | Fit weights; calibrate INT8 ranges |
| Validation | `164039_221010` | 87 | Select checkpoint by validation loss |
| Test | `164039_221786` | 87 | Evaluate after training; never select checkpoints |

The classifier is `5 → 16 ReLU → 27 Softmax`, with 555 trainable parameters.
Each row is one example. The three readings from a capture are never split across
training and evaluation: whole CSV files stay together. Balanced class weights
compensate for the extra `!` rows. Adam, L2 regularization, a fixed random seed,
deterministic CPU operations, and early stopping are configured in `config.json`.
Determinism is intended within the pinned environment; exact bytes may differ
across hardware or dependency versions.

Input order is **thumb, index, middle, ring, pinky**, normalized as `raw / 4095`.
Preprocessing lives outside the neural network and is exported in the settings
header. Do not normalize twice. Training, desktop INT8 evaluation, and firmware
use the same feature order and preprocessing. INT8 evaluation uses the driver's
round-away-from-zero input quantization and clamping.

To retrain, preserve the previous run with a new output directory:

```powershell
.\.venv\Scripts\python.exe train.py --output artifacts/run2
```

Or deliberately replace the default generated outputs:

```powershell
.\.venv\Scripts\python.exe train.py --overwrite
```

## 3. Read the results

The default output is `artifacts/`:

| Output | Contents |
| --- | --- |
| `include/model_data.h` | Aligned model bytes, `GLOVE_HAS_MODEL`, class labels and audio tracks |
| `include/model_settings.h` | Exactly five offsets and five scales for the driver |
| `model_int8.tflite` | Deployment model with INT8 input `[1,5]` and output `[1,27]` |
| `model.keras` | Floating-point deployment model for inspection |
| `metrics.json` | Float/INT8 accuracy, recall, F1, confidence coverage, neutral false speech and quantization differences |
| `confusion_matrix.csv` | Held-out test confusion matrix: rows are actual classes; columns are predictions |
| `data_audit.json` | Source hashes, class counts, duplicates, conflicting labels, split overlap and ADC boundary counts |
| `manifest.json` | Dependencies, configuration, dataset identity, model SHA256, tensor quantization and operator versions |
| `history.json` | Training/validation history |
| `reference_predictions.json` | Raw test examples and deployment predictions for firmware comparison |
| `evaluation/` | Preserved train-only model, manifest and each split's INT8 confusion matrix |
| `labels.txt` | Exact output index order: `!`, then `a` through `z` |

Look at **test INT8 accuracy**, per-class recall and confidence coverage together.
Accepted accuracy is `null` when no predictions reach the configured confidence
threshold; zero coverage does not mean successful recognition. Softmax confidence
is not a calibrated guarantee. The reports measure individual readings, not live
stability/cooldown behavior.

Try a current sensor reading (replace the five example values):

```powershell
.\.venv\Scripts\python.exe evaluate.py --raw 4095 3406 3209 4095 1774
```

Recheck the test split or export headers again:

```powershell
.\.venv\Scripts\python.exe evaluate.py --split test --output artifacts/test_recheck.json
.\.venv\Scripts\python.exe export_headers.py artifacts/model_int8.tflite --output artifacts/include
```

The exporter requires the adjacent `manifest.json` and checks its model hash, class
order and preprocessing. It is for models produced by this trainer, not arbitrary
TFLite files with unknown label mappings. Conversion enforces integer builtins,
checks the operators registered by `model_runner.cpp`, and exercises the model with
a desktop reference interpreter. Actual TFLite Micro operator-version support,
arena allocation and latency must still be checked on the board.

Optional final refit on all five files:

```powershell
.\.venv\Scripts\python.exe train.py --refit-all --output artifacts/refit
```

This first trains/evaluates the normal split, then creates fresh weights using all
five files for the chosen number of epochs. `metrics.json` still describes the
preserved `evaluation/model_int8.tflite`, **not** the refitted deployment model.
The refit has no independent test score. `evaluate.py` identifies evaluations that
contain deployment training data by matching source hashes.

Quantization reference:
<https://developers.google.com/edge/litert/conversion/tensorflow/quantization/post_training_quantization>.

## 4. Install the generated headers in the ESP32-S3 driver

From this training directory, copy **both** headers into the existing driver:

```powershell
Copy-Item -LiteralPath artifacts/include/model_data.h -Destination ../../driver_main/main/model/model_data.h
Copy-Item -LiteralPath artifacts/include/model_settings.h -Destination ../../driver_main/main/model/model_settings.h
```

These commands replace the driver's model placeholder and preprocessing settings.
For a refit run, use `artifacts/refit/include/` as the source instead.

The generated symbols match `driver_main/main/model_runner.cpp`:
`g_model_data`, `g_model_data_len`, `kClassCount`, `kLabels`, `kTracks`,
`kInputOffset`, `kInputScale`, and `GLOVE_HAS_MODEL=1`.
The existing settings file inspected during setup contained six initializers for
a five-element scale array; the generated replacement has exactly five.

Track mapping is fixed:

| Class/output index | Label | DFPlayer track |
| --- | --- | --- |
| 0 | `!` (no gesture) | 0: no playback |
| 1–26 | `a`–`z` | 1–26: `/mp3/0001.mp3` through `/mp3/0026.mp3` |

Use an **ESP-IDF terminal**, separate from the training venv:

```powershell
cd ../../driver_main
idf.py --version
idf.py menuconfig
```

Select **Flex Voice → Operating mode → Live sensors -> model -> speaker**. Retain
the project's working ESP32-S3 target, USB console, wiring and speaker settings.
Then run, substituting the board's actual COM port:

```powershell
idf.py build
idf.py -p COM7 flash monitor
```

Close serial collection/other monitors before flashing. Exit IDF Monitor with
`Ctrl+]`. The driver's `s` command stops/pauses playback; `r` resumes it.

The actual inspected driver manifest pins **ESP-IDF >=6.1.0,<6.2.0** and
**esp-tflite-micro 1.4.1**. Its existing README mentions older versions; use the
working build environment and actual manifest rather than changing versions based
on that README. This training workspace does not modify driver dependencies.

At startup, check `Model ready`, `classes=27`, and reported arena usage. The driver
currently defaults to a 64 KiB tensor arena; model file size does not determine
arena size. If allocation fails, inspect operator/version compatibility and arena
settings. No board RAM or timing claim is made by desktop conversion.

Check `RAW`, `PRED` and `PLAY` logs. The driver requires the confidence threshold,
several stable predictions, and cooldown. A confident stable `!` rearms the same
letter; no track is sent for `!`. Verify neutral readings stay silent, letters play
the expected tracks, holding a gesture does not repeat audio, and returning to
neutral lets you speak the same letter again.

## Data limitations and next collection

There are 15 rows per letter but only five independent captures per letter. The
three readings from each capture are close in time. Some sensors reach 4095;
inspect divider/calibration behavior if many gestures clip. The model sees finger
bending only; it has no hand orientation or motion input, so similar sensor vectors
may remain hard to distinguish regardless of training duration.

Collect more independent captures, remove/reapply the glove between sessions, and
include realistic neutral/transition poses. Keep new sessions in separate files.
Keep a fresh session untouched for testing; changing settings repeatedly based on
the same test score makes that session part of model development. For future data,
consider recording a capture ID and timestamp in a new collector format; this
trainer intentionally validates the current six-column CSV format strictly.

## Verification

Run the unit checks in the training environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The checks cover malformed data, session leakage guards, conflicting labels,
class/track mapping, metric edge cases, and (when artifacts exist) the exact header
bytes and reproduced INT8 predictions. `tests/check_headers.cpp` can additionally
be compiled with a C++17 compiler using `-I artifacts/include -fsyntax-only`.
