// Four static voltage inputs -> four dummy class scores.
// No sensors needed. Uses Chirale_TensorFlowLite, as in your working example.
#include <Arduino.h>
#include <math.h>
#include <Chirale_TensorFlowLite.h>
#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "model.h"
#include "test_data.h"

constexpr size_t kFeatures = 4;
const char labels[] = "ABCD";
constexpr size_t kClasses = sizeof(labels) - 1;
constexpr size_t kArenaSize = 16 * 1024;
alignas(16) uint8_t tensorArena[kArenaSize];
tflite::MicroInterpreter* interpreter = nullptr;
TfLiteTensor* input = nullptr;
TfLiteTensor* output = nullptr;

void stopWithError(const char* message) {
  Serial.println(message);
  while (true) delay(1000);
}

bool matches(TfLiteTensor* tensor, size_t width) {
  return tensor && tensor->type == kTfLiteFloat32 && tensor->dims &&
         tensor->dims->size == 2 && tensor->dims->data[0] == 1 &&
         tensor->dims->data[1] == (int)width &&
         tensor->bytes == width * sizeof(float);
}

void runTests() {
  Serial.println("\nDUMMY MODEL: highest voltage selects A/B/C/D. NOT real signs.");
  Serial.println("Case | voltages (V) | scores A B C D | expected/predicted | result | Invoke us");
  size_t completed = 0, correct = 0;
  uint32_t totalUs = 0, minUs = UINT32_MAX, maxUs = 0;

  for (size_t i = 0; i < testCount; ++i) {
    for (size_t f = 0; f < kFeatures; ++f) {
      input->data.f[f] = testCases[i].volts[f];
    }
    const uint32_t startUs = micros();
    const TfLiteStatus status = interpreter->Invoke();
    const uint32_t elapsedUs = micros() - startUs;
    if (status != kTfLiteOk) {
      Serial.print("Invoke failed on case ");
      Serial.println((unsigned int)(i + 1));
      continue;
    }
    bool finiteScores = true;
    size_t best = 0;
    for (size_t c = 0; c < kClasses; ++c) {
      if (!isfinite(output->data.f[c])) finiteScores = false;
      if (output->data.f[c] > output->data.f[best]) best = c;
    }
    if (!finiteScores) {
      Serial.println("ERROR: Non-finite model output.");
      continue;
    }
    const char predicted = labels[best];
    const bool pass = predicted == testCases[i].expected;
    Serial.print((unsigned int)(i + 1));
    Serial.print(" | ");
    for (size_t f = 0; f < kFeatures; ++f) {
      Serial.print(testCases[i].volts[f], 2); Serial.print(' ');
    }
    Serial.print("| ");
    for (size_t c = 0; c < kClasses; ++c) {
      Serial.print(output->data.f[c], 2); Serial.print(' ');
    }
    Serial.print("| "); Serial.print(testCases[i].expected);
    Serial.print('/'); Serial.print(predicted);
    Serial.print(pass ? " | PASS | " : " | FAIL | ");
    Serial.println(elapsedUs);
    completed++;
    if (pass) correct++;
    totalUs += elapsedUs;
    if (elapsedUs < minUs) minUs = elapsedUs;
    if (elapsedUs > maxUs) maxUs = elapsedUs;
    delay(10);
  }
  Serial.print("Completed: "); Serial.print((unsigned int)completed);
  Serial.print('/'); Serial.println((unsigned int)testCount);
  Serial.print("Expected-label matches: "); Serial.print((unsigned int)correct);
  Serial.print('/'); Serial.println((unsigned int)testCount);
  if (completed) {
    Serial.print("Invoke time, mean/min/max (us): ");
    Serial.print((float)totalUs / completed, 2); Serial.print('/');
    Serial.print(minUs); Serial.print('/'); Serial.println(maxUs);
  }
  Serial.println("Send r to rerun.");
}

void setup() {
  Serial.begin(115200);
  // Wait for the monitor: this is a tethered bench tester.
  while (!Serial) delay(10);
  delay(500);
  Serial.println("Four-finger model tester starting...");
  const tflite::Model* model = tflite::GetModel(g_model);
  if (model->version() != TFLITE_SCHEMA_VERSION)
    stopWithError("ERROR: Model schema mismatch.");
  static tflite::AllOpsResolver resolver;
  static tflite::MicroInterpreter instance(model, resolver, tensorArena, kArenaSize);
  interpreter = &instance;
  if (interpreter->AllocateTensors() != kTfLiteOk)
    stopWithError("ERROR: AllocateTensors failed. Check operators and arena size.");
  if (interpreter->inputs_size() != 1 || interpreter->outputs_size() != 1)
    stopWithError("ERROR: Expected exactly one input tensor and one output tensor.");
  input = interpreter->input(0);
  output = interpreter->output(0);
  if (!matches(input, kFeatures) || !matches(output, kClasses))
    stopWithError("ERROR: This harness requires float32 input [1,4] and output [1,4].");
  Serial.println("Model loaded. float32 input [1,4], output [1,4].");
  runTests();
}

void loop() {
  while (Serial.available()) {
    const char command = Serial.read();
    if (command == 'r' || command == 'R') runTests();
  }
  delay(10);
}
