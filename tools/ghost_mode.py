"""
Tesla Model 3 Ghost Mode with Data Logging
Injects Performance pedal map while simultaneously recording all CAN data.
Runs both read and write on the same serial connection by alternating.

Usage:
    python ghost_mode.py --port COM5 --mode performance --duration 60
    python ghost_mode.py --port COM5 --mode standard --duration 60   (baseline)
    python ghost_mode.py --port COM5 --mode compare --file1 baseline.log --file2 ghost.log
"""
import serial
import serial.tools.list_ports
import time
import sys
import os
import json
import argparse
from datetime import datetime


DEFAULT_BAUD = 115200

# Pedal map frame from real car
# Byte 0 bits 5-6 = pedal map value
# BF = Standard (01), DF = Performance (10), 9F = Chill (00)
FRAME_BASE = [0xBF, 0x3F, 0x14, 0x80, 0xFC, 0x07, 0x00, 0x00]

PEDAL_MODES = {
    "chill": 0,
    "standard": 1,
    "performance": 2,
}

MODE_BYTES = {
    "chill": 0x9F,
    "standard": 0xBF,
    "performance": 0xDF,
}


def extract_le(data_bytes, start_bit, bit_length, scale, offset):
    byte_vals = [int(b, 16) for b in data_bytes]
    while len(byte_vals) < 8:
        byte_vals.append(0)
    raw_val = 0
    for i, bv in enumerate(byte_vals):
        raw_val |= (bv << (i * 8))
    mask = (1 << bit_length) - 1
    extracted = (raw_val >> start_bit) & mask
    return round(extracted * scale + offset, 3)


def parse_frame(line):
    line = line.strip()
    if not line or line.startswith(">") or line.startswith("#"):
        return None, None
    if "STOPPED" in line or "ERROR" in line or "BUFFER" in line or "SEARCHING" in line:
        return None, None
    parts = line.split()
    if len(parts) < 2:
        return None, None
    can_id_str = parts[0].upper()
    if not all(c in "0123456789ABCDEF" for c in can_id_str):
        return None, None
    if len(can_id_str) > 8:
        return None, None
    try:
        return int(can_id_str, 16), parts[1:]
    except ValueError:
        return None, None


def send_cmd(ser, cmd, wait=0.5):
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    return ser.read(ser.in_waiting).decode(errors="ignore").strip()


def init_adapter(ser):
    cmds = [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]
    print("Initializing adapter...")
    for cmd, wait in cmds:
        send_cmd(ser, cmd, wait)
    print("Ready.\n")


