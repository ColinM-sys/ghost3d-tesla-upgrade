"""
Tesla Ghost Mode UI
Runs a local web server on the laptop with buttons to control ghost mode.
Works offline - no internet needed. Just open http://localhost:9090 in browser.
"""
import serial
import serial.tools.list_ports
import time
import threading
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

DEFAULT_BAUD = 115200
HTTP_PORT = 9090

MODE_BYTES = {
    "chill": 0x9F,
    "standard": 0xBF,
    "performance": 0xDF,
}

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ghost3D Tesla</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #0a0a0f;
    color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px;
    min-height: 100vh;
}
h1 {
    color: #00d4ff;
    font-size: 28px;
    letter-spacing: 3px;
    margin-bottom: 5px;
}
.subtitle { color: #666; font-size: 14px; margin-bottom: 30px; }
.status-box {
    background: #111118;
    border: 2px solid #222;
    border-radius: 12px;
    padding: 20px;
    width: 100%;
    max-width: 400px;
    text-align: center;
    margin-bottom: 20px;
}
.status-label { color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
.status-value {
    font-size: 36px;
    font-weight: bold;
    font-family: 'Consolas', monospace;
    margin: 5px 0;
}
.status-value.off { color: #666; }
.status-value.chill { color: #00aaff; }
.status-value.standard { color: #ffffff; }
.status-value.performance { color: #ff4444; }
.status-value.connected { color: #00ff88; }
.status-value.disconnected { color: #ff4444; }

.buttons {
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 100%;
    max-width: 400px;
}
button {
    padding: 18px;
    font-size: 18px;
    font-weight: bold;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    letter-spacing: 1px;
    transition: transform 0.1s, box-shadow 0.2s;
}
button:active { transform: scale(0.97); }
.btn-performance {
    background: linear-gradient(135deg, #cc0000, #ff4444);
    color: white;
    box-shadow: 0 4px 20px rgba(255, 0, 0, 0.3);
}
.btn-performance:hover { box-shadow: 0 4px 30px rgba(255, 0, 0, 0.5); }
.btn-standard {
    background: linear-gradient(135deg, #333, #555);
    color: white;
}
.btn-chill {
    background: linear-gradient(135deg, #0066aa, #0088dd);
    color: white;
}
.btn-stop {
    background: linear-gradient(135deg, #222, #333);
    color: #888;
    border: 1px solid #444;
}
.btn-honk {
    background: linear-gradient(135deg, #aa8800, #ddaa00);
    color: white;
}
.stats {
    margin-top: 20px;
    width: 100%;
    max-width: 400px;
    background: #111118;
    border-radius: 10px;
    padding: 15px;
    border: 1px solid #222;
    font-family: 'Consolas', monospace;
    font-size: 13px;
}
.stat-row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    border-bottom: 1px solid #1a1a22;
}
.stat-label { color: #888; }
.stat-value { color: #fff; }
.warning {
    margin-top: 15px;
    color: #ff6644;
    font-size: 11px;
    text-align: center;
    max-width: 400px;
}
</style>
</head>
<body>

<h1>GHOST3D</h1>
<p class="subtitle">Tesla Drive Mode Controller</p>

<div class="status-box">
    <div class="status-label">Connection</div>
    <div class="status-value" id="conn-status">...</div>
</div>

<div class="status-box">
    <div class="status-label">Current Ghost Mode</div>
    <div class="status-value off" id="mode-status">OFF</div>
</div>

<div class="buttons">
    <button class="btn-performance" onclick="setMode('performance')">PERFORMANCE MODE</button>
    <button class="btn-standard" onclick="setMode('standard')">STANDARD MODE</button>
    <button class="btn-chill" onclick="setMode('chill')">CHILL MODE</button>
    <button class="btn-stop" onclick="setMode('off')">STOP INJECTION</button>
    <button class="btn-honk" onclick="honk()">HONK</button>
</div>

<div class="stats">
    <div class="stat-row">
        <span class="stat-label">Frames Injected</span>
        <span class="stat-value" id="inject-count">0</span>
    </div>
    <div class="stat-row">
        <span class="stat-label">Uptime</span>
        <span class="stat-value" id="uptime">0s</span>
    </div>
    <div class="stat-row">
        <span class="stat-label">Injection Rate</span>
        <span class="stat-value" id="inject-rate">0 Hz</span>
    </div>
</div>

<p class="warning">For educational and research purposes only. Use at your own risk.</p>

<script>
async function setMode(mode) {
    try {
        const resp = await fetch('/api/mode', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: mode})
        });
        const data = await resp.json();
        updateUI(data);
    } catch(e) {
        document.getElementById('conn-status').textContent = 'ERROR';
        document.getElementById('conn-status').className = 'status-value disconnected';
    }
}

async function honk() {
    try {
        await fetch('/api/honk', {method: 'POST'});
    } catch(e) {}
}

function updateUI(data) {
    const modeEl = document.getElementById('mode-status');
    modeEl.textContent = (data.mode || 'OFF').toUpperCase();
    modeEl.className = 'status-value ' + (data.mode || 'off');

    document.getElementById('inject-count').textContent = data.inject_count || 0;
    document.getElementById('uptime').textContent = (data.uptime || 0) + 's';
    document.getElementById('inject-rate').textContent = (data.inject_rate || 0) + ' Hz';
}

async function poll() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();
        updateUI(data);
        const connEl = document.getElementById('conn-status');
        connEl.textContent = data.connected ? 'CONNECTED' : 'DISCONNECTED';
        connEl.className = 'status-value ' + (data.connected ? 'connected' : 'disconnected');
    } catch(e) {
        document.getElementById('conn-status').textContent = 'NO SERVER';
        document.getElementById('conn-status').className = 'status-value disconnected';
    }
}

setInterval(poll, 1000);
poll();
</script>
</body>
</html>"""


class GhostController:
    def __init__(self, port):
        self.port = port
        self.ser = None
        self.running = False
        self.active_mode = None
        self.inject_count = 0
        self.start_time = None
        self.connected = False
        self.lock = threading.Lock()
        self.inject_thread = None

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, DEFAULT_BAUD, timeout=1)
            time.sleep(0.5)
            for cmd, wait in [("ATZ", 2), ("ATE0", 0.5), ("ATH1", 0.5), ("ATSP6", 0.5), ("ATCAF0", 0.5)]:
                self.ser.write((cmd + "\r").encode())
                time.sleep(wait)
                self.ser.read(self.ser.in_waiting)
            self.connected = True
            print(f"Connected to {self.port}")
        except Exception as e:
            print(f"Connection failed: {e}")
            self.connected = False

    def honk(self):
        if not self.connected:
            return
        with self.lock:
            self.ser.write(b"ATSH 273\r")
            time.sleep(0.1)
            self.ser.read(self.ser.in_waiting)
            self.ser.write(b"00 00 00 00 00 00 00 20\r")
            time.sleep(0.2)
            self.ser.read(self.ser.in_waiting)

    def set_mode(self, mode):
        if mode == "off" or mode is None:
            self.active_mode = None
            print("Ghost mode OFF")
            return

        if mode not in MODE_BYTES:
            return

        self.active_mode = mode
        self.inject_count = 0
        self.start_time = time.time()
        print(f"Ghost mode: {mode.upper()}")

        # Start injection thread if not running
        if self.inject_thread is None or not self.inject_thread.is_alive():
            self.inject_thread = threading.Thread(target=self._inject_loop, daemon=True)
            self.inject_thread.start()

    def _inject_loop(self):
        counter = 0
        while self.active_mode is not None:
            mode = self.active_mode
            if mode is None:
                break

            mode_byte = MODE_BYTES[mode]

            with self.lock:
                try:
                    self.ser.write(b"ATSH 334\r")
                    time.sleep(0.02)
                    self.ser.read(self.ser.in_waiting)

                    b7 = (counter * 16) & 0xFF
                    b8 = (counter * 4) & 0xFF
                    frame = f"{mode_byte:02X} 3F 14 80 FC 07 {b7:02X} {b8:02X}"
                    self.ser.write((frame + "\r").encode())
                    time.sleep(0.02)
                    self.ser.read(self.ser.in_waiting)

                    self.inject_count += 1
                    counter = (counter + 1) % 256
                except Exception as e:
                    print(f"Inject error: {e}")

            time.sleep(0.05)  # 20 Hz injection rate

    def get_status(self):
        uptime = int(time.time() - self.start_time) if self.start_time and self.active_mode else 0
        rate = self.inject_count / uptime if uptime > 0 else 0
        return {
            "connected": self.connected,
            "mode": self.active_mode,
            "inject_count": self.inject_count,
            "uptime": uptime,
            "inject_rate": round(rate, 1),
        }


class GhostHandler(BaseHTTPRequestHandler):
    controller = None

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.controller.get_status()).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/mode":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            mode = body.get("mode", "off")
            self.controller.set_mode(mode)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.controller.get_status()).encode())
        elif self.path == "/api/honk":
            self.controller.honk()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
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
    parser = argparse.ArgumentParser(description="Ghost3D Tesla UI")
    parser.add_argument("--port", "-p", help="Serial port")
    parser.add_argument("--http", type=int, default=HTTP_PORT)
    args = parser.parse_args()

    port = args.port or find_port()
    if not port:
        print("No OBDLink adapter found!")
        sys.exit(1)

    controller = GhostController(port)
    controller.connect()

    GhostHandler.controller = controller
    httpd = HTTPServer(("0.0.0.0", args.http), GhostHandler)
    print(f"\nGhost3D UI running at http://localhost:{args.http}")
    print("Open this in your browser. No internet needed.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        controller.set_mode(None)
        httpd.shutdown()
        print("Stopped.")


if __name__ == "__main__":
    main()
