# How to use

## step 0:
- make ur own model (自己搞定)
- turn it into a .tflite file somehow

## step 1:
- python3 export_model_header.py path/to/new_model.tflite
- the above command will overwrite the current model.h with the contents of ur .tflite file

## step 2:
- flash test_pipeline.ino into ur ESP32 board using the arduino IDE
- this step is susceptible to errors due to ESP32 configs.
- Astra will assist you

## step 3:
- if flash is successful, the script basically takes inputs from test_data.h and runs and inference on it using the model you trained, which now resides in model.h
- it will print out your answer, the correct answer, and the inference time required.
- generally, first inference will take longer as the board is doing some memory intialisation or smth idk
- we are looking for no false positives!
- false negatives are allowed, but ofc try to keep it down.
