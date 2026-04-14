"""Send UI_pedalMap=2 (Performance) continuously for 10 seconds."""
import serial
import time

ser = serial.Serial("COM5", 115200, timeout=2)
time.sleep(0.5)

# Init
for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    ser.read(ser.in_waiting)

# Set header to 0x334 (UI_pedalMap CAN ID)
ser.write(b"ATSH 334\r")
time.sleep(0.5)
ser.read(ser.in_waiting)

# UI_pedalMap: bit 5, 2 bits, value=2 (Performance)
# Byte 0, bits 5-6 = 0b10 = 0x40
# Full 8 bytes with just pedalMap set
data = "40 00 00 00 00 00 00 00"

print("Starting in 10 seconds... GET READY!")
print("Put car in DRIVE, foot on BRAKE")
for i in range(10, 0, -1):
    print(f"  {i}...")
    time.sleep(1)
print("GO! TAP THE ACCELERATOR NOW!")

start = time.time()
count = 0
while time.time() - start < 20:
    ser.write((data + "\r").encode())
    time.sleep(0.05)
    ser.read(ser.in_waiting)
    count += 1

print(f"Done. Sent {count} frames in 10 seconds.")
print("Car should revert to Standard now.")
ser.close()
