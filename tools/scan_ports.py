"""Scan serial ports to find OBDLink MX+ adapter."""
import serial.tools.list_ports


def scan():
    ports = serial.tools.list_ports.comports()
    print(f"Found {len(ports)} serial ports:")
    for p in ports:
        print(f"  {p.device}: {p.description} [hwid={p.hwid}]")
        if any(x in p.description.upper() for x in ["OBD", "STN", "ELM", "BLUETOOTH"]):
            print(f"    ^^^ Likely OBDLink adapter! ^^^")
    if not ports:
        print("No serial ports found. Is the OBDLink paired via Bluetooth?")


if __name__ == "__main__":
    scan()
