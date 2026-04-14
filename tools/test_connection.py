"""Quick test to connect to OBDLink MX+ and verify communication."""
import serial
import time
import sys

ports_to_try = ["COM5", "COM4"]
port = sys.argv[1] if len(sys.argv) > 1 else None

if port is None:
    for p in ports_to_try:
        try:
            print(f"Trying {p}...")
            s = serial.Serial(p, 115200, timeout=2)
            time.sleep(0.5)
            s.write(b"ATZ\r")
            time.sleep(2)
            resp = s.read(s.in_waiting).decode(errors="ignore").strip()
            if resp:
                print(f"  Response: {resp}")
                port = p
                s.close()
                break
            else:
                print(f"  No response")
                s.close()
        except Exception as e:
            print(f"  Error: {e}")

if port is None:
    print("Could not connect on any port.")
    sys.exit(1)

print(f"\nConnected on {port}! Running diagnostics...\n")
s = serial.Serial(port, 115200, timeout=2)
time.sleep(0.5)

commands = [
    ("ATZ", 2, "Reset"),
    ("ATE0", 0.5, "Echo off"),
    ("ATI", 0.5, "Device ID"),
    ("STI", 0.5, "Firmware version"),
    ("STDI", 0.5, "Device description"),
    ("ATSP6", 0.5, "Set protocol CAN 500k"),
    ("ATH1", 0.5, "Headers on"),
    ("ATDPN", 0.5, "Current protocol"),
]

for cmd, wait, desc in commands:
    s.write((cmd + "\r").encode())
    time.sleep(wait)
    resp = s.read(s.in_waiting).decode(errors="ignore").strip()
    print(f"  {cmd:<10} ({desc}): {resp}")

s.close()
print("\nOBDLink MX+ is working! Ready for CAN capture.")
