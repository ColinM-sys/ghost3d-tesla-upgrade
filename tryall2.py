import serial, time
for port in ["COM3", "COM4", "COM5", "COM6", "COM7", "COM8"]:
    try:
        print(f"Trying {port}...", flush=True)
        s = serial.Serial(port, 115200, timeout=3)
        time.sleep(0.5)
        s.write(b"ATZ\r")
        time.sleep(2)
        r = s.read(s.in_waiting).decode(errors="ignore").strip()
        s.close()
        if r:
            print(f"  CONNECTED on {port}: {r}", flush=True)
            break
        else:
            print(f"  Opened {port} but no response", flush=True)
    except Exception as e:
        print(f"  {port}: {e}", flush=True)
