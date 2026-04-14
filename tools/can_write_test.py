"""
Tesla Model 3 CAN Write Test
Attempts to write CAN frames to test if the adapter can send commands.
Starts with safe commands: horn honk, light flash.

CAN ID 0x273 = UI_vehicleControl (8 bytes)
  UI_honkHorn: bit 61, 1 bit (1=honk)
  UI_domeLightSwitch: bit 59, 2 bits (0=off, 1=on, 2=auto)
  UI_lightSwitch: bit 9, 3 bits
  UI_frunkRequest: bit 5, 1 bit

WARNING: This WRITES to the CAN bus. Use at your own risk.
"""
import serial
import time
import sys


DEFAULT_BAUD = 115200


def send_cmd(ser, cmd, wait=0.5):
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    resp = ser.read(ser.in_waiting).decode(errors="ignore").strip()
    return resp


def init_adapter(ser):
    cmds = [
        ("ATZ", 2),
        ("ATE0", 0.5),
        ("ATL1", 0.5),
        ("ATH1", 0.5),
        ("ATS1", 0.5),
        ("ATSP6", 0.5),
        ("ATCAF0", 0.5),
    ]
    print("Initializing adapter...")
    for cmd, wait in cmds:
        resp = send_cmd(ser, cmd, wait)
        print(f"  {cmd} -> {resp}")
    print()


def build_frame(byte_count=8):
    """Build an 8-byte frame with all zeros."""
    return [0] * byte_count


def set_bit(frame, bit_pos, value=1):
    """Set a bit in the frame. bit_pos is DBC-style little-endian."""
    byte_idx = bit_pos // 8
    bit_idx = bit_pos % 8
    if byte_idx < len(frame):
        if value:
            frame[byte_idx] |= (1 << bit_idx)
        else:
            frame[byte_idx] &= ~(1 << bit_idx)
    return frame


def frame_to_hex(frame):
    """Convert frame bytes to hex string for OBDLink."""
    return " ".join(f"{b:02X}" for b in frame)


def try_honk(ser):
    """Try to honk the horn via CAN write."""
    print("=== HONK TEST ===")
    print("Sending UI_honkHorn=1 on CAN ID 0x273...")

    # Build frame: UI_honkHorn is bit 61
    frame = build_frame(8)
    set_bit(frame, 61, 1)

    hex_data = frame_to_hex(frame)
    # STCSM = STN CAN Send Message: ID, DLC, data
    cmd = f"STCSM 273,8,{hex_data.replace(' ', '')}"
    print(f"  Command: {cmd}")

    resp = send_cmd(ser, cmd, 1.0)
    print(f"  Response: {resp}")

    if "OK" in resp.upper() or resp == ">":
        print("  Command accepted! Did you hear the horn?")
    elif "ERROR" in resp.upper() or "?" in resp:
        print("  Command rejected by adapter.")
        # Try alternative format
        print("  Trying alternative format...")
        cmd2 = f"STCSM273,8,{hex_data.replace(' ', '')}"
        resp2 = send_cmd(ser, cmd2, 1.0)
        print(f"  Alt response: {resp2}")
    else:
        print(f"  Unknown response: {resp}")

    return resp


def try_dome_light(ser, state=1):
    """Try to toggle dome light via CAN write."""
    states = {0: "OFF", 1: "ON", 2: "AUTO"}
    print(f"\n=== DOME LIGHT TEST ({states.get(state, state)}) ===")
    print(f"Sending UI_domeLightSwitch={state} on CAN ID 0x273...")

    frame = build_frame(8)
    # UI_domeLightSwitch: bit 59, 2 bits
    byte_idx = 59 // 8  # byte 7
    bit_idx = 59 % 8    # bit 3
    frame[byte_idx] |= (state << bit_idx) & 0xFF

    hex_data = frame_to_hex(frame)
    cmd = f"STCSM 273,8,{hex_data.replace(' ', '')}"
    print(f"  Command: {cmd}")

    resp = send_cmd(ser, cmd, 1.0)
    print(f"  Response: {resp}")
    return resp


def try_pedal_map(ser, mode=2):
    """Try to change pedal map (drive mode) via CAN write."""
    modes = {0: "Chill", 1: "Standard", 2: "Performance"}
    print(f"\n=== PEDAL MAP TEST ({modes.get(mode, mode)}) ===")
    print(f"Sending UI_pedalMap={mode} on CAN ID 0x334...")

    # UI_pedalMap: bit 5, 2 bits on CAN ID 0x334 (820 decimal)
    frame = build_frame(8)
    byte_idx = 5 // 8  # byte 0
    bit_idx = 5 % 8    # bit 5
    frame[byte_idx] |= (mode << bit_idx) & 0xFF

    hex_data = frame_to_hex(frame)
    cmd = f"STCSM 334,8,{hex_data.replace(' ', '')}"
    print(f"  Command: {cmd}")

    resp = send_cmd(ser, cmd, 1.0)
    print(f"  Response: {resp}")
    return resp


def interactive_mode(ser):
    """Interactive menu for testing CAN writes."""
    while True:
        print("\n--- Tesla CAN Write Test Menu ---")
        print("1. Honk horn")
        print("2. Dome light ON")
        print("3. Dome light OFF")
        print("4. Pedal map -> Performance")
        print("5. Pedal map -> Standard (reset)")
        print("6. Pedal map -> Chill")
        print("7. Send custom CAN frame")
        print("8. Read CAN traffic (5 seconds)")
        print("0. Exit")
        print()

        choice = input("Choice: ").strip()

        if choice == "1":
            try_honk(ser)
        elif choice == "2":
            try_dome_light(ser, 1)
        elif choice == "3":
            try_dome_light(ser, 0)
        elif choice == "4":
            try_pedal_map(ser, 2)
        elif choice == "5":
            try_pedal_map(ser, 1)
        elif choice == "6":
            try_pedal_map(ser, 0)
        elif choice == "7":
            can_id = input("CAN ID (hex, e.g. 273): ").strip()
            data = input("Data bytes (hex, e.g. 00 00 00 00 00 00 20 00): ").strip()
            cmd = f"STCSM {can_id},8,{data.replace(' ', '')}"
            print(f"Sending: {cmd}")
            resp = send_cmd(ser, cmd, 1.0)
            print(f"Response: {resp}")
        elif choice == "8":
            print("Monitoring CAN for 5 seconds...")
            ser.write(b"STMA\r")
            time.sleep(0.3)
            start = time.time()
            count = 0
            while time.time() - start < 5:
                if ser.in_waiting:
                    line = ser.readline().decode(errors="ignore").strip()
                    if line and not line.startswith(">"):
                        count += 1
                        if count <= 20:
                            print(f"  {line}")
            ser.write(b"\r")
            time.sleep(0.5)
            ser.read(ser.in_waiting)
            print(f"  {count} frames in 5 seconds")
        elif choice == "0":
            break


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Tesla CAN Write Test")
    parser.add_argument("--port", "-p", default="COM5")
    parser.add_argument("--test", "-t", choices=["honk", "light", "pedalmap", "interactive"],
                        default="interactive")
    args = parser.parse_args()

    print(f"Connecting to {args.port}...")
    ser = serial.Serial(args.port, DEFAULT_BAUD, timeout=2)
    init_adapter(ser)

    if args.test == "honk":
        try_honk(ser)
    elif args.test == "light":
        try_dome_light(ser, 1)
    elif args.test == "pedalmap":
        try_pedal_map(ser, 2)
    else:
        interactive_mode(ser)

    ser.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
