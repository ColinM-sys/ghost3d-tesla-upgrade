import serial, time
for port in ["COM5", "COM4", "COM3"]:
    try:
        print(f"Trying {port}...", flush=True)
        s = serial.Serial(port, 115200, timeout=5)
        time.sleep(0.5)
        s.write(b"ATZ\r")
        time.sleep(2)
        r = s.read(s.in_waiting).decode(errors="ignore").strip()
        s.close()
        if r:
            print(f"  CONNECTED on {port}: {r}")
            break
        else:
            print(f"  Opened {port} but no response")
    except Exception as e:
        print(f"  {port}: {e}")
