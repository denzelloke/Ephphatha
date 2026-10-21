#include <cstdio>
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "flex_sensors.h"
#include "speaker.h"
#include "model_runner.h"
#include "gesture_gate.h"

namespace {
#if CONFIG_GLOVE_MODE_COLLECT
void collect() {
    ESP_ERROR_CHECK(flex::init());
    puts("READY");
    while (true) {
        const int command = getchar();
        if (command == EOF) { clearerr(stdin); vTaskDelay(pdMS_TO_TICKS(10)); continue; }
        if (command != 'c') continue;
        for (int row = 0; row < 3; ++row) {
            flex::Sample sample;
            const esp_err_t err = flex::read(sample);
            if (err == ESP_OK)
                printf("DATA,%d,%d,%d,%d,%d\n", sample[0], sample[1], sample[2], sample[3], sample[4]);
            else printf("ERROR,%s\n", esp_err_to_name(err));
            vTaskDelay(pdMS_TO_TICKS(300));
        }
        puts("DONE");
    }
}
#else
const char *TAG = "driver";
QueueHandle_t commands;
void console_task(void *) {
    // getchar may block: this task never owns sensors, inference or UART1.
    while (true) {
        int command = getchar();
        if (command == EOF) { clearerr(stdin); vTaskDelay(pdMS_TO_TICKS(10)); continue; }
        if (command == 's' || command == 'r' || command == 'p')
            xQueueSend(commands, &command, portMAX_DELAY);
    }
}
void start_console() {
    commands = xQueueCreate(16, sizeof(int));
    if (!commands) ESP_ERROR_CHECK(ESP_ERR_NO_MEM);
    if (xTaskCreate(console_task, "console", 3072, nullptr, 4, nullptr) != pdPASS)
        ESP_ERROR_CHECK(ESP_ERR_NO_MEM);
}
#endif
}

extern "C" void app_main(void) {
    setvbuf(stdout, nullptr, _IONBF, 0);
#if CONFIG_GLOVE_MODE_COLLECT
    collect();
#else
    ESP_ERROR_CHECK(speaker::init(CONFIG_GLOVE_VOLUME));
    start_console();
#if CONFIG_GLOVE_MODE_SPEAKER_TEST
    ESP_LOGI(TAG, "Speaker test: requesting track 1 once. p=play again, s=stop");
    ESP_ERROR_CHECK(speaker::play_track(1));
    while (true) {
        int command;
        if (xQueueReceive(commands, &command, portMAX_DELAY) == pdTRUE) {
            esp_err_t err = ESP_OK;
            if (command == 's') err = speaker::stop();
            if (command == 'p') err = speaker::play_track(1);
            if (err != ESP_OK) ESP_LOGE(TAG, "Speaker command failed: %s", esp_err_to_name(err));
        }
    }
#else
    ESP_ERROR_CHECK(flex::init());
    const bool model_ready = model_runner::init() == ESP_OK;
    ESP_LOGI(TAG, "Live mode: s=stop and pause, r=resume. Model ready=%s", model_ready ? "yes" : "no");
    GestureGate gate(CONFIG_GLOVE_CONFIDENCE_PERCENT / 100.0f,
                     CONFIG_GLOVE_STABLE_SAMPLES, CONFIG_GLOVE_COOLDOWN_MS);
    bool paused = false;
    unsigned iteration = 0;
    while (true) {
        int command;
        while (xQueueReceive(commands, &command, 0) == pdTRUE) {
            if (command == 's') {
                paused = true; gate.reset();
                esp_err_t err = speaker::stop();
                ESP_LOGI(TAG, "Paused. Stop command: %s", esp_err_to_name(err));
            } else if (command == 'r') {
                paused = false; gate.reset(); ESP_LOGI(TAG, "Resumed");
            }
        }
        if (!paused) {
            flex::Sample sample;
            esp_err_t err = flex::read(sample);
            if (err != ESP_OK) { gate.invalidate(); ESP_LOGW(TAG, "ADC: %s", esp_err_to_name(err)); }
            else {
                if (++iteration % 10 == 0)
                    ESP_LOGI(TAG, "RAW %d %d %d %d %d", sample[0], sample[1], sample[2], sample[3], sample[4]);
                if (model_ready) {
                    model_runner::Prediction prediction;
                    err = model_runner::predict(sample, prediction);
                    if (err != ESP_OK) {
                        gate.invalidate(); ESP_LOGW(TAG, "Inference: %s", esp_err_to_name(err));
                    } else {
                        int track = model_runner::track(prediction.class_index);
                        int64_t now = esp_timer_get_time() / 1000;
                        if (iteration % 10 == 0)
                            ESP_LOGI(TAG, "PRED label=%s confidence=%.3f", model_runner::label(prediction.class_index), prediction.confidence);
                        if (gate.update(prediction.class_index, prediction.confidence, track == 0, now)) {
                            err = speaker::play_track(static_cast<uint16_t>(track));
                            if (err == ESP_OK) {
                                gate.mark_spoken(prediction.class_index, esp_timer_get_time() / 1000);
                                ESP_LOGI(TAG, "PLAY label=%s confidence=%.3f track=%d",
                                    model_runner::label(prediction.class_index), prediction.confidence, track);
                            } else ESP_LOGW(TAG, "Speaker: %s", esp_err_to_name(err));
                        }
                    }
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_GLOVE_SAMPLE_MS));
    }
#endif
#endif
}
