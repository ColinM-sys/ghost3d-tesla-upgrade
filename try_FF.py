"""Try 0xFF as Performance byte."""
import serial, time
ser = serial.Serial("COM5", 115200, timeout=2)
time.sleep(0.5)
for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    ser.read(ser.in_waiting)
ser.write(b"ATSH 334\r")
time.sleep(0.5)
ser.read(ser.in_waiting)
print("TRYING 0xFF AS PERFORMANCE — 120 seconds", flush=True)
count = 0
start = time.time()
while time.time() - start < 120:
    cnt = count & 0xF
    b6 = (cnt << 4) | 0x04
    frame_bytes = [0xFF, 0x3F, 0x0A, 0x80, 0xFC, 0x07, b6]
    b7 = (sum(frame_bytes) + 0x37) & 0xFF
    frame = " ".join(f"{b:02X}" for b in frame_bytes) + f" {b7:02X}"
    ser.write((frame + "\r").encode())
    ser.read(ser.in_waiting)
    count += 1
print(f"Done. {count} frames.", flush=True)
ser.close()
