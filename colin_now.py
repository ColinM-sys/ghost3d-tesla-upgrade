"""Colin Mode: Performance + max power + max torque. 120 seconds."""
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
print("COLIN MODE ON — MAX POWER + MAX TORQUE — 120 seconds", flush=True)
start = time.time()
count = 0
while time.time() - start < 120:
    cnt = count & 0xF
    b6 = (cnt << 4) | 0x04
    b7 = (((cnt + 0xD) & 0xF) << 4)
    # Byte 0: Performance pedal (7F) + power limit max (bits 0-4 = 31)
    # 7F = 01111111, power bits 0-4 = 11111 = 31 (max 640kW)
    # Combined: bits 0-4 = 11111 (31), bits 5-6 = 10 (perf) = 01011111 + 00100000
    # Actually: 31 = 0x1F, perf bits 5-6 = 10 -> byte0 = 0x1F | (2<<5) = 0x1F | 0x40 = 0x5F
    byte0 = 0x5F  # power max + performance pedal
    # Byte 1: torque limit max (bits 0-5 = 63) + other bits from real frame (3F)
    # 63 = 0x3F = 00111111, real byte1 = 0x3F -> same! Max torque already set
    byte1 = 0x3F
    frame = f"{byte0:02X} {byte1:02X} 14 80 FC 07 {b6:02X} {b7:02X}"
    ser.write((frame + "\r").encode())
    time.sleep(0.05)
    ser.read(ser.in_waiting)
    count += 1
print(f"Done. Sent {count} frames.", flush=True)
ser.close()
