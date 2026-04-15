"""
Ghost3D - Tesla Performance Controller
Combined ghost mode injection + CAN reading + performance dashboard.
Single app that does everything. Works offline.

Usage:
    python ghost3d.py --port COM5
    Open http://localhost:9090 in browser
"""
import serial
import serial.tools.list_ports
import time
import threading
import json
import sys
import os
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

DEFAULT_BAUD = 115200
HTTP_PORT = 9090

MODE_BYTES = {
    "chill": 0x3F,
    "standard": 0xBF,
    "performance": 0x7F,
}

# Traction control modes for CAN ID 0x293 (659 decimal)
# UI_tractionControlMode: bit 2, 3 bits
# Also UI_trackStabilityAssist: bit 16, 8 bits (0-100%, scale 0.5)
TC_MODES = {
    "normal": 0,
    "slip_start": 1,
    "dev1": 2,
    "dev2": 3,
    "rolls": 4,
    "dyno": 5,       # Full TC off — drift mode
    "offroad": 6,
}

SIGNALS = {
    0x118: {
        "DI_accelPedalPos": (32, 8, 0.4, 0, "%"),
        "DI_brakePedalState": (19, 2, 1, 0, ""),
    },
    0x129: {
        "SteeringAngle": (16, 14, 0.1, -819.2, "deg"),
        "SteeringSpeed": (32, 14, 0.5, -4096, "d/s"),
    },
    0x132: {
        "HVBatt_SOC_raw": (0, 10, 0.1, 0, "%"),
    },
    0x252: {
        "BMS_packVoltage": (0, 16, 0.01, 0, "V"),
    },
    0x261: {
        "DI_elecPower": (0, 11, 0.5, -512, "kW"),
    },
    0x292: {
        "BMS_packCurrent": (0, 16, 0.1, -1000, "A"),
    },
    0x2B3: {
        "EPAS_steeringAngle": (0, 16, 0.1, -819.2, "deg"),
    },
    0x318: {
        "ESP_vehicleSpeed": (12, 12, 0.05, 0, "km/h"),
    },
    0x334: {
        "UI_pedalMap": (5, 2, 1, 0, ""),
    },
    0x388: {"WheelSpeed_FL": (0, 16, 0.01, 0, "km/h")},
    0x389: {"WheelSpeed_FR": (0, 16, 0.01, 0, "km/h")},
    0x38A: {"WheelSpeed_RL": (0, 16, 0.01, 0, "km/h")},
    0x38B: {"WheelSpeed_RR": (0, 16, 0.01, 0, "km/h")},
    0x201: {
        "BMS_packTempMax": (0, 8, 0.5, -40, "C"),
        "BMS_packTempMin": (8, 8, 0.5, -40, "C"),
    },
    0x2E1: {
        "VCLEFT_frontDoorState": (0, 2, 1, 0, ""),
        "VCLEFT_rearDoorState": (2, 2, 1, 0, ""),
    },
    0x3F5: {"AmbientTemp": (0, 8, 0.5, -40, "C")},
    0x376: {
        "DI_inverterTemp": (0, 8, 1, -40, "C"),
        "DI_statorTemp": (8, 8, 1, -40, "C"),
    },
    0x293: {"UI_steeringTuneRequest": (0, 2, 1, 0, "")},
}

PEDAL_MAP_NAMES = {0: "Chill", 1: "Standard", 2: "Performance"}
BRAKE_STATE_NAMES = {0: "OFF", 1: "ON", 2: "INVALID"}


def extract_le(data_bytes, start_bit, bit_length, scale, offset):
    try:
        byte_vals = [int(b, 16) for b in data_bytes]
        while len(byte_vals) < 8:
            byte_vals.append(0)
        raw_val = 0
        for i, bv in enumerate(byte_vals):
            raw_val |= (bv << (i * 8))
        mask = (1 << bit_length) - 1
        extracted = (raw_val >> start_bit) & mask
        return round(extracted * scale + offset, 3)
    except (ValueError, IndexError):
        return None


def parse_frame(line):
    line = line.strip()
    if not line or line.startswith(">") or line.startswith("#"):
        return None, None
    if any(x in line for x in ["STOPPED", "ERROR", "BUFFER", "SEARCHING", "NO DATA"]):
        return None, None
    parts = line.split()
    if len(parts) < 2:
        return None, None
    cid = parts[0].upper()
    if not all(c in "0123456789ABCDEF" for c in cid) or len(cid) > 8:
        return None, None
    try:
        return int(cid, 16), parts[1:]
    except ValueError:
        return None, None


