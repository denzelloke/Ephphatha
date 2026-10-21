# Flex Voice: ESP32-S3 flex sensors -> TFLite Micro -> DFPlayer

This project combines your five-sensor ADC code and UART DFPlayer code into separate C++ modules. It is native ESP-IDF, not Arduino. Training happens separately on your PC. Inference happens locally on the ESP32-S3; there is no server or Wi-Fi requirement.

**Start here:** use ESP-IDF **5.5.x** and an **ESP32-S3**. The manifest deliberately pins `espressif/esp-tflite-micro` to `1.3.5` and constrains IDF to the 5.5 release family. This is a chosen dependency baseline, not a claim that it is the newest version. If you use another IDF version, select 5.5.x for this project first. Do not simply remove the constraints and assume compatibility.

No trained model was supplied. The included `model_data.h` is an explicit placeholder. Collection and speaker testing do not need a model; live mode prints raw readings and keeps automatic playback disabled until a valid model initializes.

## 1. What each file does

| File | Purpose |
|---|---|
| `CMakeLists.txt` | Root ESP-IDF project definition |
| `sdkconfig.defaults` | Native USB console, 12 KiB main task stack, large single-app partition |
| `main/CMakeLists.txt` | Lists the four compiled `.cpp` files and IDF dependencies |
| `main/idf_component.yml` | Downloads the pinned TFLite Micro component automatically |
| `main/Kconfig.projbuild` | Adds the Flex Voice menu and operating modes |
| `main/app_main.cpp` | Main driver: coordinates sensing, inference and audio |
| `main/flex_sensors.h/.cpp` | Reads five raw ADC values in the original finger order |
| `main/speaker.h/.cpp` | Initializes UART1 and sends DFPlayer play/stop/volume commands |
| `main/model_runner.h/.cpp` | Preprocesses readings, runs TFLite Micro, returns class and confidence |
| `main/gesture_gate.h` | Stability, repeat prevention and cooldown logic |
| `main/model/model_settings.h` | Input preprocessing constants |
| `main/model/model_data.h` | Placeholder now; model bytes and labels after conversion |
| `labels.txt` | Output class order; must match your training encoder exactly |
| `tools/collect_data.py` | Your original collector, copied unchanged |
| `tools/tflite_to_header.py` | Converts model bytes and label order to a C++ header |
| `tools/inspect_model.py` | Optional desktop shape/type/operator inspection using TensorFlow |
| `tools/requirements.txt` | Dependency for the collector only |
| `tests/` | Host checks for conversion and gesture decision logic |

The modules are source/header pairs inside the `main` component. They do not need separate ESP-IDF components. Headers declare the functions other modules can use; `.cpp` files implement those functions. Only `app_main.cpp` defines `app_main()`.

## 2. Wiring: retain your working connections

| Function | ESP32-S3 pin | ADC / connection |
|---|---|---|
| Thumb divider output | GPIO4 | ADC1 channel 3 |
| Index divider output | GPIO5 | ADC1 channel 4 |
| Middle divider output | GPIO6 | ADC1 channel 5 |
| Ring divider output | GPIO7 | ADC1 channel 6 |
| Pinky divider output | GPIO15 | ADC2 channel 4 |
| DFPlayer TX | GPIO16 | ESP UART1 RX |
| DFPlayer RX | GPIO17 through your 1 kOhm resistor | ESP UART1 TX |
| Ground | GND | Common ground with sensor dividers and DFPlayer |

Keep the flex sensor voltage dividers and supply arrangement you already tested; sensor GPIOs must remain within the ESP32-S3's allowed input voltage. The DFPlayer drives the speaker through its speaker terminals, not through an ESP GPIO. Use your working DFPlayer supply. UART1 is 9600 baud. Console/collection is 115200 baud.

The pinky uses ADC2, which is also used by Wi-Fi. This project does not initialize Wi-Fi. If you add Wi-Fi later, handle ADC contention or consider moving that sensor to an available ADC1 pin and update the channel mapping. An ADC read failure skips the entire sample.

## 3. Put the files into a fresh template in VS Code

