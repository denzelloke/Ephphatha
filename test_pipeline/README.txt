FOUR-FINGER ESP32-S3 DUMMY MODEL TESTER

1. Extract the ZIP. Open FourFingerTester/FourFingerTester.ino.
2. Use your already-working Chirale_TensorFlowLite library and ESP32 package.
3. Keep USB Mode = Hardware CDC and JTAG, USB CDC On Boot = Enabled,
   Upload Mode = UART0 / Hardware CDC. Select the current /dev/ttyACM port.
4. Upload. Open Serial Monitor at 115200 baud. Press RESET if needed.
5. Send r to rerun. Any line-ending selection is OK.

Do NOT copy this over the sine example while retaining its model.h.
This folder includes its own complete model.h. No Python installation or model
conversion is required to run the supplied dummy.

FILES
FourFingerTester.ino: runtime, shape/type checks, test loop, timing.
model.h: complete embedded dummy TFLite binary as C++ bytes.
test_data.h: static four-voltage snapshots and expected dummy letters.
dummy_model.tflite: the same model in standard binary format.
make_dummy_model.py: optional stdlib-only model regeneration source.
export_model_header.py: optional converter for your friend's future .tflite.

MODEL
Input: one float32 tensor [1,4], thumb/index/middle/ring in volts.
Output: one float32 tensor [1,4], scores in A/B/C/D order.
Graph: a single fully-connected layer, identity 4x4 weights, zero bias,
no activation. Thus output scores equal input voltages. The sketch chooses
argmax (first class wins ties). These scores are NOT probabilities.
This is an intentionally untrained model, NOT a sign-language classifier.
The letters are placeholders. No glove or IMU is required.

Expected predictions for the seven supplied cases: A B C D C D D.
Expect 7/7 label matches. This is a wiring/firmware test, not ML accuracy.

TIMING
micros() surrounds Invoke() only. The first invocation is included. Input
copying, printing and delays are excluded. This very small dummy does not
predict the timing or RAM requirement of a future trained model.
Arena: 16 KiB of internal RAM. It is working memory, not model storage size.

NEXT MODEL
Replace model.h using:
  python3 export_model_header.py path/to/new_model.tflite
For direct replacement keep float32 [1,4] input and float32 [1,4] output,
agreed voltage preprocessing, label order, compatible ops and memory use.
For another number of classes, update labels in the sketch and test labels.
For quantized input/output, input/output conversion must also be adapted.
Do not run make_dummy_model.py afterward: it would restore the dummy model.
Replace synthetic fixtures with separately held-out labelled recordings for
meaningful recognition evaluation. Normalization must match training.

VALIDATION
The serialized graph, buffers and dense-layer reference outputs were checked
locally. No Arduino toolchain, TFLite runtime, or physical ESP32 was available
here, so compilation and on-device execution remain to be confirmed by upload.