class Ghost3D:
    def __init__(self, port):
        self.port = port
        self.ser = None
        self.connected = False
        self.lock = threading.Lock()

        # CAN read state
        self.state = {}
        self.frame_count = 0
        self.unique_ids = set()
        self.start_time = None

        # Ghost mode state
        self.ghost_mode = None
        self.inject_count = 0
        self.ghost_start = None

        # Drift mode state
        self.drift_mode = False
        self.tc_mode = "normal"

        # Colin mode state (max everything)
        self.colin_mode = False

        # Logging
        self.log_file = None

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, DEFAULT_BAUD, timeout=1)
            time.sleep(0.5)
            for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5),
                              ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
                self.ser.write((cmd + "\r").encode())
                time.sleep(wait)
                self.ser.read(self.ser.in_waiting)
            self.connected = True
            self.start_time = time.time()
            print(f"Connected to {self.port}")
        except Exception as e:
            print(f"Connection failed: {e}")
            self.connected = False

    def start_log(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("captures", exist_ok=True)
        path = f"captures/ghost3d_{ts}.log"
        self.log_file = open(path, "w")
        self.log_file.write(f"# Ghost3D Recording - {datetime.now().isoformat()}\n\n")
        print(f"Logging to {path}")

    def set_ghost(self, mode):
        if mode == "off" or mode is None:
            self.ghost_mode = None
            self.inject_count = 0
            self.ghost_start = None
            self.drift_mode = False
            self.colin_mode = False
            self.tc_mode = "normal"
            print("ALL MODES OFF")
        elif mode in MODE_BYTES:
            self.ghost_mode = mode
            self.inject_count = 0
            self.ghost_start = time.time()
            print(f"Ghost mode: {mode.upper()}")

    def set_drift(self, enabled):
        self.drift_mode = enabled
        if enabled:
            self.ghost_mode = "performance"
            self.tc_mode = "dyno"
            self.ghost_start = time.time() if not self.ghost_start else self.ghost_start
            print("DRIFT MODE ON — Performance + TC Off")
        else:
            self.tc_mode = "normal"
            # Don't turn off ghost mode — let user control that separately
            print("DRIFT MODE OFF — TC restored")

    def set_colin(self, enabled):
        self.colin_mode = enabled
        if enabled:
            self.ghost_mode = "performance"
            self.tc_mode = "dyno"
            self.drift_mode = True
            self.ghost_start = time.time() if not self.ghost_start else self.ghost_start
            print("COLIN MODE ACTIVATED — MAX POWER + TC OFF + TORQUE OVERRIDE")
        else:
            self.colin_mode = False
            self.drift_mode = False
            self.ghost_mode = None
            self.tc_mode = "normal"
            self.inject_count = 0
            self.ghost_start = None
            print("COLIN MODE OFF — all reverted")

    def set_tc(self, mode):
        if mode in TC_MODES:
            self.tc_mode = mode
            print(f"Traction control: {mode.upper()}")

    def honk(self):
        if not self.connected:
            return
        with self.lock:
            try:
                self.ser.write(b"ATSH 273\r")
                time.sleep(0.1)
                self.ser.read(self.ser.in_waiting)
                self.ser.write(b"00 00 00 00 00 00 00 20\r")
                time.sleep(0.2)
                self.ser.read(self.ser.in_waiting)
            except Exception:
                pass

    def _inject_ghost(self):
        if not self.connected:
            return
        has_ghost = self.ghost_mode is not None
        has_tc = self.tc_mode != "normal"

        if not has_ghost and not has_tc:
            return

        try:
            counter = self.inject_count % 256
            b7 = (counter * 16) & 0xFF
            b8 = (counter * 4) & 0xFF

            # Inject pedal map (ghost mode)
            if has_ghost:
                mode_byte = MODE_BYTES[self.ghost_mode]
                self.ser.write(b"ATSH 334\r")
                time.sleep(0.02)
                self.ser.read(self.ser.in_waiting)
                # Real frame: XX 3F 14 80 FC 07 [counter|4] [(counter+D)<<4]
                # Byte 0: pedal map in bits 5-6
                # Byte 6: high nibble = counter (0-15), low nibble = 4
                # Byte 7: high nibble = (counter + 0xD) mod 16, low nibble = 0
                cnt = counter & 0xF
                chk6 = (cnt << 4) | 0x04
                chk7 = (((cnt + 0xD) & 0xF) << 4)
                frame = f"{mode_byte:02X} 3F 14 80 FC 07 {chk6:02X} {chk7:02X}"
                self.ser.write((frame + "\r").encode())
                time.sleep(0.02)
                self.ser.read(self.ser.in_waiting)

            # Inject traction control mode
            if has_tc:
                tc_val = TC_MODES[self.tc_mode]
                tc_byte0 = (tc_val << 2) & 0xFF
                stability = 0 if self.drift_mode else 200
                self.ser.write(b"ATSH 293\r")
                time.sleep(0.02)
                self.ser.read(self.ser.in_waiting)
                frame = f"{tc_byte0:02X} 00 {stability:02X} 00 00 00 {b7:02X} {b8:02X}"
                self.ser.write((frame + "\r").encode())
                time.sleep(0.02)
                self.ser.read(self.ser.in_waiting)

            # Colin Mode: override power and torque limits
            if self.colin_mode:
                # UI_systemPowerLimit: CAN ID 0x334, bit 0, 5 bits, scale 20, offset 20
                # Max value = 31 → 31*20+20 = 640 kW
                # UI_systemTorqueLimit: bit 8, 6 bits, scale 100, offset 4000
                # Max value = 63 → 63*100+4000 = 10300 Nm
                # These are on the SAME CAN ID as pedalMap (0x334)
                # So we need to combine them into one frame
                # Pedal map is bit 5, 2 bits
                # Power limit is bit 0, 5 bits = 31 (max)
                # Torque limit is bit 8, 6 bits = 63 (max)
                power_bits = 31  # max power: 640kW
                torque_bits = 63  # max torque: 10300Nm
                pedal_bits = 2   # performance

                # Build byte 0: bits 0-4 = power (31), bits 5-6 = pedal (2)
                byte0 = (power_bits & 0x1F) | ((pedal_bits & 0x03) << 5)
                # Build byte 1: bits 0-5 = torque (63)
                byte1 = torque_bits & 0x3F

                self.ser.write(b"ATSH 334\r")
                time.sleep(0.02)
                self.ser.read(self.ser.in_waiting)
                frame = f"{byte0:02X} {byte1:02X} 14 80 FC 07 {b7:02X} {b8:02X}"
                self.ser.write((frame + "\r").encode())
                time.sleep(0.02)
                self.ser.read(self.ser.in_waiting)

            self.inject_count += 1
        except Exception:
            pass

    def _read_burst(self, duration=0.15):
        """Read CAN data for a short burst then cleanly stop."""
        if not self.connected:
            return
        try:
            # Reinit for reading
            self.ser.write(b"ATSP6\r")
            time.sleep(0.05)
            self.ser.read(self.ser.in_waiting)
            self.ser.write(b"ATCAF0\r")
            time.sleep(0.05)
            self.ser.read(self.ser.in_waiting)
            self.ser.write(b"ATH1\r")
            time.sleep(0.05)
            self.ser.read(self.ser.in_waiting)
            self.ser.write(b"ATS1\r")
            time.sleep(0.05)
            self.ser.read(self.ser.in_waiting)

            # Start monitor
            self.ser.write(b"STMA\r")
            time.sleep(0.02)
            end = time.time() + duration
            while time.time() < end:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    can_id, data = parse_frame(line)
                    if can_id is not None and data is not None:
                        self.frame_count += 1
                        self.unique_ids.add(can_id)
                        elapsed = time.time() - self.start_time

                        if self.log_file:
                            self.log_file.write(f"{elapsed:.4f} {can_id:03X} {' '.join(data)}\n")

                        if can_id in SIGNALS:
                            with self.lock:
                                for sig_name, params in SIGNALS[can_id].items():
                                    start, length, scale, offset, unit = params
                                    val = extract_le(data, start, length, scale, offset)
                                    if val is not None:
                                        display = val
                                        if sig_name == "UI_pedalMap":
                                            display = PEDAL_MAP_NAMES.get(int(val), val)
                                        elif sig_name == "DI_brakePedalState":
                                            display = BRAKE_STATE_NAMES.get(int(val), val)
                                        self.state[sig_name] = {
                                            "value": val,
                                            "display": str(display),
                                            "unit": unit,
                                            "can_id": f"{can_id:03X}",
                                            "time": time.time(),
                                        }
                else:
                    time.sleep(0.005)
            # Stop monitor and flush completely
            self.ser.write(b"\r")
            time.sleep(0.15)
            self.ser.read(self.ser.in_waiting)
            time.sleep(0.05)
            self.ser.read(self.ser.in_waiting)
        except serial.SerialException:
            self.connected = False
        except Exception as e:
            print(f"Read error: {e}")

    def run_loop(self):
        """Main loop: alternates between reading CAN and injecting ghost mode."""
        self.start_log()
        print("Main loop started. Reading CAN + injecting ghost mode.\n")

        while True:
            try:
                if not self.connected:
                    time.sleep(1)
                    try:
                        self.ser = serial.Serial(self.port, DEFAULT_BAUD, timeout=1)
                        time.sleep(0.5)
                        for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5),
                                          ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
                            self.ser.write((cmd + "\r").encode())
                            time.sleep(wait)
                            self.ser.read(self.ser.in_waiting)
                        self.connected = True
                        print("Reconnected.")
                    except Exception:
                        continue

                # Always read a short burst
                self._read_burst(0.2)

                # Then inject if ghost mode active
                if self.ghost_mode is not None or self.tc_mode != "normal":
                    with self.lock:
                        self._inject_ghost()
                        self._inject_ghost()
                        self._inject_ghost()

                # Flush log periodically
                if self.log_file and self.frame_count % 500 == 0:
                    self.log_file.flush()

            except Exception as e:
                print(f"Loop error: {e}")
                time.sleep(0.5)

    def get_state(self):
        with self.lock:
            uptime = time.time() - self.start_time if self.start_time else 0
            fps = self.frame_count / uptime if uptime > 0 else 0
            ghost_uptime = int(time.time() - self.ghost_start) if self.ghost_start and self.ghost_mode else 0
            return {
                "signals": dict(self.state),
                "frame_count": self.frame_count,
                "unique_ids": len(self.unique_ids),
                "uptime": round(uptime, 1),
                "fps": round(fps, 1),
                "connected": self.connected,
                "ghost_mode": self.ghost_mode,
                "inject_count": self.inject_count,
                "ghost_uptime": ghost_uptime,
                "inject_rate": round(self.inject_count / ghost_uptime, 1) if ghost_uptime > 0 else 0,
                "drift_mode": self.drift_mode,
                "tc_mode": self.tc_mode,
                "colin_mode": self.colin_mode,
            }


