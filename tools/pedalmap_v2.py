"""Send correct UI_pedalMap=Performance using real frame from car."""
import serial
import time

ser = serial.Serial("COM5", 115200, timeout=2)
time.sleep(0.5)

for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    ser.read(ser.in_waiting)

ser.write(b"ATSH 334\r")
time.sleep(0.5)
ser.read(ser.in_waiting)

# Real frame from car: BF 3F 14 80 FC 07 XX XX
# BF = 10111111 -> bits 5-6 = 01 = Standard
# DF = 11011111 -> bits 5-6 = 10 = Performance
# Last 2 bytes vary (counter/checksum) - try different values
data = "DF 3F 14 80 FC 07 00 00"

print("PERFORMANCE MODE ACTIVE FOR 60 SECONDS!")
print("TAP THE ACCELERATOR!")

start = time.time()
count = 0
counter = 0
while time.time() - start < 60:
    # Rotate last 2 bytes to try different counter values
    b7 = (counter * 16) & 0xFF
    b8 = (counter * 4) & 0xFF
    frame = f"DF 3F 14 80 FC 07 {b7:02X} {b8:02X}"
    ser.write((frame + "\r").encode())
    time.sleep(0.05)
    ser.read(ser.in_waiting)
    count += 1
    counter = (counter + 1) % 256

print(f"Done. Sent {count} frames.")
ser.close()
