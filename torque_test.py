"""Test torque injection on 0x1D8 with cracked checksum."""
import serial, time
ser = serial.Serial("COM5", 115200, timeout=2)
time.sleep(0.5)
for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATS1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    ser.read(ser.in_waiting)

# Inject 0x1D8 with small torque and read response
ser.write(b"ATSH 1D8\r")
time.sleep(0.1)
ser.read(ser.in_waiting)

print("Sending 10 torque frames on 0x1D8...", flush=True)
for i in range(10):
    cnt = (i * 2) & 0xF
    b6 = (cnt << 4)
    # Keep same base as car: 29 00 00 00 00 00 XX XX
    frame_bytes = [0x29, 0x00, 0x00, 0x00, 0x00, 0x00, b6]
    b7 = (sum(frame_bytes) + 0xD9) & 0xFF
    frame = " ".join(f"{b:02X}" for b in frame_bytes) + f" {b7:02X}"
    ser.write((frame + "\r").encode())
    time.sleep(0.1)
    resp = ser.read(ser.in_waiting).decode(errors="ignore").strip()
    has_error = "?" in resp or "ERROR" in resp
    print(f"  {frame} -> {'REJECTED' if has_error else 'ACCEPTED'}: {resp[:60]}", flush=True)

# Now read bus for 0x1D8 response
print("\nReading 0x1D8 from bus...", flush=True)
ser.write(b"ATSP6\r")
time.sleep(0.1)
ser.read(ser.in_waiting)
ser.write(b"ATCAF0\r")
time.sleep(0.1)
ser.read(ser.in_waiting)
ser.write(b"ATH1\r")
time.sleep(0.1)
ser.read(ser.in_waiting)
ser.write(b"STMA\r")
time.sleep(0.3)
start = time.time()
found = 0
while time.time() - start < 5 and found < 5:
    if ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
        if "1D8" in line[:5]:
            print(f"  BUS: {line}", flush=True)
            found += 1
    else:
        time.sleep(0.01)
ser.write(b"\r")
time.sleep(0.3)
ser.close()
print("Done.", flush=True)
