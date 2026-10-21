#include <stdio.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "esp_adc/adc_oneshot.h"

extern "C" void app_main(void)
{
    // Create handles for both ADC units.
    adc_oneshot_unit_handle_t adc1_handle;
    adc_oneshot_unit_handle_t adc2_handle;

    adc_oneshot_unit_init_cfg_t adc1_config = {};
    adc1_config.unit_id = ADC_UNIT_1;
    adc1_config.ulp_mode = ADC_ULP_MODE_DISABLE;

    adc_oneshot_unit_init_cfg_t adc2_config = {};
    adc2_config.unit_id = ADC_UNIT_2;
    adc2_config.ulp_mode = ADC_ULP_MODE_DISABLE;

    ESP_ERROR_CHECK(
        adc_oneshot_new_unit(&adc1_config, &adc1_handle)
    );

    ESP_ERROR_CHECK(
        adc_oneshot_new_unit(&adc2_config, &adc2_handle)
    );

    // Use the same settings for all five fingers.
    adc_oneshot_chan_cfg_t channel_config = {};
    channel_config.atten = ADC_ATTEN_DB_12;
    channel_config.bitwidth = ADC_BITWIDTH_12;

    // Thumb: GPIO4, ADC1 channel 3.
    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc1_handle, ADC_CHANNEL_3, &channel_config
        )
    );

    // Index: GPIO5, ADC1 channel 4.
    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc1_handle, ADC_CHANNEL_4, &channel_config
        )
    );

    // Middle: GPIO6, ADC1 channel 5.
    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc1_handle, ADC_CHANNEL_5, &channel_config
        )
    );

    // Ring: GPIO7, ADC1 channel 6.
    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc1_handle, ADC_CHANNEL_6, &channel_config
        )
    );

    // Pinky: GPIO15, ADC2 channel 4.
    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc2_handle, ADC_CHANNEL_4, &channel_config
        )
    );

    printf("READY\n");
    fflush(stdout);

    while (1)
    {
        int command = getchar();

        if (command == EOF)
        {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        printf("RX,%d\n", command);
        fflush(stdout);

        if (command != 'c')
        {
            continue;
        }

        for (int sample = 0; sample < 3; sample++)
        {
            int raw_thumb = 0;
            int raw_index = 0;
            int raw_middle = 0;
            int raw_ring = 0;
            int raw_pinky = 0;

            esp_err_t status_thumb = adc_oneshot_read(
                adc1_handle, ADC_CHANNEL_3, &raw_thumb
            );

            esp_err_t status_index = adc_oneshot_read(
                adc1_handle, ADC_CHANNEL_4, &raw_index
            );

            esp_err_t status_middle = adc_oneshot_read(
                adc1_handle, ADC_CHANNEL_5, &raw_middle
            );

            esp_err_t status_ring = adc_oneshot_read(
                adc1_handle, ADC_CHANNEL_6, &raw_ring
            );

            esp_err_t status_pinky = adc_oneshot_read(
                adc2_handle, ADC_CHANNEL_4, &raw_pinky
            );

            if (status_thumb == ESP_OK &&
                status_index == ESP_OK &&
                status_middle == ESP_OK &&
                status_ring == ESP_OK &&
                status_pinky == ESP_OK)
            {
                printf(
                    "DATA,%d,%d,%d,%d,%d\n",
                    raw_thumb,
                    raw_index,
                    raw_middle,
                    raw_ring,
                    raw_pinky
                );
            }
            else
            {
                printf("ERROR,ADC oneshot failed\n");
            }

            // Push buffered output to the serial connection.
            fflush(stdout);

            // Pause for 300 ms before the next reading.
            vTaskDelay(pdMS_TO_TICKS(300));
        }

        printf("DONE\n");
        fflush(stdout);
    }
}