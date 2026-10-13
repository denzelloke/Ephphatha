import csv
import time
from datetime import datetime
from pathlib import Path

import serial


PORT = "COM8"  # CHANGE to your ESP's actual COM port.
BAUD_RATE = 115200
CAPTURE_COMMAND = b"c"
CAPTURE_TIMEOUT = 5


def debug(message):
    print(f"[DEBUG {time.monotonic():.3f}] {message}", flush=True)


filename = Path(
    f"glove_data_{datetime.now():%Y%m%d_%H%M%S_%f}.csv"
)

debug(f"Opening {PORT} at {BAUD_RATE} baud")

with serial.Serial(
    PORT, BAUD_RATE, timeout=0.2, write_timeout=2
) as esp, filename.open("x", newline="") as file:

    debug(
        f"Port opened: name={esp.name}, "
        f"is_open={esp.is_open}, baudrate={esp.baudrate}"
    )
    debug(f"Serial settings: {esp.get_settings()}")
    debug(f"DTR={esp.dtr}, RTS={esp.rts}")

    writer = csv.writer(file)
    writer.writerow([
        "Label", "thumb_raw", "index_raw", "middle_raw", "pinky_raw"
    ])
    file.flush()

    print("Listening for startup messages...")
    startup_deadline = time.monotonic() + 3
    startup_bytes = 0

    while time.monotonic() < startup_deadline:
        raw = esp.readline()

        if raw:
            startup_bytes += len(raw)
            debug(f"BOOT RAW: {raw!r}")
            print("BOOT TEXT:", raw.decode("utf-8", errors="replace").strip())

    debug(f"Startup received {startup_bytes} bytes")

    if startup_bytes == 0:
        debug(
            "No startup bytes observed. This alone does not prove failure: "
            "the firmware might not print startup messages."
        )

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

            # Show queued data before discarding it.
            pending = esp.in_waiting
            debug(f"Bytes waiting before capture: {pending}")

            if pending:
                stale = esp.read(pending)
                debug(f"Discarding queued bytes: {stale!r}")

            esp.reset_input_buffer()

            debug(
                f"TX command: {CAPTURE_COMMAND!r}, "
                f"hex={CAPTURE_COMMAND.hex(' ')}"
            )

            written = esp.write(CAPTURE_COMMAND)
            esp.flush()

            debug(f"Write returned: {written} bytes")
            debug(
                "This confirms a local serial write, "
                "not that the ESP firmware handled the command."
            )

            readings = []
            capture_failed = False
            finished = False

            received_bytes = 0
            empty_reads = 0
            unexpected_lines = 0

            started = time.monotonic()
            deadline = started + CAPTURE_TIMEOUT
            next_status = started + 1

            while time.monotonic() < deadline:
                raw = esp.readline()
                now = time.monotonic()

                if not raw:
                    empty_reads += 1

                    if now >= next_status:
                        debug(
                            f"Waiting: elapsed={now - started:.1f}s, "
                            f"received_bytes={received_bytes}, "
                            f"valid_rows={len(readings)}, "
                            f"in_waiting={esp.in_waiting}"
                        )
                        next_status = now + 1

                    continue

                received_bytes += len(raw)

                # repr exposes newlines, invalid bytes, and partial messages.
                debug(f"RX RAW (+{now - started:.3f}s): {raw!r}")

                if not raw.endswith(b"\n"):
                    debug(
                        "RX has no trailing newline. It may be a partial "
                        "message or the firmware may omit line endings."
                    )

                line = raw.decode("utf-8", errors="replace").strip()
                debug(f"RX TEXT: {line!r}")

                if "\ufffd" in line:
                    debug(
                        "Invalid UTF-8 bytes detected. Check baud rate "
                        "and whether the ESP sends text or binary data."
                    )

                if not line:
                    debug("Received only whitespace or line endings")
                    continue

                if line == "DONE":
                    debug("Recognised DONE")
                    finished = True
                    break

                if line.startswith("ERROR,"):
                    debug(f"ESP reported an error: {line}")
                    capture_failed = True

                elif line.startswith("DATA,"):
                    fields = line.split(",")
                    debug(f"DATA fields: {fields!r}")

                    try:
                        values = [int(value) for value in fields[1:]]
                    except ValueError:
                        debug("Rejected DATA: one or more values are not integers")
                        capture_failed = True
                        continue

                    if len(values) != 4:
                        debug(
                            f"Rejected DATA: expected 4 sensor values, "
                            f"got {len(values)}"
                        )
                        capture_failed = True
                        continue

                    if not all(0 <= value <= 4095 for value in values):
                        debug(f"Rejected DATA: values outside 0–4095: {values}")
                        capture_failed = True
                        continue

                    readings.append(values)
                    debug(f"Accepted row {len(readings)}: {values}")

                else:
                    unexpected_lines += 1
                    debug(
                        "Unrecognised message: expected DATA,..., "
                        "ERROR,..., or DONE"
                    )

            debug(
                f"Capture summary: received_bytes={received_bytes}, "
                f"empty_reads={empty_reads}, "
                f"unexpected_lines={unexpected_lines}, "
                f"valid_rows={len(readings)}, "
                f"finished={finished}, "
                f"capture_failed={capture_failed}"
            )

            if not finished:
                if received_bytes == 0:
                    print(
                        "\nDIAGNOSIS: No bytes received after sending the command.\n"
                        "Check that:\n"
                        "  1. PORT is the ESP's intended serial interface.\n"
                        "  2. The flashed firmware reads from that interface.\n"
                        "  3. Firmware expects 'c', rather than 'c\\n' or another command.\n"
                        "  4. Firmware is running and is not blocked."
                    )
                elif readings:
                    print(
                        "\nDIAGNOSIS: Valid sensor data arrived, but no DONE.\n"
                        "Check whether firmware sends exactly 'DONE' on its own line "
                        "and completes within 5 seconds."
                    )
                else:
                    print(
                        "\nDIAGNOSIS: Bytes arrived, but no valid sensor rows or DONE.\n"
                        "Inspect RX RAW and RX TEXT above for a protocol mismatch, "
                        "partial lines, boot messages, or garbled data."
                    )

                print("Capture timed out. Nothing saved for this attempt.")
                print("Stopping to avoid mixing delayed readings into another label.")
                break

            if capture_failed or len(readings) != 3:
                print(
                    f"Incomplete capture: expected 3 valid rows, "
                    f"got {len(readings)}. Nothing saved; try again."
                )
                continue

            for values in readings:
                writer.writerow([label] + values)

            file.flush()
            print(f"Saved 3 rows labelled '{label}'.")

    except KeyboardInterrupt:
        print("\nCollection stopped.")

    except serial.SerialException as error:
        debug(f"Serial communication failed: {error!r}")
        raise

print(f"CSV closed: {filename.resolve()}")