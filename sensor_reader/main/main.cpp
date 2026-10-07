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
            ADC_CHANNEL_0,
            &channel_config));

    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc_handle,
            ADC_CHANNEL_1,
            &channel_config));

    ESP_ERROR_CHECK(
        adc_oneshot_config_channel(
            adc_handle,
            ADC_CHANNEL_2,
            &channel_config));

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

    // 6a. create bus config for I2C bus
    i2c_master_bus_config_t bus_config = {};
    bus_config.i2c_port = I2C_NUM_0; // i2c controller 0 (diff from gpio)
    bus_config.sda_io_num = GPIO_NUM_8;
    bus_config.scl_io_num = GPIO_NUM_9;
    bus_config.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_config.glitch_ignore_cnt = 7;
    bus_config.flags.enable_internal_pullup = true;

    // 6b. create bus handle for I2C bus
    i2c_master_bus_handle_t bus_handle;

    // 6c. create I2C bus
    ESP_ERROR_CHECK(
        i2c_new_master_bus(&bus_config, &bus_handle));

    // 7a. config I2C device
    // refer to MPU6050 datasheet - "MPU6050.pdf"
    i2c_device_config_t i2c_device_config = {};
    i2c_device_config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    i2c_device_config.device_address = 0x68;  // AD0
    i2c_device_config.scl_speed_hz = 100000; // 40kHz is max

    // 7b. create master device handle
    i2c_master_dev_handle_t i2c_device_handle;

    // 7c. create device handle for mpu
    ESP_ERROR_CHECK(
        i2c_master_bus_add_device(bus_handle, &i2c_device_config, &i2c_device_handle));

    // 8. writes a register address, then reads its contents
    uint8_t register_address = 0x75; // WHO_AM_I
    uint8_t device_id = 0;

    esp_err_t status = i2c_master_transmit_receive(
        i2c_device_handle,
        &register_address,
        sizeof(register_address),
        &device_id,
        sizeof(device_id),
        100);

    if (status == ESP_OK)
    {
        printf("MPU6050 identity: 0x%02X\n", (unsigned int)device_id);
    }
    else
    {
        printf("MPU6050 read failed: %s\n", esp_err_to_name(status));
    }

    while (1)
    {
        int raw_thumb, raw_index, raw_middle, raw_ring, raw_pinky = 0;

        // read and print thumb flex sensor
        esp_err_t status_thumb = adc_oneshot_read(
            adc_handle,
            ADC_CHANNEL_0,
            &raw_thumb);
        if (status_thumb == ESP_OK)
        {
            printf("Thumb raw:  %d\n", raw_thumb);
        }
        else
        {
            printf("Thumb ADC error: %s\n", esp_err_to_name(status_thumb));
        }

        // read and print index flex sensor
        esp_err_t status_index = adc_oneshot_read(
            adc_handle,
            ADC_CHANNEL_1,
            &raw_index);
        if (status_index == ESP_OK)
        {
            printf("Index raw:  %d\n", raw_index);
        }
        else
        {
            printf("Index ADC error: %s\n", esp_err_to_name(status_index));
        }

        // read and print middle flex sensor
        esp_err_t status_middle = adc_oneshot_read(
            adc_handle,
            ADC_CHANNEL_2,
            &raw_middle);
        if (status_middle == ESP_OK)
        {
            printf("Middle raw: %d\n", raw_middle);
        }
        else
        {
            printf("Middle ADC error: %s\n", esp_err_to_name(status_middle));
        }

        // read and print ring flex sensor
        esp_err_t status_ring = adc_oneshot_read(
            adc_handle,
            ADC_CHANNEL_3,
            &raw_ring);
        if (status_ring == ESP_OK)
        {
            printf("Ring raw:   %d\n", raw_ring);
        }
        else
        {
            printf("Ring ADC error: %s\n", esp_err_to_name(status_ring));
        }

        // read and print pinky flex sensor
        esp_err_t status_pinky = adc_oneshot_read(
            adc_handle,
            ADC_CHANNEL_4,
            &raw_pinky);
        if (status_pinky == ESP_OK)
        {
            printf("Pinky raw:  %d\n\n\n", raw_pinky);
        }
        else
        {
            printf("Pinky ADC error: %s\n", esp_err_to_name(status_pinky));
        }

        // Pause for 50 ms before the next reading.
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}