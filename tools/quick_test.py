import serial, time

for port in ["COM4", "COM5"]:
    try:
        print(f"Trying {port}...", flush=True)
        s = serial.Serial(port, 115200, timeout=3)
        time.sleep(1)
        s.write(b"ATI\r")
        time.sleep(2)
        r = s.read(s.in_waiting).decode(errors="ignore").strip()
        s.close()
        if r:
            print(f"  CONNECTED on {port}: {r}")
        else:
            print(f"  Opened {port} but no response")
    except Exception as e:
        print(f"  {port} FAILED: {e}")