1. Extract the ZIP. Open the `flex_voice` directory, the one containing the ROOT `CMakeLists.txt`.
2. You can use this directory directly as your ESP-IDF project; creating a second template is unnecessary.
3. If you already created an empty template, copy the **contents** of `flex_voice` into its root. Replace its root `CMakeLists.txt` and its entire `main` directory. Remove the original template's `main.c`, `hello_world_main.c`, or any other old application source. Do not put the project inside the template's `main` folder. Keep your existing `.vscode` configuration if useful.
4. In VS Code, open the Command Palette and run **ESP-IDF: Open ESP-IDF Terminal**. Use the extension's environment/version selection if necessary to select IDF 5.5.x. Run `idf.py --version` to check it.
5. In that terminal, from the project root, run:

   ```powershell
   idf.py set-target esp32s3
   idf.py menuconfig
   ```

6. Open **Flex Voice -> Operating mode**. Initially choose **Collect labelled data (Python collector)**. Save and exit.
7. Check **Component config -> ESP System Settings -> Channel for console output** and choose **USB Serial/JTAG Controller** if using the board's native USB socket. If your cable is plugged into the board's separate USB-to-UART bridge socket, choose the default UART console instead. These are alternative USB sockets on some boards; match the actual socket you use.
8. If the template already had `sdkconfig`, defaults may not override existing settings. In menuconfig also set **Main task stack size** to **12288**, and **Partition Table -> Partition Table** to **Single factory app (large), no OTA**. Menu names can vary slightly; menuconfig search can find `ESP_MAIN_TASK_STACK_SIZE`, `PARTITION_TABLE_SINGLE_APP_LARGE`, and `ESP_CONSOLE_USB_SERIAL_JTAG`.
9. Build:

   ```powershell
   idf.py build
   ```

   Internet is needed on the first build so ESP-IDF Component Manager can download TFLite Micro and its dependencies. Do not manually create or edit `managed_components`. Keep the generated `dependencies.lock` when later versioning the project.

10. Find the board's current port in Windows Device Manager. Substitute it for COM8:

    ```powershell
    idf.py -p COM8 flash monitor
    ```

Native USB Serial/JTAG supports serial flashing through `idf.py flash`. If the VS Code extension asks for a flash method, use **UART** for this serial/esptool workflow, including the native USB COM port. The JTAG/OpenOCD flash workflow is separate and unnecessary here.

If no port appears, check the USB data cable/socket. If necessary, hold BOOT while tapping RESET, release BOOT, and recheck the port. Close other monitors or Python collectors before flashing. Exit IDF Monitor with **Ctrl+]**; closing the monitor alone does not stop running firmware.

## 4. Collect data, as before

The default firmware waits for `c`, then replies with three `DATA,thumb,index,middle,ring,pinky` lines 300 ms apart, followed by `DONE`. Each row is a separate five-feature example. It does NOT combine three rows into a 15-feature example.

1. Flash collection mode and confirm `READY` in the monitor.
2. Exit the monitor with Ctrl+].
3. Edit `PORT = "COM8"` in `tools/collect_data.py` to match your board.
4. Run:

   ```powershell
   python -m pip install -r tools/requirements.txt
   python tools/collect_data.py
   ```

5. Hold a gesture, enter its lowercase label, and press Enter. Hold it until the saved message. Use `!` for no gesture and `quit` to exit. CSV files are written in the directory from which you launched the script.

Collection mode does not initialize the DFPlayer or run the model. A separately powered DFPlayer might finish a previously playing track; power-cycle it or use speaker-test `s` if needed. Your existing collector and CSV columns remain compatible.

## 5. Test audio before adding a model

Prepare the DFPlayer microSD using your working format, with a folder called `mp3` at the root. This project maps **letters to track numbers**, independently of model class order:

| Label | Track | Filename |
|---|---:|---|
| `!` (no gesture) | 0 (silent) | No file needed |
| `a` | 1 | `/mp3/0001.mp3` |
| `b` | 2 | `/mp3/0002.mp3` |
| `c` | 3 | `/mp3/0003.mp3` |
| ... | ... | ... |
| `z` | 26 | `/mp3/0026.mp3` |

If your existing recordings use a different order, rename them to this order or change the track-generation rule in `tflite_to_header.py`. Track 27 is unused by default. Do not assume your current files already match.

Run `idf.py menuconfig`, choose **Flex Voice -> Operating mode -> Speaker test**, save, then `idf.py -p COM8 flash monitor`. Track 1 plays once after the DFPlayer startup delay. In the monitor, type `p` to request it again or `s` to stop. Press Enter too if your terminal buffers input until Enter. Volume defaults to 20; change it under Flex Voice (range 0..30).

The driver reports successful UART transmission, not verified playback. It does not parse DFPlayer acknowledgments or use the BUSY pin. Missing files, card issues, or an unpowered module therefore may not produce an ESP error.

