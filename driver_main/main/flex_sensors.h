#pragma once
#include <array>
#include "esp_err.h"

namespace flex {
constexpr int kCount = 5;
// Fixed order: thumb, index, middle, ring, pinky. Raw 12-bit ADC counts.
using Sample = std::array<int, kCount>;
esp_err_t init();
esp_err_t read(Sample &sample);
}
