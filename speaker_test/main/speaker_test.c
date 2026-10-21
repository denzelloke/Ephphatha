#include <stdio.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_err.h"

#define DFPLAYER_UART     UART_NUM_1
#define ESP_RX_PIN        16
#define ESP_TX_PIN        17

#define VOLUME            30
#define TRACK_INTERVAL_MS 1000

static int track = 1;

static void dfplayer_send_command(uint8_t command, uint16_t parameter)
{
    uint8_t packet[10] = {
        0x7E,
        0xFF,
        0x06,
        command,
        0x00,  // No acknowledgement requested
        (uint8_t)(parameter >> 8),
        (uint8_t)(parameter & 0xFF),
        0x00,
        0x00,
        0xEF
    };

    uint16_t checksum = (uint16_t)(
        0 - (packet[1] + packet[2] + packet[3] +
             packet[4] + packet[5] + packet[6])
    );

    packet[7] = (uint8_t)(checksum >> 8);
    packet[8] = (uint8_t)(checksum & 0xFF);

    uart_write_bytes(
        DFPLAYER_UART,
        (const char *)packet,
        sizeof(packet)
    );

    ESP_ERROR_CHECK(
        uart_wait_tx_done(DFPLAYER_UART, pdMS_TO_TICKS(1000))
    );
}

void app_main(void)
{
    // ESP-IDF initializes the console using menuconfig settings.
    vTaskDelay(pdMS_TO_TICKS(1000));

    printf("Speaker test starting\n");
    fflush(stdout);

    const uart_config_t uart_config = {
        .baud_rate = 9600,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    ESP_ERROR_CHECK(
        uart_driver_install(DFPLAYER_UART, 1024, 0, 0, NULL, 0)
    );

    ESP_ERROR_CHECK(
        uart_param_config(DFPLAYER_UART, &uart_config)
    );

    ESP_ERROR_CHECK(
        uart_set_pin(
            DFPLAYER_UART,
            ESP_TX_PIN,
            ESP_RX_PIN,
            UART_PIN_NO_CHANGE,
            UART_PIN_NO_CHANGE
        )
    );

    vTaskDelay(pdMS_TO_TICKS(3000));

    // Equivalent to player.outputDevice(DFPLAYER_DEVICE_SD).
    dfplayer_send_command(0x09, 2);
    vTaskDelay(pdMS_TO_TICKS(1000));

    // Equivalent to player.volume(VOLUME).
    dfplayer_send_command(0x06, VOLUME);
    vTaskDelay(pdMS_TO_TICKS(300));

    while (1)
    {
        // Equivalent to player.playMp3Folder(track).
        dfplayer_send_command(0x12, (uint16_t)track);

        printf(
            "Requested track %d: /mp3/%04u.mp3\n",
            track,
            (unsigned int)track
        );
        fflush(stdout);

        vTaskDelay(pdMS_TO_TICKS(TRACK_INTERVAL_MS));

        track++;

        if (track > 27) {
            track = 1;
        }
    }
}