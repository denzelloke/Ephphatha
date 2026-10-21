#pragma once
#include <cstdint>
#include "esp_err.h"

// One caller only: the main task owns all commands.
namespace speaker {
esp_err_t init(uint8_t volume);
esp_err_t set_volume(uint8_t volume);
esp_err_t play_track(uint16_t track); // /mp3/0001.mp3, etc.
esp_err_t stop();
}
