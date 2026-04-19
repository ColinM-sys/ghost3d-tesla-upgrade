"""Colin Mode FAST: 10ms intervals instead of 50ms. 120 seconds."""
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
print("COLIN MODE FAST — 10ms intervals — 120 seconds", flush=True)
start = time.time()
count = 0
while time.time() - start < 120:
    cnt = count & 0xF
    b6 = (cnt << 4) | 0x04
    b7 = (((cnt + 0xD) & 0xF) << 4)
    byte0 = 0x5F
    byte1 = 0x3F
    frame = f"{byte0:02X} {byte1:02X} 14 80 FC 07 {b6:02X} {b7:02X}"
    ser.write((frame + "\r").encode())
    time.sleep(0.01)
    ser.read(ser.in_waiting)
    count += 1
print(f"Done. Sent {count} frames.", flush=True)
ser.close()
