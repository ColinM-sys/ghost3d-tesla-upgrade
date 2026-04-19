"""Direct Performance injection with CRACKED checksum. Runs for 120 seconds."""
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
print("BOOST ON — CRACKED CHECKSUM — 120 seconds", flush=True)
start = time.time()
count = 0
while time.time() - start < 120:
    cnt = count & 0xF
    # Byte 6: counter in high nibble, 4 in low nibble
    b6 = (cnt << 4) | 0x04
    # Byte 7: (counter + 0xD) mod 16 in high nibble, 0 in low nibble
    b7 = (((cnt + 0xD) & 0xF) << 4)
    # 7F = Performance mode (bits 5-6 = 10)
    ser.write(f"7F 3F 14 80 FC 07 {b6:02X} {b7:02X}\r".encode())
    time.sleep(0.05)
    ser.read(ser.in_waiting)
    count += 1
print(f"Done. Sent {count} frames.", flush=True)
ser.close()
