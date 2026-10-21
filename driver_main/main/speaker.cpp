#include "speaker.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace speaker {
namespace {
constexpr uart_port_t kUart = UART_NUM_1;
constexpr int kRx = 16, kTx = 17;
bool ready = false;
esp_err_t send(uint8_t command, uint16_t parameter) {
    if (!ready) return ESP_ERR_INVALID_STATE;
    uint8_t packet[10] = {0x7E, 0xFF, 0x06, command, 0,
        static_cast<uint8_t>(parameter >> 8), static_cast<uint8_t>(parameter), 0, 0, 0xEF};
    uint16_t sum = 0;
    for (int i = 1; i <= 6; ++i) sum += packet[i];
    const uint16_t checksum = static_cast<uint16_t>(0 - sum);
    packet[7] = static_cast<uint8_t>(checksum >> 8);
    packet[8] = static_cast<uint8_t>(checksum);
    if (uart_write_bytes(kUart, packet, sizeof(packet)) != sizeof(packet)) return ESP_FAIL;
    esp_err_t err = uart_wait_tx_done(kUart, pdMS_TO_TICKS(1000));
    vTaskDelay(pdMS_TO_TICKS(100)); // Give DFPlayer time to process each command.
    return err; // UART transport result only; no DFPlayer ACK or BUSY monitoring.
}
}
esp_err_t init(uint8_t volume) {
    if (volume > 30) return ESP_ERR_INVALID_ARG;
    if (ready) return set_volume(volume);
    uart_config_t cfg = {};
    cfg.baud_rate = 9600;
    cfg.data_bits = UART_DATA_8_BITS;
    cfg.parity = UART_PARITY_DISABLE;
    cfg.stop_bits = UART_STOP_BITS_1;
    cfg.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    cfg.source_clk = UART_SCLK_DEFAULT;
    esp_err_t err = uart_driver_install(kUart, 1024, 0, 0, nullptr, 0);
    if (err != ESP_OK) return err;
    err = uart_param_config(kUart, &cfg);
    if (err == ESP_OK) err = uart_set_pin(kUart, kTx, kRx, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) { uart_driver_delete(kUart); return err; }
    ready = true;
    vTaskDelay(pdMS_TO_TICKS(3000));
    err = send(0x09, 2); // Select microSD.
    if (err != ESP_OK) return err;
    vTaskDelay(pdMS_TO_TICKS(1000));
    err = stop();
    if (err != ESP_OK) return err;
    return set_volume(volume);
}
esp_err_t set_volume(uint8_t volume) {
    return volume <= 30 ? send(0x06, volume) : ESP_ERR_INVALID_ARG;
}
esp_err_t play_track(uint16_t track) {
    return track >= 1 && track <= 3000 ? send(0x12, track) : ESP_ERR_INVALID_ARG;
}
esp_err_t stop() { return send(0x16, 0); }
}
