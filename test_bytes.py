"""Test different byte 0 values and see car response."""
import serial, time
ser = serial.Serial("COM5", 115200, timeout=2)
time.sleep(0.5)
for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATS1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    ser.read(ser.in_waiting)

test_bytes = [0x3F, 0x7F, 0xBF, 0xFF]
names = {0x3F: "Chill", 0x7F: "Perf?", 0xBF: "Standard", 0xFF: "Perf??"}

for tb in test_bytes:
    cnt = 5
    b6 = (cnt << 4) | 0x04
    frame_bytes = [tb, 0x3F, 0x0A, 0x80, 0xFC, 0x07, b6]
    b7 = (sum(frame_bytes) + 0x37) & 0xFF
    frame = " ".join(f"{b:02X}" for b in frame_bytes) + f" {b7:02X}"

    # Send it
    ser.write(b"ATSH 334\r")
    time.sleep(0.05)
    ser.read(ser.in_waiting)
    ser.write((frame + "\r").encode())
    time.sleep(0.2)
    resp = ser.read(ser.in_waiting).decode(errors="ignore").strip()

    # Check for errors
    has_error = "ERROR" in resp or "?" in resp
    print(f"  0x{tb:02X} ({names[tb]:8s}): {frame} -> {'ERROR' if has_error else 'OK'}: {resp[:80]}", flush=True)

# Now read what the car is sending
print("\nReading car's 0x334 response...", flush=True)
ser.write(b"ATSP6\r")
time.sleep(0.1)
ser.read(ser.in_waiting)
ser.write(b"ATCAF0\r")
time.sleep(0.1)
ser.read(ser.in_waiting)
ser.write(b"STMA\r")
time.sleep(0.3)
start = time.time()
found = 0
while time.time() - start < 20 and found < 3:
    if ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
        if "334" in line[:5]:
            print(f"  CAR: {line}", flush=True)
            found += 1
    else:
        time.sleep(0.01)
ser.write(b"\r")
time.sleep(0.3)
ser.close()
print("Done.", flush=True)
