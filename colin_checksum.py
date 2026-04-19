"""Colin Mode with CORRECT checksum: byte7 = (sum(bytes0-6) + 0x37) & 0xFF"""
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
print("COLIN MODE — CORRECT CHECKSUM — runs forever", flush=True)
count = 0
while True:
    cnt = count & 0xF
    b6 = (cnt << 4) | 0x04
    # Performance pedal (7F) with current byte2 (0A)
    frame_bytes = [0x7F, 0x3F, 0x0A, 0x80, 0xFC, 0x07, b6]
    b7 = (sum(frame_bytes) + 0x37) & 0xFF
    frame = " ".join(f"{b:02X}" for b in frame_bytes) + f" {b7:02X}"
    ser.write((frame + "\r").encode())
    ser.read(ser.in_waiting)
    count += 1
    if count % 1000 == 0:
        print(f"  {count} frames", flush=True)
