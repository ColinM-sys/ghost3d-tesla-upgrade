import serial, time
print("Hammering COM5 until it connects...", flush=True)
for attempt in range(120):
    try:
        s = serial.Serial("COM5", 115200, timeout=2)
        time.sleep(0.3)
        s.write(b"ATZ\r")
        time.sleep(1.5)
        r = s.read(s.in_waiting).decode(errors="ignore").strip()
        if r and "ELM" in r:
            print(f"CONNECTED on attempt {attempt+1}: {r}", flush=True)
            s.close()
            break
        s.close()
        if attempt % 10 == 0:
            print(f"  Attempt {attempt+1}: opened but no response", flush=True)
    except Exception as e:
        if attempt % 10 == 0:
            print(f"  Attempt {attempt+1}: {e}", flush=True)
    time.sleep(0.5)
else:
    print("Failed after 120 attempts.", flush=True)
