"""Try different CAN write command formats on OBDLink MX+."""
import serial
import time

ser = serial.Serial("COM5", 115200, timeout=2)
time.sleep(0.5)

def cmd(c, wait=1.0):
    ser.write((c + "\r").encode())
    time.sleep(wait)
    r = ser.read(ser.in_waiting).decode(errors="ignore").strip()
    print(f"  {c} -> {r}")
    return r

# Init
cmd("ATZ", 2)
cmd("ATE0", 0.5)
cmd("ATH1", 0.5)
cmd("ATSP6", 0.5)
cmd("ATCAF0", 0.5)

print("\n=== Testing CAN write commands ===\n")

# Format 1: STCSM (STN specific)
print("Format 1: STCSM ID,DLC,DATA")
cmd("STCSM 273,8,0000000000000020")

# Format 2: STCSM without spaces in args
print("\nFormat 2: STCSM with no space after comma")
cmd("STCSM273,8,0000000000000020")

# Format 3: AT SH + data send (ELM327 standard)
print("\nFormat 3: AT SH (set header) then send data")
cmd("ATSH 273")
cmd("0000000000000020")

# Format 4: AT SH with CAN formatting on
print("\nFormat 4: ATCAF1 then SH + send")
cmd("ATCAF1", 0.5)
cmd("ATSH 273")
cmd("00 00 00 00 00 00 00 20")

# Format 5: Try STCMM (send multiple)
print("\nFormat 5: STCMM")
cmd("ATCAF0", 0.5)
cmd("STCMM 273,8,0000000000000020,1")

# Format 6: STN raw CAN send
print("\nFormat 6: STCFCSM")
cmd("STCFCSM 273,0000000000000020")

# Format 7: Check if write is supported
print("\nFormat 7: STN capabilities")
cmd("STI")
cmd("STDI")
cmd("STFCP")

# Format 8: Try with CAN extended addressing
print("\nFormat 8: STP (set protocol) then send")
cmd("ATSP 6", 0.5)
cmd("ATSH 273", 0.5)
cmd("ATFC SH 273", 0.5)
cmd("ATFC SD 0000000000000020", 0.5)
cmd("ATFC SM 1", 0.5)

ser.close()
print("\nDone - check which format got OK response")
