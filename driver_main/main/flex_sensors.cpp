#include "flex_sensors.h"
#include "esp_adc/adc_oneshot.h"
#include "sdkconfig.h"

#if !CONFIG_IDF_TARGET_ESP32S3
#error "This project's ADC channel mapping is for ESP32-S3."
#endif

namespace flex {
namespace {
adc_oneshot_unit_handle_t units[2] = {};
// GPIO4/5/6/7 -> ADC1 channels 3/4/5/6; GPIO15 -> ADC2 channel 4.
constexpr adc_channel_t channels[kCount] = {
    ADC_CHANNEL_3, ADC_CHANNEL_4, ADC_CHANNEL_5, ADC_CHANNEL_6, ADC_CHANNEL_4
};
void cleanup() {
    for (auto &unit : units) {
        if (unit) { adc_oneshot_del_unit(unit); unit = nullptr; }
    }
}
}
esp_err_t init() {
    if (units[0] && units[1]) return ESP_OK;
    for (int i = 0; i < 2; ++i) {
        adc_oneshot_unit_init_cfg_t cfg = {};
        cfg.unit_id = i == 0 ? ADC_UNIT_1 : ADC_UNIT_2;
        cfg.ulp_mode = ADC_ULP_MODE_DISABLE;
        esp_err_t err = adc_oneshot_new_unit(&cfg, &units[i]);
        if (err != ESP_OK) { cleanup(); return err; }
    }
    adc_oneshot_chan_cfg_t cfg = {};
    cfg.atten = ADC_ATTEN_DB_12;
    cfg.bitwidth = ADC_BITWIDTH_12;
    for (int i = 0; i < kCount; ++i) {
        esp_err_t err = adc_oneshot_config_channel(units[i == 4], channels[i], &cfg);
        if (err != ESP_OK) { cleanup(); return err; }
    }
    return ESP_OK;
}
esp_err_t read(Sample &sample) {
    if (!units[0] || !units[1]) return ESP_ERR_INVALID_STATE;
    Sample fresh = {};
    for (int i = 0; i < kCount; ++i) {
        esp_err_t err = adc_oneshot_read(units[i == 4], channels[i], &fresh[i]);
        if (err != ESP_OK) return err; // Never publish a partial sample.
    }
    sample = fresh;
    return ESP_OK;
}
}