def record_drive(ser, duration, mode_name, inject_mode=None):
    """Record CAN data while optionally injecting a pedal map mode."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("captures", exist_ok=True)
    log_path = f"captures/ghost_{mode_name}_{timestamp}.log"

    inject = inject_mode is not None
    if inject:
        mode_byte = MODE_BYTES.get(inject_mode, 0xBF)
        print(f"GHOST MODE: Injecting {inject_mode.upper()} ({mode_byte:#04x})")
    else:
        print(f"BASELINE: Recording {mode_name} (no injection)")

    print(f"Duration: {duration}s")
    print(f"Log: {log_path}")
    print()

    # Phase: alternating read bursts and write bursts
    start = time.time()
    frame_count = 0
    inject_count = 0
    accel_samples = []
    speed_samples = []

    with open(log_path, "w") as log:
        log.write(f"# Ghost Mode Recording\n")
        log.write(f"# Mode: {mode_name}\n")
        log.write(f"# Injection: {inject_mode if inject else 'none'}\n")
        log.write(f"# Started: {datetime.now().isoformat()}\n")
        log.write(f"# Duration: {duration}s\n\n")

        while time.time() - start < duration:
            elapsed = time.time() - start

            # READ PHASE: monitor for 0.2 seconds
            ser.write(b"STMA\r")
            time.sleep(0.01)
            read_start = time.time()
            while time.time() - read_start < 0.2:
                if ser.in_waiting:
                    line = ser.readline().decode(errors="ignore").strip()
                    can_id, data = parse_frame(line)
                    if can_id is not None and data is not None:
                        frame_count += 1
                        can_hex = f"{can_id:03X}"
                        data_str = " ".join(data)
                        log.write(f"{elapsed:.4f} {can_hex} {data_str}\n")

                        # Track key signals
                        if can_id == 0x118 and len(data) >= 5:
                            accel = extract_le(data, 32, 8, 0.4, 0)
                            accel_samples.append((elapsed, accel))
                        elif can_id == 0x318 and len(data) >= 3:
                            speed = extract_le(data, 12, 12, 0.05, 0)
                            speed_samples.append((elapsed, speed))
                else:
                    time.sleep(0.005)

            # Stop monitor
            ser.write(b"\r")
            time.sleep(0.1)
            ser.read(ser.in_waiting)

            # WRITE PHASE: inject pedal map if ghost mode active
            if inject:
                ser.write(b"ATSH 334\r")
                time.sleep(0.05)
                ser.read(ser.in_waiting)

                # Send 3 rapid injections
                for i in range(3):
                    counter = (inject_count + i) % 256
                    b7 = (counter * 16) & 0xFF
                    b8 = (counter * 4) & 0xFF
                    frame = f"{mode_byte:02X} 3F 14 80 FC 07 {b7:02X} {b8:02X}"
                    ser.write((frame + "\r").encode())
                    time.sleep(0.02)
                    ser.read(ser.in_waiting)

                inject_count += 3

                # Reset header for next read
                ser.write(b"ATSH 7DF\r")
                time.sleep(0.05)
                ser.read(ser.in_waiting)

            # Status update
            if int(elapsed) % 5 == 0 and int(elapsed) != int(elapsed - 0.3):
                last_accel = accel_samples[-1][1] if accel_samples else 0
                last_speed = speed_samples[-1][1] if speed_samples else 0
                print(f"  [{elapsed:.0f}s] {frame_count} frames | "
                      f"Accel: {last_accel:.1f}% | Speed: {last_speed:.1f} km/h | "
                      f"Injected: {inject_count}")

        log.flush()

    print(f"\nDone: {frame_count} frames captured, {inject_count} injections sent")
    print(f"Accel samples: {len(accel_samples)}, Speed samples: {len(speed_samples)}")
    print(f"Saved to {log_path}")

    # Save summary
    summary = {
        "mode": mode_name,
        "injection": inject_mode,
        "duration": duration,
        "frame_count": frame_count,
        "inject_count": inject_count,
        "accel_samples": len(accel_samples),
        "speed_samples": len(speed_samples),
        "accel_max": max(v for _, v in accel_samples) if accel_samples else 0,
        "speed_max": max(v for _, v in speed_samples) if speed_samples else 0,
        "log_file": log_path,
    }
    summary_path = log_path.replace(".log", "_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    return log_path, accel_samples, speed_samples


def compare_drives(file1, file2):
    """Compare acceleration curves between two drive logs."""
    print(f"Comparing:")
    print(f"  Baseline: {file1}")
    print(f"  Ghost:    {file2}")
    print()

    def load_signals(filepath):
        accel = []
        speed = []
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 3:
                    continue
                try:
                    t = float(parts[0])
                    cid = int(parts[1], 16)
                    data = parts[2:]
                except (ValueError, IndexError):
                    continue

                if cid == 0x118 and len(data) >= 5:
                    val = extract_le(data, 32, 8, 0.4, 0)
                    accel.append((t, val))
                elif cid == 0x318 and len(data) >= 3:
                    val = extract_le(data, 12, 12, 0.05, 0)
                    speed.append((t, val))
        return accel, speed

    accel1, speed1 = load_signals(file1)
    accel2, speed2 = load_signals(file2)

    print(f"{'Metric':<30} {'Baseline':<15} {'Ghost':<15} {'Diff'}")
    print("=" * 75)

    # Peak acceleration pedal
    max_accel1 = max(v for _, v in accel1) if accel1 else 0
    max_accel2 = max(v for _, v in accel2) if accel2 else 0
    print(f"{'Peak pedal position':<30} {max_accel1:<15.1f} {max_accel2:<15.1f}")

    # Peak speed
    max_speed1 = max(v for _, v in speed1) if speed1 else 0
    max_speed2 = max(v for _, v in speed2) if speed2 else 0
    print(f"{'Peak speed (km/h)':<30} {max_speed1:<15.1f} {max_speed2:<15.1f}")

    # Time to reach 20 km/h (find first time speed crosses 20)
    def time_to_speed(speed_data, target):
        for t, v in speed_data:
            if v >= target:
                return t
        return None

    t20_1 = time_to_speed(speed1, 20)
    t20_2 = time_to_speed(speed2, 20)
    if t20_1 and t20_2:
        diff = t20_2 - t20_1
        print(f"{'Time to 20 km/h (s)':<30} {t20_1:<15.2f} {t20_2:<15.2f} {diff:+.2f}s")

    t30_1 = time_to_speed(speed1, 30)
    t30_2 = time_to_speed(speed2, 30)
    if t30_1 and t30_2:
        diff = t30_2 - t30_1
        print(f"{'Time to 30 km/h (s)':<30} {t30_1:<15.2f} {t30_2:<15.2f} {diff:+.2f}s")

    t40_1 = time_to_speed(speed1, 40)
    t40_2 = time_to_speed(speed2, 40)
    if t40_1 and t40_2:
        diff = t40_2 - t40_1
        print(f"{'Time to 40 km/h (s)':<30} {t40_1:<15.2f} {t40_2:<15.2f} {diff:+.2f}s")

    # Average acceleration rate (speed change per second during first accel event)
    def avg_accel_rate(speed_data):
        # Find first continuous acceleration (speed increasing)
        started = False
        start_t = None
        start_v = None
        for t, v in speed_data:
            if not started and v > 5:
                started = True
                start_t = t
                start_v = v
            elif started and v < start_v:
                # Speed decreasing, end of acceleration
                if t - start_t > 1:
                    return (v - start_v) / (t - start_t)
                break
            elif started:
                start_v_end = v
                end_t = t
        if started and start_t:
            return (start_v_end - start_v) / (end_t - start_t) if end_t > start_t else 0
        return 0

    # Acceleration timeline comparison
    print(f"\n--- ACCELERATION COMPARISON ---")
    print(f"{'Time':<10} {'Baseline Speed':<20} {'Ghost Speed':<20} {'Difference'}")
    print("-" * 65)

    # Sample at 1-second intervals
    max_time = min(
        max(t for t, _ in speed1) if speed1 else 0,
        max(t for t, _ in speed2) if speed2 else 0
    )

    for target_t in range(0, int(max_time) + 1, 2):
        # Find closest speed to this time
        v1 = None
        v2 = None
        for t, v in speed1:
            if abs(t - target_t) < 1:
                v1 = v
                break
        for t, v in speed2:
            if abs(t - target_t) < 1:
                v2 = v
                break
        if v1 is not None and v2 is not None:
            diff = v2 - v1
            print(f"{target_t:<10} {v1:<20.1f} {v2:<20.1f} {diff:+.1f} km/h")


def find_port():
    for p in serial.tools.list_ports.comports():
        if any(x in p.description.upper() for x in ["OBD", "STN", "ELM", "BLUETOOTH", "STANDARD SERIAL"]):
            return p.device
    return None


def main():
    parser = argparse.ArgumentParser(description="Tesla Ghost Mode with Logging")
    parser.add_argument("--port", "-p", help="Serial port")
    parser.add_argument("--mode", "-m", choices=["baseline", "chill", "standard", "performance", "compare"],
                        default="performance", help="Mode to run")
    parser.add_argument("--duration", "-d", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--file1", help="Baseline log file (for compare mode)")
    parser.add_argument("--file2", help="Ghost log file (for compare mode)")
    args = parser.parse_args()

    if args.mode == "compare":
        if not args.file1 or not args.file2:
            print("Compare mode requires --file1 and --file2")
            sys.exit(1)
        compare_drives(args.file1, args.file2)
        return

    port = args.port or find_port()
    if not port:
        print("No OBDLink adapter found!")
        sys.exit(1)

    ser = serial.Serial(port, DEFAULT_BAUD, timeout=1)
    init_adapter(ser)

    if args.mode == "baseline":
        # Record without injection
        record_drive(ser, args.duration, "baseline", inject_mode=None)
    else:
        # Record with injection
        record_drive(ser, args.duration, args.mode, inject_mode=args.mode)

    ser.close()


if __name__ == "__main__":
    main()
