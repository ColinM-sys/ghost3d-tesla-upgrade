"""
Tesla Model 3 CAN Frame Decoder
Parses captured CAN frames and identifies known message IDs.
"""
import sys
from collections import Counter

# Known Tesla Model 3 CAN IDs (partial - community sourced)
KNOWN_IDS = {
    "0x108": ("DI_torque1", "Drive inverter torque info"),
    "0x118": ("DI_torque2", "Drive inverter torque info 2"),
    "0x129": ("DI_speed", "Vehicle speed from drive inverter"),
    "0x132": ("HVBatt_status", "HV Battery status"),
    "0x186": ("DI_torque3", "Torque request/actual"),
    "0x1D5": ("VCLEFT_switchStatus", "Left stalk/switch status"),
    "0x1D8": ("DI_state", "Drive inverter state"),
    "0x201": ("BMS_status", "Battery Management System"),
    "0x212": ("BMS_thermal", "Battery thermal management"),
    "0x241": ("VCRIGHT_switchStatus", "Right stalk/switch status"),
    "0x257": ("UI_speed", "Speed displayed on UI"),
    "0x261": ("DI_systemStatus", "Drive system status"),
    "0x266": ("DI_gradeEst", "Grade estimation"),
    "0x292": ("BMS_contactorState", "Battery contactor state"),
    "0x2B3": ("SteeringAngle", "Steering wheel angle"),
    "0x2E1": ("VCLEFT_doorStatus", "Door status left"),
    "0x2E3": ("VCRIGHT_doorStatus", "Door status right"),
    "0x312": ("BMS_kwhCounter", "Energy counter"),
    "0x318": ("ESP_status", "Electronic stability program"),
    "0x321": ("VCFRONT_lighting", "Lighting status"),
    "0x332": ("ESP_brakeTorque", "Brake torque from ESP"),
    "0x336": ("DI_odometer", "Odometer reading"),
    "0x352": ("BMS_packVoltage", "Pack voltage"),
    "0x376": ("DI_temperature", "Drive inverter temperature"),
    "0x388": ("Wheel_speed_FL", "Front left wheel speed"),
    "0x389": ("Wheel_speed_FR", "Front right wheel speed"),
    "0x38A": ("Wheel_speed_RL", "Rear left wheel speed"),
    "0x38B": ("Wheel_speed_RR", "Rear right wheel speed"),
    "0x3B6": ("VCFRONT_status", "Front body controller status"),
    "0x3F5": ("Ambient_temp", "Outside temperature"),
    "0x528": ("UI_powertrainControl", "Powertrain control from UI"),
}


def decode_capture(filepath):
    """Parse a CAN capture file and show statistics."""
    id_counter = Counter()
    total_frames = 0

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Format: timestamp CAN_ID DATA_BYTES
            parts = line.split(None, 2)
            if len(parts) >= 2:
                can_id = parts[1][:3] if len(parts[1]) >= 3 else parts[1]
                id_counter[can_id] += 1
                total_frames += 1

    print(f"Total frames: {total_frames}")
    print(f"Unique CAN IDs: {len(id_counter)}\n")

    print(f"{'CAN ID':<10} {'Count':<10} {'Name':<25} {'Description'}")
    print("-" * 80)

    for can_id, count in id_counter.most_common():
        hex_id = f"0x{can_id.upper()}"
        if hex_id in KNOWN_IDS:
            name, desc = KNOWN_IDS[hex_id]
            print(f"{hex_id:<10} {count:<10} {name:<25} {desc}")
        else:
            print(f"{hex_id:<10} {count:<10} {'UNKNOWN':<25} (needs identification)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python can_decode.py <capture_file.log>")
        sys.exit(1)
    decode_capture(sys.argv[1])
