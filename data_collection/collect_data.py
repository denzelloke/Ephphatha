import csv
import time
from datetime import datetime
from pathlib import Path

import serial


PORT = "/dev/ttyACM0"
BAUD_RATE = 115200

# A new filename for each session prevents overwriting previous data.
filename = Path(
    f"glove_data_{datetime.now():%Y%m%d_%H%M%S_%f}.csv"
)

with serial.Serial(
    PORT, BAUD_RATE, timeout=0.2, write_timeout=2
) as esp, filename.open("x", newline="") as file:

    writer = csv.writer(file)
    writer.writerow([
        "Label", "thumb_raw", "index_raw", "middle_raw", "pinky_raw"
    ])
    file.flush()

    # Allow startup time if opening the port resets the board.
    print("Listening for startup messages...")
    startup_deadline = time.monotonic() + 3

    while time.monotonic() < startup_deadline:
        startup_line = esp.readline().decode(
            "utf-8", errors="replace"
        ).strip()

        if startup_line:
            print("BOOT:", repr(startup_line))

    print(f"Saving to: {filename.resolve()}")

    try:
        while True:
            label = input("\nEnter a letter, or 'quit': ").strip().lower()

            if label == "quit":
                break

            if len(label) != 1 or label not in "abcdefghijklmnopqrstuvwxyz":
                print("Please enter one letter from a to z.")
                continue

            print(f"Prepare the gesture for '{label}'.")

            for seconds in (3, 2, 1):
                print(seconds, flush=True)
                time.sleep(1)

            # Discard old messages before requesting a fresh capture.
            esp.reset_input_buffer()
            print("Sending capture command")
            esp.write(b"c")
            esp.flush()

            readings = []
            capture_failed = False
            finished = False
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                line = esp.readline().decode(
                    "utf-8", errors="replace"
                ).strip()

                if line:
                    print("ESP received:", repr(line))

                if line == "DONE":
                    finished = True
                    break

                if line.startswith("ERROR,"):
                    print(line)
                    capture_failed = True

                elif line.startswith("DATA,"):
                    fields = line.split(",")

                    try:
                        values = [int(value) for value in fields[1:]]
                    except ValueError:
                        capture_failed = True
                        continue

                    if len(values) != 4 or not all(
                        0 <= value <= 4095 for value in values
                    ):
                        capture_failed = True
                        continue

                    readings.append(values)

            if not finished:
                print("Capture timed out. Nothing saved for this attempt.")
                print("Stopping to avoid mixing delayed readings into another label.")
                break

            if capture_failed or len(readings) != 3:
                print("Incomplete capture. Nothing saved; try the label again.")
                continue

            for values in readings:
                writer.writerow([label] + values)

            file.flush()
            print(f"Saved 3 rows labelled '{label}'.")

    except KeyboardInterrupt:
        print("\nCollection stopped.")

print(f"CSV closed: {filename.resolve()}")