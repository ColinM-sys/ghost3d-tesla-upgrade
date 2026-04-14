"""
Tesla Model 3 Live CAN Sniffer
Shows real-time CAN data with change detection.
Highlights signals that change when you press pedals, turn wheel, etc.

Usage:
    python live_sniffer.py                  # auto-detect port
    python live_sniffer.py --port COM5      # specific port
    python live_sniffer.py --mode baseline  # record baseline (car on, no input)
    python live_sniffer.py --mode diff      # show only changes from baseline
"""
import serial
import serial.tools.list_ports
import time
import sys
import os
import json
import argparse
from datetime import datetime
from collections import defaultdict


DEFAULT_BAUD = 115200
BASELINE_FILE = "captures/baseline.json"

# Known Tesla Model 3 CAN IDs
KNOWN_IDS = {
    "108": "DI_torque1",
    "118": "DI_torque2",
    "129": "DI_speed",
    "132": "HVBatt_status",
    "186": "DI_torque3",
    "1D5": "VCLEFT_switchStatus",
    "1D8": "DI_state",
    "201": "BMS_status",
    "212": "BMS_thermal",
    "241": "VCRIGHT_switchStatus",
    "257": "UI_speed",
    "261": "DI_systemStatus",
    "266": "DI_gradeEst",
    "292": "BMS_contactorState",
    "2B3": "SteeringAngle",
    "2E1": "VCLEFT_doorStatus",
    "2E3": "VCRIGHT_doorStatus",
    "312": "BMS_kwhCounter",
    "318": "ESP_status",
    "321": "VCFRONT_lighting",
    "332": "ESP_brakeTorque",
    "336": "DI_odometer",
    "352": "BMS_packVoltage",
    "376": "DI_temperature",
    "388": "Wheel_speed_FL",
    "389": "Wheel_speed_FR",
    "38A": "Wheel_speed_RL",
    "38B": "Wheel_speed_RR",
    "3B6": "VCFRONT_status",
    "3F5": "Ambient_temp",
    "528": "UI_powertrainControl",
}


def find_obdlink_port():
    for p in serial.tools.list_ports.comports():
        if any(x in p.description.upper() for x in ["OBD", "STN", "ELM", "BLUETOOTH", "STANDARD SERIAL"]):
            return p.device
    return None


def send_cmd(ser, cmd, wait=0.5):
    ser.write((cmd + "\r").encode())
    time.sleep(wait)
    return ser.read(ser.in_waiting).decode(errors="ignore").strip()


def init_adapter(ser):
    """Initialize OBDLink for raw CAN monitoring."""
    cmds = [
        ("ATZ", 2), ("ATE0", 0.5), ("ATL1", 0.5),
        ("ATH1", 0.5), ("ATS1", 0.5), ("ATSP6", 0.5),
        ("ATCAF0", 0.5), ("ATR1", 0.5),
    ]
    print("Initializing OBDLink MX+...")
    for cmd, wait in cmds:
        resp = send_cmd(ser, cmd, wait)
        print(f"  {cmd} -> {resp}")
    print()


def parse_can_frame(line):
    """Parse a raw CAN frame line into ID and data bytes."""
    line = line.strip()
    if not line or line.startswith(">") or "SEARCHING" in line or "NO DATA" in line:
        return None, None

    # Remove spaces and try to parse
    # Format varies: "1D8 00 11 22 33 44 55 66 77" or "1D800112233445566 77"
    parts = line.split()
    if len(parts) < 2:
        return None, None

    can_id = parts[0].upper()
    # Validate it looks like a hex CAN ID (3 chars for 11-bit)
    if not all(c in "0123456789ABCDEF" for c in can_id):
        return None, None
    if len(can_id) > 8:
        return None, None

    data_bytes = parts[1:]
    return can_id, data_bytes


