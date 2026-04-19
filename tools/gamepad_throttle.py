"""
Tesla Model 3 Gamepad Throttle Control
Maps right trigger to direct torque injection on CAN ID 0x1D8.
Checksum: byte7 = (sum(bytes 0-6) + 0xD9) & 0xFF

Requirements: pip install pygame pyserial
Usage: python gamepad_throttle.py --port COM5
"""
import serial
import time
import sys
import argparse

try:
    import pygame
except ImportError:
    print("ERROR: pip install pygame")
    sys.exit(1)

DEFAULT_BAUD = 115200
MAX_TORQUE_NM = 400  # Max torque to inject (car rated ~430 Nm)
CAN_ID = 0x1D8


def checksum(frame_bytes):
    return (sum(frame_bytes) + 0xD9) & 0xFF


def encode_torque(nm):
    """Encode Nm value into 0x1D8 frame bytes 1-2 (13-bit signed at bit 8, scale 0.222)."""
    raw = int(nm / 0.222) & 0x1FFF
    b1 = raw & 0xFF
    b2 = (raw >> 8) & 0x1F
    return b1, b2


def send_frame(ser, torque_nm, counter):
    b1, b2 = encode_torque(torque_nm)
    cnt = counter & 0xF
    b6 = (cnt << 4) & 0xF0
    frame_bytes = [0x29, b1, b2, 0x00, 0x00, 0x00, b6]
    b7 = checksum(frame_bytes)
    frame = " ".join(f"{b:02X}" for b in frame_bytes) + f" {b7:02X}"
    ser.write((frame + "\r").encode())
    ser.read(ser.in_waiting)


def setup_serial(port):
    ser = serial.Serial(port, DEFAULT_BAUD, timeout=1)
    time.sleep(0.5)
    for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
        ser.write((cmd + "\r").encode())
        time.sleep(wait)
        ser.read(ser.in_waiting)
    ser.write(f"ATSH {CAN_ID:03X}\r".encode())
    time.sleep(0.5)
    ser.read(ser.in_waiting)
    return ser


def main():
    parser = argparse.ArgumentParser(description="Gamepad throttle control for Tesla Model 3")
    parser.add_argument("--port", "-p", default="COM5", help="Serial port (default: COM5)")
    parser.add_argument("--max-torque", type=int, default=MAX_TORQUE_NM, help="Max torque Nm")
    args = parser.parse_args()

    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("ERROR: No gamepad found. Plug in your Logitech and try again.")
        sys.exit(1)

    joy = pygame.joystick.Joystick(0)
    joy.init()
    print(f"Gamepad: {joy.get_name()}")

    print(f"Connecting to {args.port}...")
    ser = setup_serial(args.port)
    print("Connected. Right trigger = torque boost. Ctrl+C to stop.\n")

    counter = 0
    try:
        while True:
            pygame.event.pump()

            # Right trigger: axis 5 on Xbox/Logitech (-1.0 to 1.0, -1=released)
            # Try axis 5 first, fall back to axis 2
            try:
                trigger = joy.get_axis(5)
            except Exception:
                trigger = joy.get_axis(2)

            # Normalize: -1.0 = not pressed, 1.0 = fully pressed -> 0.0 to 1.0
            trigger_pct = (trigger + 1.0) / 2.0
            torque = trigger_pct * args.max_torque

            if trigger_pct > 0.05:
                send_frame(ser, torque, counter)
                counter += 1
                print(f"\r  Trigger: {trigger_pct*100:.0f}%  Torque: {torque:.0f} Nm  Frames: {counter}", end="", flush=True)

            time.sleep(0.02)  # 50Hz

    except KeyboardInterrupt:
        print(f"\n\nStopped. {counter} frames sent.")
        ser.close()
        pygame.quit()


if __name__ == "__main__":
    main()
