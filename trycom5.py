import serial, time
try:
    print("Trying COM5...", flush=True)
    s = serial.Serial("COM5", 115200, timeout=3)
    time.sleep(0.5)
    s.write(b"ATZ\r")
    time.sleep(2)
    r = s.read(s.in_waiting).decode(errors="ignore").strip()
    s.close()
    if r:
        print(f"CONNECTED: {r}")
    else:
        print("Opened but no response")
except Exception as e:
    print(f"FAILED: {e}")
