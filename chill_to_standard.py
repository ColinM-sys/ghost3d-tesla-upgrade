"""Override Chill with Standard (BF) and check acceptance."""
import serial, time
ser = serial.Serial("COM5", 115200, timeout=2)
time.sleep(0.5)
for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATS1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    ser.read(ser.in_waiting)

# Send 5 Standard frames and check response
ser.write(b"ATSH 334\r")
time.sleep(0.1)
ser.read(ser.in_waiting)

print("Sending Standard (BF) frames...", flush=True)
for i in range(5):
    cnt = i & 0xF
    b6 = (cnt << 4) | 0x04
    frame_bytes = [0xBF, 0x3F, 0x0A, 0x80, 0xFC, 0x07, b6]
    b7 = (sum(frame_bytes) + 0x37) & 0xFF
    frame = " ".join(f"{b:02X}" for b in frame_bytes) + f" {b7:02X}"
    ser.write((frame + "\r").encode())
    time.sleep(0.15)
    resp = ser.read(ser.in_waiting).decode(errors="ignore").strip()
    has_334 = "334" in resp
    print(f"  SENT: {frame} -> car_334={has_334}: {resp[:80]}", flush=True)

# Now flood for 60 seconds
print("\nFLOODING Standard (BF) for 60 seconds — test pedal NOW!", flush=True)
start = time.time()
count = 0
while time.time() - start < 60:
    cnt = count & 0xF
    b6 = (cnt << 4) | 0x04
    frame_bytes = [0xBF, 0x3F, 0x0A, 0x80, 0xFC, 0x07, b6]
    b7 = (sum(frame_bytes) + 0x37) & 0xFF
    frame = " ".join(f"{b:02X}" for b in frame_bytes) + f" {b7:02X}"
    ser.write((frame + "\r").encode())
    ser.read(ser.in_waiting)
    count += 1
print(f"Done. {count} frames.", flush=True)
ser.close()
