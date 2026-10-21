idf_component_register(
    SRCS "app_main.cpp" "flex_sensors.cpp" "speaker.cpp" "model_runner.cpp"
    INCLUDE_DIRS "." "model"
    REQUIRES esp_adc esp_driver_uart esp_timer
)
target_compile_features(${COMPONENT_LIB} PUBLIC cxx_std_17)