class Handler(BaseHTTPRequestHandler):
    controller = None

    def do_GET(self):
        if self.path == "/api/state":
            state = self.controller.get_state()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(state).encode())
        elif self.path == "/" or self.path == "/index.html":
            self._serve_file("performance_dash.html")
        elif self.path.startswith("/"):
            fname = self.path.lstrip("/")
            fpath = Path(__file__).parent / fname
            if fpath.exists():
                self._serve_file(fname)
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_file(self, filename):
        fpath = Path(__file__).parent / filename
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(fpath.read_bytes())

    def do_POST(self):
        if self.path == "/api/mode":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            mode = body.get("mode", "off")
            self.controller.set_ghost(mode)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.controller.get_state()).encode())
        elif self.path == "/api/honk":
            self.controller.honk()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif self.path == "/api/drift":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            enabled = body.get("enabled", False)
            self.controller.set_drift(enabled)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.controller.get_state()).encode())
        elif self.path == "/api/colin":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            enabled = body.get("enabled", False)
            self.controller.set_colin(enabled)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.controller.get_state()).encode())
        elif self.path == "/api/tc":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            mode = body.get("mode", "normal")
            self.controller.set_tc(mode)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.controller.get_state()).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def find_port():
    for p in serial.tools.list_ports.comports():
        if any(x in p.description.upper() for x in ["OBD", "STN", "ELM", "BLUETOOTH", "STANDARD SERIAL"]):
            return p.device
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ghost3D - Tesla Performance Controller")
    parser.add_argument("--port", "-p", help="Serial port")
    parser.add_argument("--http", type=int, default=HTTP_PORT)
    args = parser.parse_args()

    port = args.port or find_port()
    if not port:
        print("No OBDLink adapter found!")
        sys.exit(1)

    g = Ghost3D(port)
    g.connect()

    # Start CAN read/write loop
    threading.Thread(target=g.run_loop, daemon=True).start()

    # Start HTTP server
    Handler.controller = g
    httpd = HTTPServer(("0.0.0.0", args.http), Handler)
    print(f"\n{'='*50}")
    print(f"  GHOST3D Tesla Performance Controller")
    print(f"  http://localhost:{args.http}")
    print(f"{'='*50}\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        g.set_ghost(None)
        if g.log_file:
            g.log_file.close()
        httpd.shutdown()
        print("Stopped.")


if __name__ == "__main__":
    main()
