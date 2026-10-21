#include "model_runner.h"
#include "model_data.h"
#include "model_settings.h"
#include "sdkconfig.h"
#include "esp_log.h"
#include <algorithm>
#include <cmath>
#include <cstdint>

#if GLOVE_HAS_MODEL
#include "flatbuffers/verifier.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#endif

namespace model_runner {
static const char *TAG = "model";
#if GLOVE_HAS_MODEL
namespace {
alignas(16) uint8_t arena[CONFIG_GLOVE_ARENA_KB * 1024];
tflite::MicroMutableOpResolver<8> resolver;
tflite::MicroInterpreter *interpreter = nullptr;
TfLiteTensor *input = nullptr, *output = nullptr;
bool attempted = false, ready = false;
bool supported(const TfLiteTensor *tensor) {
    if (tensor->type == kTfLiteFloat32) return true;
    if (tensor->type != kTfLiteInt8 && tensor->type != kTfLiteUInt8) return false;
    if (tensor->quantization.type != kTfLiteAffineQuantization || !tensor->quantization.params) return false;
    const auto *affine = static_cast<const TfLiteAffineQuantization *>(tensor->quantization.params);
    if (!affine->scale || !affine->zero_point || affine->scale->size != 1 || affine->zero_point->size != 1)
        return false; // External I/O uses per-tensor quantization only.
    const int lo = tensor->type == kTfLiteInt8 ? -128 : 0;
    const int hi = tensor->type == kTfLiteInt8 ? 127 : 255;
    return std::isfinite(tensor->params.scale) && tensor->params.scale > 0 &&
        tensor->params.zero_point >= lo && tensor->params.zero_point <= hi;
}
bool shape(const TfLiteTensor *t, int count) {
    return t && t->dims && t->dims->size == 2 &&
        t->dims->data[0] == 1 && t->dims->data[1] == count;
}
float read_output(int i) {
    if (output->type == kTfLiteFloat32) return output->data.f[i];
    int q = output->type == kTfLiteInt8 ? output->data.int8[i] : output->data.uint8[i];
    return (q - output->params.zero_point) * output->params.scale;
}
}
esp_err_t init() {
    if (ready) return ESP_OK;
    if (attempted) return ESP_ERR_INVALID_STATE;
    attempted = true;
    flatbuffers::Verifier verifier(g_model_data, g_model_data_len);
    if (!tflite::VerifyModelBuffer(verifier)) {
        ESP_LOGE(TAG, "Invalid/truncated TFLite flatbuffer"); return ESP_ERR_INVALID_ARG;
    }
    const tflite::Model *model = tflite::GetModel(g_model_data);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        ESP_LOGE(TAG, "Model schema mismatch"); return ESP_ERR_NOT_SUPPORTED;
    }
    if (resolver.AddFullyConnected() != kTfLiteOk || resolver.AddRelu() != kTfLiteOk ||
        resolver.AddSoftmax() != kTfLiteOk || resolver.AddReshape() != kTfLiteOk ||
        resolver.AddQuantize() != kTfLiteOk || resolver.AddDequantize() != kTfLiteOk ||
        resolver.AddAdd() != kTfLiteOk || resolver.AddMul() != kTfLiteOk) return ESP_FAIL;
    static tflite::MicroInterpreter instance(model, resolver, arena, sizeof(arena));
    interpreter = &instance;
    if (interpreter->AllocateTensors() != kTfLiteOk) {
        ESP_LOGE(TAG, "AllocateTensors failed: check unsupported ops/versions and arena size");
        return ESP_FAIL;
    }
    if (interpreter->inputs_size() != 1 || interpreter->outputs_size() != 1) return ESP_ERR_NOT_SUPPORTED;
    input = interpreter->input(0); output = interpreter->output(0);
    if (!shape(input, 5) || !shape(output, kClassCount) || !supported(input) || !supported(output)) {
        ESP_LOGE(TAG, "Need input [1,5], output [1,%d], float32/int8/uint8", kClassCount);
        return ESP_ERR_NOT_SUPPORTED;
    }
    ready = true;
    ESP_LOGI(TAG, "Model ready, classes=%d, arena used=%u bytes", kClassCount,
             static_cast<unsigned>(interpreter->arena_used_bytes()));
    return ESP_OK;
}
esp_err_t predict(const flex::Sample &sample, Prediction &prediction) {
    prediction = {};
    if (!ready) return ESP_ERR_INVALID_STATE;
    for (int i = 0; i < 5; ++i) {
        if (sample[i] < 0 || sample[i] > 4095) return ESP_ERR_INVALID_ARG;
        const float value = (sample[i] - kInputOffset[i]) * kInputScale[i];
        if (!std::isfinite(value)) return ESP_ERR_INVALID_ARG;
        if (input->type == kTfLiteFloat32) input->data.f[i] = value;
        else {
            const float q = std::round(value / input->params.scale) + input->params.zero_point;
            if (input->type == kTfLiteInt8)
                input->data.int8[i] = static_cast<int8_t>(std::max(-128.0f, std::min(127.0f, q)));
            else input->data.uint8[i] = static_cast<uint8_t>(std::max(0.0f, std::min(255.0f, q)));
        }
    }
    if (interpreter->Invoke() != kTfLiteOk) return ESP_FAIL;
    int best = -1; float score = -1, sum = 0;
    for (int i = 0; i < kClassCount; ++i) {
        const float value = read_output(i);
        if (!std::isfinite(value) || value < -0.01f || value > 1.01f) return ESP_ERR_INVALID_RESPONSE;
        sum += value;
        if (value > score) { best = i; score = value; }
    }
    // Softmax probabilities expected; allow rounding error from quantization.
    if (std::fabs(sum - 1.0f) > 0.15f) return ESP_ERR_INVALID_RESPONSE;
    prediction = {best, score};
    return ESP_OK;
}
const char *label(int index) { return index >= 0 && index < kClassCount ? kLabels[index] : "?"; }
int track(int index) { return index >= 0 && index < kClassCount ? kTracks[index] : 0; }
#else
esp_err_t init() {
    ESP_LOGW(TAG, "No model installed. Convert your .tflite with tools/tflite_to_header.py, rebuild and flash.");
    return ESP_ERR_NOT_FOUND;
}
esp_err_t predict(const flex::Sample &, Prediction &prediction) {
    prediction = {}; return ESP_ERR_INVALID_STATE;
}
const char *label(int) { return "?"; }
int track(int) { return 0; }
#endif
}