## 6. Train a compatible model separately

Use the following contract when building your model:

| Item | Required convention |
|---|---|
| Input tensors | One tensor, shape `[1, 5]` at inference |
| Feature order | thumb, index, middle, ring, pinky |
| Default preprocessing | Each raw ADC value divided by 4095.0 |
| Output tensors | One tensor, shape `[1, N]` |
| Output meaning | Softmax probabilities for N classes |
| Class labels | Unique lowercase letters and `!`; 2..27 classes total |
| Class ordering | Exact output-index order written to `labels.txt` |
| Input/output tensor types | float32, int8, or uint8; integer I/O uses per-tensor quantization |
| Suitable starting architecture | Input(5), small Dense/ReLU layers, Dense(N, softmax) |

Default example: train with 27 classes in `!,a,b,...,z` order. But do not assume your training library uses this order. Export its actual encoder order to `labels.txt`, one label per line. A model trained on only `!,a,b,c` needs four lines and a `[1,4]` output; untrained letters must not remain in that file.

In Python, the default preprocessing is:

```python
feature_columns = ["thumb_raw", "index_raw", "middle_raw", "ring_raw", "pinky_raw"]
X = df[feature_columns].to_numpy(dtype="float32") / 4095.0
```

If your trained model expects raw counts, set all five scales to `1.0f` in `main/model/model_settings.h`. For standardized features `(raw - mean) / std`, set offsets to training means and scales to inverse training standard deviations. Never normalize twice. The firmware does not average readings or apply smoothing before inference, matching your original raw samples.

Float32 is the simplest initial export. If you choose integer quantization, use a representative dataset with the same preprocessing. The runtime applies `round(real / scale) + zero_point` on input and `(quantized - zero_point) * scale` on output using the model's tensor metadata. This is separate from raw ADC normalization.

Registered model operators: FULLY_CONNECTED, RELU, SOFTMAX, RESHAPE, QUANTIZE, DEQUANTIZE, ADD, MUL. A `.tflite` file is not automatically compatible with TFLite Micro: unsupported operators, operator versions, custom/Flex ops, dynamic behavior, or excessive RAM may prevent initialization. If needed, adapt the model or add supported operator registrations and increase the resolver capacity in `model_runner.cpp`.

Five bend sensors measure finger flexion, not hand orientation, finger separation, or motion trajectories. Some signs may produce indistinguishable inputs. This is a static gesture-classification pipeline, not a guarantee of recognizing every signed letter. Train and evaluate the gestures the hardware can distinguish. Include realistic no-gesture and transition examples. Keep related captures/session data together when splitting train and test data, so almost-identical rows from one capture do not inflate test accuracy.

## 7. Convert your .tflite to .h and install it

1. Copy your trusted, trained file into the project root as `model.tflite`.
2. Update `labels.txt` to exactly match the model output order.
3. Optionally, from your TensorFlow training environment:

   ```powershell
   python tools/inspect_model.py model.tflite --labels labels.txt
   ```

   This checks I/O shape/type and prints the model's operators. It needs TensorFlow and NumPy in that training environment. Neither TensorFlow nor this optional step is required for byte-to-header conversion. It does not test embedded execution or model accuracy.

4. From the project root:

   ```powershell
   python tools/tflite_to_header.py model.tflite --labels labels.txt
   ```

   This replaces `main/model/model_data.h` with aligned model bytes, labels and track mappings. It requires only Python's standard library. It does **not** retrain, quantize, or translate the model into neural-network C code. TFLite Micro interprets the embedded flatbuffer.

5. Choose **Flex Voice -> Operating mode -> Live sensors -> model -> speaker** in `idf.py menuconfig`.
6. Rebuild and flash:

   ```powershell
   idf.py -p COM8 flash monitor
   ```

   `flash` builds as needed. Merely copying a new `.tflite` to your PC or the DFPlayer card does not update the ESP. Repeat conversion, build and flash after each model change. The `.tflite` is embedded in ESP firmware; only MP3 files belong on the DFPlayer card.

## 8. Understand the main loop

The driver calls `flex::read(sample)`, then `model_runner::predict(sample, prediction)`. The model module preprocesses all five inputs, invokes TFLite Micro, and returns the highest-scoring class index plus confidence. The driver looks up the corresponding track and asks `GestureGate` whether it should play. Finally `speaker::play_track(track)` sends a UART command; the DFPlayer decodes and plays the MP3 independently.

