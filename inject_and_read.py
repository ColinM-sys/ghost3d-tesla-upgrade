"""Inject one frame then immediately read to see what 0x334 looks like on the bus."""
import serial, time

ser = serial.Serial("COM5", 115200, timeout=2)
time.sleep(0.5)
for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATS1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    ser.read(ser.in_waiting)

# First read current 0x334 without injection
print("=== BEFORE INJECTION ===", flush=True)
ser.write(b"STMA\r")
time.sleep(0.5)
start = time.time()
found = 0
while time.time() - start < 15 and found < 3:
    if ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
        if "334" in line[:5]:
            print(f"  CAR: {line}", flush=True)
            found += 1
    else:
        time.sleep(0.01)
ser.write(b"\r")
time.sleep(0.3)
ser.read(ser.in_waiting)

# Now inject 10 frames and read
print("\n=== INJECTING 10 FRAMES ===", flush=True)
for i in range(10):
    cnt = i & 0xF
    b6 = (cnt << 4) | 0x04
    frame_bytes = [0x7F, 0x3F, 0x0A, 0x80, 0xFC, 0x07, b6]
    b7 = (sum(frame_bytes) + 0x37) & 0xFF
    frame = " ".join(f"{b:02X}" for b in frame_bytes) + f" {b7:02X}"

    ser.write(b"ATSH 334\r")
    time.sleep(0.05)
    ser.read(ser.in_waiting)
    ser.write((frame + "\r").encode())
    time.sleep(0.1)
    resp = ser.read(ser.in_waiting).decode(errors="ignore").strip()
    print(f"  SENT: {frame} -> RESP: {resp}", flush=True)

# Read after injection
print("\n=== AFTER INJECTION ===", flush=True)
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
time.sleep(0.5)
start = time.time()
found = 0
while time.time() - start < 15 and found < 3:
    if ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
        if "334" in line[:5]:
            print(f"  BUS: {line}", flush=True)
            found += 1
    else:
        time.sleep(0.01)
ser.write(b"\r")
time.sleep(0.3)
ser.close()
print("\nDone.", flush=True)
