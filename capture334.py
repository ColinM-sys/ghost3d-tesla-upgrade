"""Capture only 0x334 frames with spaces on, for 60 seconds."""
import serial, time
ser = serial.Serial("COM5", 115200, timeout=2)
time.sleep(0.5)
for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATS1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    ser.read(ser.in_waiting)

print("Capturing 0x334 frames for 60 seconds...", flush=True)
print("SWITCH MODES ON THE SCREEN during capture!", flush=True)
print("Standard -> Chill -> Standard", flush=True)
print("", flush=True)

ser.write(b"STMA\r")
time.sleep(0.3)

start = time.time()
count = 0
while time.time() - start < 60:
    if ser.in_waiting:
        line = ser.readline().decode(errors="ignore").strip()
        if line and "334" in line[:5]:
            elapsed = time.time() - start
            print(f"  [{elapsed:.1f}s] {line}", flush=True)
            count += 1
    else:
        time.sleep(0.01)

ser.write(b"\r")
time.sleep(0.3)
ser.close()
print(f"\nDone. Found {count} frames with 334.", flush=True)
