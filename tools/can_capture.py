"""
Tesla Model 3 CAN Bus Capture Tool
Connects to OBDLink MX+ via Bluetooth serial and captures raw CAN frames.
"""
import serial
import time
import sys
import os
from datetime import datetime

DEFAULT_BAUD = 115200


def find_obdlink_port():
    """Auto-detect OBDLink MX+ serial port."""
    import serial.tools.list_ports
    for p in serial.tools.list_ports.comports():
        if any(x in p.description.upper() for x in ["OBD", "STN", "ELM", "BLUETOOTH", "STANDARD SERIAL"]):
            return p.device
    return None


def send_command(ser, cmd, wait=0.5):
    """Send AT/ST command and return response."""
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    response = ser.read(ser.in_waiting).decode(errors="ignore").strip()
    return response


def setup_can_monitor(ser):
    """Initialize OBDLink MX+ for raw CAN monitoring."""
    commands = [
        ("ATZ", 2),        # Reset
        ("ATE0", 0.5),     # Echo off
        ("ATL1", 0.5),     # Linefeeds on
        ("ATH1", 0.5),     # Headers on (show CAN IDs)
        ("ATS0", 0.5),     # Spaces off (compact output)
        ("ATSP6", 0.5),    # Set protocol to ISO 15765-4 CAN (11bit, 500kbaud)
        ("ATCAF0", 0.5),   # CAN auto-formatting off (raw frames)
        ("ATR1", 0.5),     # Responses on
    ]

    print("Initializing OBDLink MX+...")
    for cmd, wait in commands:
        resp = send_command(ser, cmd, wait)
        print(f"  {cmd} -> {resp}")
    print("Ready for CAN capture.\n")


def capture(port=None, duration=60, output_dir="captures"):
    """Capture CAN frames for specified duration."""
    if port is None:
        port = find_obdlink_port()
        if port is None:
            print("ERROR: No OBDLink adapter found. Pair via Bluetooth first.")
            print("Run scan_ports.py to see available ports.")
            sys.exit(1)

    print(f"Connecting to {port} at {DEFAULT_BAUD} baud...")
    ser = serial.Serial(port, DEFAULT_BAUD, timeout=1)

    setup_can_monitor(ser)

    # Start monitoring all CAN traffic
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)
    outfile = os.path.join(output_dir, f"can_capture_{timestamp}.log")

    print(f"Starting CAN capture for {duration}s -> {outfile}")
    print("Sending STMA (monitor all)...\n")

    ser.write(b"STMA\r")  # STN command: monitor all CAN traffic

    start = time.time()
    frame_count = 0

    with open(outfile, "w") as f:
        f.write(f"# Tesla Model 3 CAN Capture\n")
        f.write(f"# Date: {timestamp}\n")
        f.write(f"# Port: {port}\n")
        f.write(f"# Duration: {duration}s\n\n")

        try:
            while time.time() - start < duration:
                if ser.in_waiting:
                    line = ser.readline().decode(errors="ignore").strip()
                    if line and not line.startswith(">"):
                        elapsed = time.time() - start
                        entry = f"{elapsed:.4f} {line}"
                        f.write(entry + "\n")
                        frame_count += 1
                        if frame_count % 100 == 0:
                            print(f"  {frame_count} frames captured ({elapsed:.1f}s)...")
        except KeyboardInterrupt:
            print("\nCapture interrupted by user.")
        finally:
            # Send any char to stop STMA
            ser.write(b"\r")
            time.sleep(0.5)
            ser.close()

    print(f"\nCapture complete: {frame_count} frames saved to {outfile}")
    return outfile


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tesla Model 3 CAN Bus Capture")
    parser.add_argument("--port", "-p", help="Serial port (auto-detect if not specified)")
    parser.add_argument("--duration", "-d", type=int, default=60, help="Capture duration in seconds")
    parser.add_argument("--output", "-o", default="captures", help="Output directory")
    args = parser.parse_args()

    capture(port=args.port, duration=args.duration, output_dir=args.output)
