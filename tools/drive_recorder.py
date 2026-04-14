"""
Tesla Model 3 Drive Recorder
Records all CAN data to a log file while also serving the dashboard.
Designed to work offline (no WiFi needed) - just needs Bluetooth to OBDLink.
"""
import serial
import serial.tools.list_ports
import time
import json
import threading
import sys
import os
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

DEFAULT_BAUD = 115200
HTTP_PORT = 8080

SIGNALS = {
    0x118: {
        "DI_accelPedalPos": (32, 8, 0.4, 0, "%", "little"),
        "DI_brakePedalState": (19, 2, 1, 0, "", "little"),
    },
    0x129: {
        "SteeringAngle": (16, 14, 0.1, -819.2, "deg", "little"),
        "SteeringSpeed": (32, 14, 0.5, -4096, "d/s", "little"),
    },
    0x132: {
        "HVBatt_SOC_raw": (0, 10, 0.1, 0, "%", "little"),
    },
    0x252: {
        "BMS_packVoltage": (0, 16, 0.01, 0, "V", "little"),
    },
    0x261: {
        "DI_elecPower": (0, 11, 0.5, -512, "kW", "little"),
    },
    0x292: {
        "BMS_packCurrent": (0, 16, 0.1, -1000, "A", "little"),
    },
    0x2B3: {
        "EPAS_steeringAngle": (0, 16, 0.1, -819.2, "deg", "little"),
    },
    0x318: {
        "ESP_vehicleSpeed": (12, 12, 0.05, 0, "km/h", "little"),
    },
    0x334: {
        "UI_pedalMap": (5, 2, 1, 0, "", "little"),
    },
    0x388: {
        "WheelSpeed_FL": (0, 16, 0.01, 0, "km/h", "little"),
    },
    0x389: {
        "WheelSpeed_FR": (0, 16, 0.01, 0, "km/h", "little"),
    },
    0x38A: {
        "WheelSpeed_RL": (0, 16, 0.01, 0, "km/h", "little"),
    },
    0x38B: {
        "WheelSpeed_RR": (0, 16, 0.01, 0, "km/h", "little"),
    },
    0x201: {
        "BMS_packTempMax": (0, 8, 0.5, -40, "C", "little"),
        "BMS_packTempMin": (8, 8, 0.5, -40, "C", "little"),
    },
    0x2E1: {
        "VCLEFT_frontDoorState": (0, 2, 1, 0, "", "little"),
        "VCLEFT_rearDoorState": (2, 2, 1, 0, "", "little"),
    },
    0x3F5: {
        "AmbientTemp": (0, 8, 0.5, -40, "C", "little"),
    },
    0x376: {
        "DI_inverterTemp": (0, 8, 1, -40, "C", "little"),
        "DI_statorTemp": (8, 8, 1, -40, "C", "little"),
    },
    0x293: {
        "UI_steeringTuneRequest": (0, 2, 1, 0, "", "little"),
    },
    0x528: {
        "UI_powertrainControl": (0, 8, 1, 0, "", "little"),
    },
}

PEDAL_MAP_NAMES = {0: "Chill", 1: "Sport", 2: "Performance"}
STEERING_TUNE_NAMES = {0: "Comfort", 1: "Standard", 2: "Sport"}
DOOR_STATE_NAMES = {0: "Closed", 1: "Open", 2: "Opening", 3: "Ajar"}
BRAKE_STATE_NAMES = {0: "OFF", 1: "ON", 2: "INVALID"}


def extract_signal_le(data_bytes, start_bit, bit_length, scale, offset):
    try:
        byte_vals = [int(b, 16) for b in data_bytes]
        while len(byte_vals) < 8:
            byte_vals.append(0)
        raw_val = 0
        for i, bv in enumerate(byte_vals):
            raw_val |= (bv << (i * 8))
        mask = (1 << bit_length) - 1
        extracted = (raw_val >> start_bit) & mask
        value = round(extracted * scale + offset, 3)
        return value
    except (ValueError, IndexError):
        return None


