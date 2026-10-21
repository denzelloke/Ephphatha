#pragma once
#include "flex_sensors.h"

namespace model_runner {
struct Prediction { int class_index = -1; float confidence = 0; };
esp_err_t init();
esp_err_t predict(const flex::Sample &sample, Prediction &prediction);
const char *label(int class_index);
int track(int class_index); // 0 = silent; a = 1, ..., z = 26.
}