Defaults: 100 ms delay per loop (actual interval includes processing), at least 80% confidence, three consecutive predictions of the same class, and at least 1500 ms between audio requests. All are menuconfig settings.

- Holding a gesture plays it once.
- A different stable gesture can play after the cooldown.
- To repeat the same gesture, first hold a confidently recognized `!` long enough to pass the same stability check, then make the gesture again.
- Low confidence or an ADC/inference error resets the stability counter but does not rearm a held gesture.
- `!` is silent and rearms repetition; it does not cut off an existing recording.
- Type `s` to stop current audio **and pause the live pipeline**; `r` resumes it and clears the gate history. This lets you deliberately repeat a gesture too.
- New accepted gestures can interrupt an unfinished track. The cooldown is not a playback-completion detector. Increase it for longer clips; fully queued playback would need additional policy and completion feedback.

Example log format (illustrative, not a measured result):

```text
model: Model ready, classes=27, arena used=... bytes
driver: RAW 1200 1800 1700 1600 1400
driver: PRED label=a confidence=0.950
driver: PLAY label=a confidence=0.950 track=1
```

The console reader is a separate FreeRTOS task so waiting for keyboard input cannot block sampling. All sensor/model/speaker work belongs to the main task; there are no concurrent DFPlayer writers.

## 9. Troubleshooting and verification limits

| Symptom | Check |
|---|---|
| Port busy / COM8 does not exist | Current Device Manager port; close collector and other monitors |
| Flash succeeds but no READY/logs | Console setting matches USB socket; reset board; correct port |
| Collector timeout | Collection mode, same COM port, correct USB console input; no competing monitor |
| Multiple definitions of app_main | Remove template and old test application source files |
| No model installed | Run converter, then rebuild and reflash |
| Wrong letter audio | Exact training label order, generated mapping, MP3 numbering |
| AllocateTensors fails | Read preceding TFLM diagnostics: ops/versions first, then arena RAM |
| Arena too small | Increase Flex Voice tensor arena (for example 64 to 96 KiB), while checking available internal RAM |
| Unsupported shape/type | Use fixed `[1,5]` input and `[1,N]` output; supported I/O dtype |
| Invalid inference response | Output must be probabilities; check export/preprocessing/quantization |
| Model predicts badly | Training feature order/scaling, training-data coverage, sensor wiring/calibration |
| Correct PLAY log but no audio | Power, common ground, UART wiring, card and exact filenames |
| Playback keeps interrupting | Increase cooldown; stable different labels can start new tracks |
| Linker reports firmware too large | Check large app partition and actual board flash capacity; reduce model size if needed |
| Component dependency/version error | Use the specified IDF 5.5.x environment; first build needs registry access |

The 64 KiB arena is a starting allocation for a small dense network, not a size guarantee for your future model. No PSRAM is assumed. The large single-app partition is intended for a typical ESP32-S3 development board with at least 4 MB flash; check your board before changing physical flash-size settings.

Host checks included: byte-exact header embedding, label-order/track mapping, invalid conversion inputs, gesture stability, neutral rearming, repeat suppression and cooldown. These do not substitute for an ESP-IDF build or on-board testing. The generation environment had no ESP-IDF toolchain, connected ESP32-S3/DFPlayer, or trained `.tflite`; firmware compilation, actual model inference and hardware behavior could not be verified here.

To rerun host checks where Python and a C++ compiler are available:

```text
python -m unittest discover -s tests -p "test_*.py"
g++ -std=c++17 -Wall -Wextra -Werror -Imain tests/test_gate.cpp -o gate_test
./gate_test
```

## Official references used

- ESP-IDF ADC oneshot API: https://docs.espressif.com/projects/esp-idf/en/release-v5.5/esp32s3/api-reference/peripherals/adc_oneshot.html
- Native USB console and flashing: https://docs.espressif.com/projects/esp-idf/en/release-v5.5/esp32s3/api-guides/usb-serial-jtag-console.html
- ESP-IDF Component Manager: https://docs.espressif.com/projects/idf-component-manager/
- Espressif TFLite Micro: https://github.com/espressif/esp-tflite-micro
- Pinned component: https://components.espressif.com/components/espressif/esp-tflite-micro/versions/1.3.5
- DFRobot DFPlayer library/protocol: https://github.com/DFRobot/DFRobotDFPlayerMini

Sensor and DFPlayer command sequences were adapted from the three files you supplied. The collector is preserved unchanged.
