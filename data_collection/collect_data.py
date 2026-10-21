"""Collect five flex sensors: a-z or ! (no gesture), Enter to capture.

Install dependency: python -m pip install pyserial
Run: python collect_data.py
Close Serial Monitor first. Firmware must reply DATA,... then DONE.
"""

import csv
import time
from datetime import datetime
from pathlib import Path

import serial

PORT = "COM7"  # Change if your ESP32 uses another port.
BAUD_RATE = 115200
CAPTURE_COMMAND = b"c"
CAPTURE_TIMEOUT = 5
EXPECTED_ROWS = 3


def main():
    filename = Path(f"glove_data_{datetime.now():%Y%m%d_%H%M%S_%f}.csv")

    try:
        with serial.Serial(
            PORT, BAUD_RATE, timeout=0.2, write_timeout=2
        ) as esp, filename.open("x", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "Label", "thumb_raw", "index_raw", "middle_raw",
                "ring_raw", "pinky_raw"])
            file.flush()

            # Drain startup messages silently, once per session.
            startup_deadline = time.monotonic() + 3
            while time.monotonic() < startup_deadline:
                esp.readline()

            print(f"Saving to: {filename.resolve()}")
            print("Hold your gesture before Enter and until the saved message.")

            while True:
                label = input(
                    "\nEnter a-z, '!' for no gesture, or 'quit': "
                ).strip().lower()
                if label == "quit":
                    break
                if len(label) != 1 or label not in "abcdefghijklmnopqrstuvwxyz!":
                    print("Enter one letter from a to z, '!', or 'quit'.")
                    continue

                # No countdown: request fresh readings immediately.
                esp.reset_input_buffer()
                esp.write(CAPTURE_COMMAND)
                esp.flush()

                readings = []
                capture_failed = False
                finished = False
                deadline = time.monotonic() + CAPTURE_TIMEOUT
                pending = bytearray()

                while time.monotonic() < deadline:
                    # Preserve partial lines across serial read timeouts.
                    pending.extend(esp.readline())
                    if b"\n" not in pending:
                        continue
                    raw, _, remainder = pending.partition(b"\n")
                    pending = bytearray(remainder)
                    line = raw.decode("utf-8", errors="replace").strip()

                    if line == "DONE":
                        finished = True
                        break
                    if line.startswith("ERROR,"):
                        print(line)
                        capture_failed = True
                    elif line.startswith("DATA,"):
                        try:
                            values = [int(value) for value in line.split(",")[1:]]
                        except ValueError:
                            capture_failed = True
                            continue
                        if len(values) != 5 or not all(0 <= v <= 4095 for v in values):
                            capture_failed = True
                            continue
                        readings.append(values)
                    # Ignore firmware debug and other non-data messages.

                if not finished:
                    print("Capture timed out. Nothing saved for this attempt.")
                    print("Stopping to avoid mixing delayed readings into another label.")
                    break
                if capture_failed or len(readings) != EXPECTED_ROWS:
                    print(f"Incomplete capture: got {len(readings)} valid rows. Nothing saved; try again.")
                    continue

                for values in readings:
                    writer.writerow([label] + values)
                file.flush()
                description = "no gesture (!)" if label == "!" else label
                print(f"Saved {EXPECTED_ROWS} rows labelled '{description}'.")

    except (KeyboardInterrupt, EOFError):
        print("\nCollection stopped.")
    except serial.SerialException as error:
        print(f"Serial communication failed: {error}")
    except OSError as error:
        print(f"File or device error: {error}")
    finally:
        if filename.exists():
            print(f"CSV closed: {filename.resolve()}")


if __name__ == "__main__":
    main()
