"""Colin Mode NONSTOP: fastest possible, no sleep, runs until killed."""
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
print("COLIN MODE NONSTOP — max speed — runs forever until killed", flush=True)
count = 0
while True:
    cnt = count & 0xF
    b6 = (cnt << 4) | 0x04
    b7 = (((cnt + 0xD) & 0xF) << 4)
    ser.write(f"5F 3F 14 80 FC 07 {b6:02X} {b7:02X}\r".encode())
    ser.read(ser.in_waiting)
    count += 1
    if count % 1000 == 0:
        print(f"  {count} frames sent", flush=True)