def record_baseline(ser, duration=15):
    """Record baseline CAN data (car on, no driver input)."""
    print(f"Recording baseline for {duration}s...")
    print("DO NOT touch pedals, steering, or any controls!\n")

    ser.write(b"STMA\r")
    time.sleep(0.3)

    baseline = {}  # {can_id: {byte_index: set_of_values_seen}}
    start = time.time()
    frame_count = 0

    try:
        while time.time() - start < duration:
            if ser.in_waiting:
                line = ser.readline().decode(errors="ignore").strip()
                can_id, data = parse_can_frame(line)
                if can_id and data:
                    if can_id not in baseline:
                        baseline[can_id] = {}
                    for i, byte_val in enumerate(data):
                        if i not in baseline[can_id]:
                            baseline[can_id][i] = set()
                        baseline[can_id][i].add(byte_val.upper())
                    frame_count += 1
                    if frame_count % 500 == 0:
                        elapsed = time.time() - start
                        print(f"  {frame_count} frames, {len(baseline)} unique IDs ({elapsed:.0f}s)")
    except KeyboardInterrupt:
        pass

    # Stop monitoring
    ser.write(b"\r")
    time.sleep(0.5)
    ser.read(ser.in_waiting)

    # Convert sets to lists for JSON
    baseline_json = {}
    for can_id, bytes_dict in baseline.items():
        baseline_json[can_id] = {}
        for byte_idx, values in bytes_dict.items():
            baseline_json[can_id][str(byte_idx)] = list(values)

    os.makedirs("captures", exist_ok=True)
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline_json, f, indent=2)

    print(f"\nBaseline recorded: {frame_count} frames, {len(baseline)} CAN IDs")
    print(f"Saved to {BASELINE_FILE}")
    return baseline_json


def load_baseline():
    """Load baseline data."""
    if not os.path.exists(BASELINE_FILE):
        print(f"No baseline found at {BASELINE_FILE}")
        print("Run with --mode baseline first!")
        sys.exit(1)
    with open(BASELINE_FILE) as f:
        return json.load(f)


def live_diff(ser, baseline, duration=60):
    """Monitor CAN bus and highlight changes from baseline."""
    print(f"Live diff mode for {duration}s")
    print("Press pedals, turn wheel - changes will be highlighted!\n")
    print(f"{'Time':<8} {'CAN ID':<8} {'Name':<25} {'Byte':<6} {'Baseline':<20} {'NOW':<10} {'Delta'}")
    print("=" * 100)

    ser.write(b"STMA\r")
    time.sleep(0.3)

    start = time.time()
    seen_changes = set()  # Track unique changes to avoid spam
    frame_count = 0
    change_log = []

    try:
        while time.time() - start < duration:
            if ser.in_waiting:
                line = ser.readline().decode(errors="ignore").strip()
                can_id, data = parse_can_frame(line)
                if can_id and data:
                    frame_count += 1

                    if can_id in baseline:
                        for i, byte_val in enumerate(data):
                            byte_val = byte_val.upper()
                            str_i = str(i)
                            if str_i in baseline[can_id]:
                                baseline_vals = set(baseline[can_id][str_i])
                                if byte_val not in baseline_vals:
                                    change_key = f"{can_id}:{i}"
                                    elapsed = time.time() - start
                                    name = KNOWN_IDS.get(can_id, "???")

                                    # Calculate numeric delta from nearest baseline value
                                    try:
                                        curr_int = int(byte_val, 16)
                                        base_ints = [int(v, 16) for v in baseline_vals]
                                        nearest = min(base_ints, key=lambda x: abs(x - curr_int))
                                        delta = curr_int - nearest
                                        delta_str = f"{delta:+d}"
                                    except ValueError:
                                        delta_str = "?"

                                    base_str = ",".join(sorted(baseline_vals)[:3])
                                    if len(baseline_vals) > 3:
                                        base_str += "..."

                                    entry = {
                                        "time": round(elapsed, 2),
                                        "can_id": can_id,
                                        "name": name,
                                        "byte": i,
                                        "baseline": list(baseline_vals),
                                        "value": byte_val,
                                        "delta": delta_str,
                                    }
                                    change_log.append(entry)

                                    # Only print first occurrence + periodic updates
                                    if change_key not in seen_changes or frame_count % 200 == 0:
                                        seen_changes.add(change_key)
                                        marker = " *** NEW ***" if change_key not in seen_changes else ""
                                        print(f"{elapsed:<8.2f} {can_id:<8} {name:<25} [{i}]   {base_str:<20} {byte_val:<10} {delta_str}{marker}")

                    else:
                        # Entirely new CAN ID not in baseline!
                        name = KNOWN_IDS.get(can_id, "???")
                        elapsed = time.time() - start
                        new_key = f"NEW:{can_id}"
                        if new_key not in seen_changes:
                            seen_changes.add(new_key)
                            data_str = " ".join(data)
                            print(f"{elapsed:<8.2f} {can_id:<8} {name:<25} *** ENTIRELY NEW CAN ID ***  data: {data_str}")
                            change_log.append({
                                "time": round(elapsed, 2),
                                "can_id": can_id,
                                "name": name,
                                "new_id": True,
                                "data": data,
                            })

    except KeyboardInterrupt:
        print("\nStopped by user.")

    # Stop monitoring
    ser.write(b"\r")
    time.sleep(0.5)
    ser.read(ser.in_waiting)

    # Save change log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"captures/diff_{timestamp}.json"
    with open(log_file, "w") as f:
        json.dump(change_log, f, indent=2)

    # Summary
    changed_ids = set()
    for entry in change_log:
        changed_ids.add(entry["can_id"])

    print(f"\n{'=' * 60}")
    print(f"Summary: {len(change_log)} changes detected across {len(changed_ids)} CAN IDs")
    print(f"Changed IDs: {', '.join(sorted(changed_ids))}")
    print(f"Change log saved to {log_file}")

    # Highlight likely input signals
    input_candidates = []
    for cid in changed_ids:
        name = KNOWN_IDS.get(cid, "UNKNOWN")
        changes = [e for e in change_log if e["can_id"] == cid]
        input_candidates.append((cid, name, len(changes)))

    input_candidates.sort(key=lambda x: x[2], reverse=True)
    print(f"\nMost active changed signals (likely inputs):")
    for cid, name, count in input_candidates[:10]:
        print(f"  0x{cid}: {name} ({count} changes)")


