import subprocess
import time
import http.server
import threading

# 1. Start a temporary webhook server on host port 9999
webhook_received = []
class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        len_h = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(len_h).decode()
        webhook_received.append(body)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
    def log_message(self, format, *args):
        pass

server = http.server.HTTPServer(('0.0.0.0', 9999), WebhookHandler)
th = threading.Thread(target=server.serve_forever, daemon=True)
th.start()
print("[1] Temporary host webhook server running on port 9999...")

SCAN_ID = "t12net"
NET_NAME = f"scan-{SCAN_ID}-net"
ACX_NAME = f"scan-{SCAN_ID}-acunetix"
DRIVER_NAME = f"scan-{SCAN_ID}-driver"

try:
    # 2. Start net container
    print(f"[2] Starting net container ({NET_NAME})...")
    subprocess.check_call([
        "docker", "run", "-d",
        "--name", NET_NAME,
        "--label", f"scan-id={SCAN_ID}",
        "--label", "role=net",
        "--add-host", "host.docker.internal:host-gateway",
        "alpine:3.20", "sleep", "infinity"
    ])

    # 3. Start Acunetix container joining net container network
    print(f"[3] Starting Acunetix sidecar sharing network ({ACX_NAME})...")
    subprocess.check_call([
        "docker", "run", "-d",
        "--name", ACX_NAME,
        "--label", f"scan-id={SCAN_ID}",
        "--label", "role=acunetix",
        "--network", f"container:{NET_NAME}",
        "acunetix:24.4"
    ])
    time.sleep(2)
    subprocess.check_call([
        "docker", "exec", "-u", "0", ACX_NAME,
        "chmod", "777", "/home/acunetix/.acunetix/data/license"
    ])

    # Wait for Acunetix to respond on localhost:3443 from inside net container
    print("Waiting for Acunetix on localhost:3443 inside pod net...")
    ready = False
    for i in range(25):
        res = subprocess.run([
            "docker", "run", "--rm",
            "--network", f"container:{NET_NAME}",
            "curlimages/curl:latest",
            "curl", "-k", "-s", "-o", "/dev/null", "-w", "%{http_code}",
            "https://localhost:3443/api/v1/info"
        ], capture_output=True, text=True)
        if res.stdout.strip() in ["400", "401"]:
            ready = True
            break
        time.sleep(2)

    assert ready, "Acuentix should respond on localhost:3443 inside shared pod net"
    print(f"    --> Acunetix is responding on localhost:3443! HTTP code: {res.stdout.strip()}")

    # 4. From driver container, send webhook to host.docker.internal:9999
    print("[4] Testing driver container calling host.docker.internal:9999...")
    wh_res = subprocess.run([
        "docker", "run", "--rm",
        "--network", f"container:{NET_NAME}",
        "curlimages/curl:latest",
        "curl", "-s", "-X", "POST",
        "http://host.docker.internal:9999/webhook",
        "-H", "Content-Type: application/json",
        "-d", '{"scan_id":"t12net","status":"DRIVER_CONNECTED"}'
    ], capture_output=True, text=True)
    print("    Driver curl output:", wh_res.stdout)
    assert len(webhook_received) > 0, "Webhook should be received on host"
    print(f"    --> Host webhook received payload: {webhook_received[0]}")

    print("\n--> T1.2 SHARED NET CONTAINER VERIFIED SUCCESSFULLY!")

finally:
    server.shutdown()
    print("Cleaning up test containers...")
    subprocess.run(["docker", "rm", "-f", ACX_NAME, NET_NAME], capture_output=True)
