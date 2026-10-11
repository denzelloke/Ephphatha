#include <stdio.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "esp_adc/adc_oneshot.h"
#include "driver/i2c_master.h"

extern "C" void app_main(void)
{
    // 1. create adc handle
    adc_oneshot_unit_handle_t adc_handle;

    // 2. configure adc unit - the actual thing doing the converting
    adc_oneshot_unit_init_cfg_t unit_config = {};
    unit_config.unit_id = ADC_UNIT_1;
    unit_config.ulp_mode = ADC_ULP_MODE_DISABLE;
    // c convention - {} initialises struct w all with members filled w zeroes
    // ulp = ultra low power mode: sleeps a lot ig
    // clk_src implicitly set to 0. driver will choose its defualt clk src.

    // 3. initialise adc unit handle
    ESP_ERROR_CHECK(
        adc_oneshot_new_unit(&unit_config, &adc_handle));
    // adc unit will now be interfaced with using adc_handle
    // output is either ESP_OK or ESP_ERROR_CHECK

    // 4. configure adc channel - can have multiple channels into the adc unit
    adc_oneshot_chan_cfg_t channel_config = {};
    channel_config.atten = ADC_ATTEN_DB_12;
    channel_config.bitwidth = ADC_BITWIDTH_DEFAULT;
    // attenuation scales down input voltage so we can measure larger input voltages.
    // Vafter = Vin * 10^-(12/20) = Vin * 0.251
    // max bitwidth is 12 bits, which is also the default, so 0-4095.

    // 5. initialise adc channel(s)
    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc_handle,
            ADC_CHANNEL_3,
            &channel_config));

    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc_handle,
            ADC_CHANNEL_4,
            &channel_config));

    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc_handle,
            ADC_CHANNEL_5,
            &channel_config));

    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc_handle,
            ADC_CHANNEL_6,
            &channel_config));

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
            int raw_pinky = 0;

            // read thumb flex sensor
            esp_err_t status_thumb = adc_oneshot_read(
                adc_handle,
                ADC_CHANNEL_3,
                &raw_thumb);

            // read index flex sensor
            esp_err_t status_index = adc_oneshot_read(
                adc_handle,
                ADC_CHANNEL_4,
                &raw_index);

            // read middle flex sensor
            esp_err_t status_middle = adc_oneshot_read(
                adc_handle,
                ADC_CHANNEL_5,
                &raw_middle);

            // read pinky flex sensor
            esp_err_t status_pinky = adc_oneshot_read(
                adc_handle,
                ADC_CHANNEL_6,
                &raw_pinky);

            // if all status ok, print values.
            if (status_thumb == ESP_OK && status_index == ESP_OK && status_middle == ESP_OK && status_pinky == ESP_OK)
            {
                printf("DATA,%d,%d,%d,%d\n", raw_thumb, raw_index, raw_middle, raw_pinky);
            }
            else
            {
                printf("ERROR,ADC oneshot failed\n");
            }

            // holup what is this
            fflush(stdout);

            

            // Pause for 50 ms before the next reading.
            vTaskDelay(pdMS_TO_TICKS(300));
        }

        printf("DONE\n");
        fflush(stdout);
    }
}