def live_monitor(ser, duration=60):
    """Simple live monitor showing all CAN traffic with labels."""
    print(f"Live monitor for {duration}s - showing all traffic\n")
    print(f"{'Time':<8} {'CAN ID':<8} {'Name':<25} {'Data'}")
    print("-" * 80)

    ser.write(b"STMA\r")
    time.sleep(0.3)

    start = time.time()
    last_values = {}
    frame_count = 0

    try:
        while time.time() - start < duration:
            if ser.in_waiting:
                line = ser.readline().decode(errors="ignore").strip()
                can_id, data = parse_can_frame(line)
                if can_id and data:
                    frame_count += 1
                    data_str = " ".join(data)
                    name = KNOWN_IDS.get(can_id, "")

                    # Only print when value changes for this ID
                    prev = last_values.get(can_id)
                    if prev != data_str:
                        last_values[can_id] = data_str
                        elapsed = time.time() - start
                        changed = " <-- CHANGED" if prev is not None else ""
                        print(f"{elapsed:<8.2f} {can_id:<8} {name:<25} {data_str}{changed}")
    except KeyboardInterrupt:
        print("\nStopped.")

    ser.write(b"\r")
    time.sleep(0.5)
    ser.read(ser.in_waiting)
    print(f"\n{frame_count} total frames, {len(last_values)} unique IDs")


def main():
    parser = argparse.ArgumentParser(description="Tesla Model 3 Live CAN Sniffer")
    parser.add_argument("--port", "-p", help="Serial port")
    parser.add_argument("--mode", "-m", choices=["monitor", "baseline", "diff"],
                        default="monitor", help="Mode: monitor (live view), baseline (record idle), diff (show changes)")
    parser.add_argument("--duration", "-d", type=int, default=60, help="Duration in seconds")
    args = parser.parse_args()

    port = args.port or find_obdlink_port()
    if not port:
        print("No OBDLink adapter found. Pair via Bluetooth first, then run scan_ports.py")
        sys.exit(1)

    print(f"Connecting to {port}...")
    ser = serial.Serial(port, DEFAULT_BAUD, timeout=1)
    init_adapter(ser)

    if args.mode == "baseline":
        record_baseline(ser, args.duration)
    elif args.mode == "diff":
        baseline = load_baseline()
        live_diff(ser, baseline, args.duration)
    else:
        live_monitor(ser, args.duration)

    ser.close()


if __name__ == "__main__":
    main()