def parse_can_frame(line):
    line = line.strip()
    if not line or line.startswith(">") or "SEARCHING" in line or "NO DATA" in line:
        return None, None
    if "STOPPED" in line or "CAN ERROR" in line or "BUS" in line or "BUFFER" in line:
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
        can_id = int(can_id_str, 16)
    except ValueError:
        return None, None
    return can_id, parts[1:]


class DriveRecorder:
    def __init__(self, port, baud=DEFAULT_BAUD):
        self.port = port
        self.baud = baud
        self.ser = None
        self.running = False
        self.state = {}
        self.raw_frames = {}
        self.frame_count = 0
        self.unique_ids = set()
        self.lock = threading.Lock()
        self.start_time = None
        self.log_file = None
        self.log_writer = None

    def connect(self):
        print(f"Connecting to {self.port}...")
        self.ser = serial.Serial(self.port, self.baud, timeout=1)
        time.sleep(0.5)
        cmds = [
            ("ATZ", 2), ("ATE0", 0.5), ("ATL1", 0.5),
            ("ATH1", 0.5), ("ATS1", 0.5), ("ATSP6", 0.5),
            ("ATCAF0", 0.5),
        ]
        for cmd, wait in cmds:
            self.ser.write((cmd + "\r").encode())
            time.sleep(wait)
            resp = self.ser.read(self.ser.in_waiting).decode(errors="ignore").strip()
            print(f"  {cmd} -> {resp}")
        print("Connected.\n")

    def start_log(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("captures", exist_ok=True)
        log_path = f"captures/drive_{timestamp}.log"
        self.log_file = open(log_path, "w")
        self.log_file.write(f"# Tesla Model 3 Drive Recording\n")
        self.log_file.write(f"# Started: {datetime.now().isoformat()}\n")
        self.log_file.write(f"# Port: {self.port}\n\n")
        print(f"Recording to {log_path}")
        return log_path

    def restart_monitor(self):
        try:
            self.ser.write(b"\r")
            time.sleep(0.5)
            self.ser.read(self.ser.in_waiting)
            time.sleep(0.2)
            self.ser.write(b"STMA\r")
            time.sleep(0.3)
            print(f"  Monitor restarted at frame {self.frame_count}")
        except Exception as e:
            print(f"  Restart failed: {e}")

    def process_frame(self, can_id, data, elapsed):
        self.frame_count += 1
        self.unique_ids.add(can_id)
        can_id_hex = f"{can_id:03X}"

        # Write raw frame to log file
        if self.log_file:
            data_str = " ".join(data)
            self.log_file.write(f"{elapsed:.4f} {can_id_hex} {data_str}\n")
            if self.frame_count % 500 == 0:
                self.log_file.flush()

        with self.lock:
            self.raw_frames[can_id_hex] = {
                "data": " ".join(data),
                "time": time.time(),
            }

            if can_id in SIGNALS:
                for sig_name, params in SIGNALS[can_id].items():
                    start, length, scale, offset, unit, byte_order = params
                    val = extract_signal_le(data, start, length, scale, offset)
                    if val is not None:
                        display_val = val
                        if sig_name == "UI_pedalMap":
                            display_val = PEDAL_MAP_NAMES.get(int(val), val)
                        elif sig_name == "UI_steeringTuneRequest":
                            display_val = STEERING_TUNE_NAMES.get(int(val), val)
                        elif "doorState" in sig_name.lower() or "DoorState" in sig_name:
                            display_val = DOOR_STATE_NAMES.get(int(val), val)
                        elif sig_name == "DI_brakePedalState":
                            display_val = BRAKE_STATE_NAMES.get(int(val), val)

                        self.state[sig_name] = {
                            "value": val,
                            "display": str(display_val),
                            "unit": unit,
                            "can_id": can_id_hex,
                            "time": time.time(),
                        }

    def start_reading(self):
        self.running = True
        self.start_time = time.time()
        log_path = self.start_log()

        self.ser.write(b"STMA\r")
        time.sleep(0.3)

        last_frame_time = time.time()
        last_status = time.time()

        while self.running:
            try:
                now = time.time()

                # Auto-restart if no data for 3 seconds
                if now - last_frame_time > 3:
                    self.restart_monitor()
                    last_frame_time = now

                # Print status every 10 seconds
                if now - last_status > 10:
                    elapsed = now - self.start_time
                    fps = self.frame_count / elapsed if elapsed > 0 else 0
                    print(f"  [{elapsed:.0f}s] {self.frame_count} frames, {len(self.unique_ids)} IDs, {fps:.0f} FPS")
                    last_status = now

                if self.ser.in_waiting:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    can_id, data = parse_can_frame(line)
                    if can_id is not None and data is not None:
                        elapsed = now - self.start_time
                        self.process_frame(can_id, data, elapsed)
                        last_frame_time = now
                else:
                    time.sleep(0.01)

            except serial.SerialException as e:
                print(f"Serial error: {e}")
                time.sleep(2)
                try:
                    self.ser.close()
                    self.ser = serial.Serial(self.port, self.baud, timeout=1)
                    time.sleep(1)
                    self.ser.write(b"STMA\r")
                    time.sleep(0.3)
                    last_frame_time = time.time()
                    print("Reconnected.")
                except Exception:
                    pass
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(0.1)

        # Cleanup
        if self.log_file:
            self.log_file.flush()
            self.log_file.close()
            print(f"\nRecording saved: {self.frame_count} frames, {len(self.unique_ids)} IDs")

    def stop(self):
        self.running = False
        if self.ser:
            try:
                self.ser.write(b"\r")
                time.sleep(0.3)
                self.ser.close()
            except Exception:
                pass

    def get_state(self):
        with self.lock:
            uptime = time.time() - self.start_time if self.start_time else 0
            fps = self.frame_count / uptime if uptime > 0 else 0
            return {
                "signals": dict(self.state),
                "frame_count": self.frame_count,
                "unique_ids": len(self.unique_ids),
                "raw_frame_count": len(self.raw_frames),
                "uptime": round(uptime, 1),
                "fps": round(fps, 1),
            }


class DashboardHandler(SimpleHTTPRequestHandler):
    recorder = None

    def do_GET(self):
        if self.path == "/api/state":
            state = self.recorder.get_state() if self.recorder else {}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(state).encode())
        elif self.path == "/" or self.path == "/index.html":
            dashboard_path = Path(__file__).parent / "dashboard.html"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(dashboard_path.read_bytes())
        elif self.path == "/performance" or self.path == "/performance_dash.html":
            perf_path = Path(__file__).parent / "performance_dash.html"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(perf_path.read_bytes())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def find_obdlink_port():
    for p in serial.tools.list_ports.comports():
        if any(x in p.description.upper() for x in ["OBD", "STN", "ELM", "BLUETOOTH", "STANDARD SERIAL"]):
            return p.device
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Tesla Drive Recorder")
    parser.add_argument("--port", "-p", help="Serial port")
    parser.add_argument("--http", type=int, default=HTTP_PORT, help="HTTP port")
    args = parser.parse_args()

    port = args.port or find_obdlink_port()
    if not port:
        print("No OBDLink adapter found!")
        sys.exit(1)

    recorder = DriveRecorder(port, DEFAULT_BAUD)
    recorder.connect()

    # Start CAN reading in background
    read_thread = threading.Thread(target=recorder.start_reading, daemon=True)
    read_thread.start()

    # Start HTTP server
    DashboardHandler.recorder = recorder
    httpd = HTTPServer(("0.0.0.0", args.http), DashboardHandler)
    print(f"Dashboard: http://localhost:{args.http}")
    print(f"Remote:    http://100.113.229.71:{args.http}")
    print("Recording all CAN data to captures/ folder")
    print("Drive around! Data is saved even without WiFi.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
        recorder.stop()
        httpd.shutdown()


if __name__ == "__main__":
    main()
