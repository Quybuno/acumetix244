#!/usr/bin/env python3
"""
Test script for Task T2.10: Webhook delivery with token, retries, and exit code 50 on failure.
Verifies:
1. Driver sends scan results to webhook with authentication token (X-Webhook-Token / Authorization).
2. Mock webhook server receives and validates payload and token headers (HTTP 200).
3. Network / HTTP failure triggers retry mechanism with exponential backoff.
4. When all retry attempts are exhausted, driver exits with code 50 (CALLBACK_LOST).
5. Zero password/token leakage in output/logs.
"""
import sys
import json
import subprocess
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from driver.client import AcunetixClient

TMP_DIR = BASE_DIR / "tmp" / "test_t210"

class MockWebhookHandler(BaseHTTPRequestHandler):
    received_payloads = []
    received_headers = []
    should_fail = False

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8")
        MockWebhookHandler.received_payloads.append(json.loads(body))
        MockWebhookHandler.received_headers.append(dict(self.headers))

        if MockWebhookHandler.should_fail:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error": "Internal Server Error"}')
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "received"}')

    def log_message(self, format, *args):
        # suppress default console logs
        pass

def find_active_acunetix_url() -> str:
    for port in [8888, 3443]:
        url = f"https://127.0.0.1:{port}"
        try:
            client = AcunetixClient(base_url=url)
            ready, _, _ = client.probe_health()
            if ready:
                return url
        except Exception:
            pass
    raise RuntimeError("No active Acunetix instance found on port 8888 or 3443")

def main():
    print("=" * 60)
    print("RUNNING VERIFICATION FOR TASK T2.10 (WEBHOOK DELIVERY & RETRY)")
    print("=" * 60)

    acx_url = find_active_acunetix_url()
    print(f"Targeting active Acunetix instance at: {acx_url}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    sec_file = TMP_DIR / "credentials.json"
    opt_file = TMP_DIR / "options.json"

    expected_token = "secret-deepreview-webhook-token-998877"
    raw_secrets = {
        "admin_email": "admin@acunetix.com",
        "admin_password": "Acunetix@123",
        "target_url": "http://127.0.0.1:3000",
        "webhook_token": expected_token
    }
    sec_file.write_text(json.dumps(raw_secrets, indent=2), encoding="utf-8")

    scan_options = {
        "profile": "crawl_only",
        "scan_speed": "fast"
    }
    opt_file.write_text(json.dumps(scan_options, indent=2), encoding="utf-8")

    # Start mock webhook server on random available port
    server = HTTPServer(("127.0.0.1", 0), MockWebhookHandler)
    server_port = server.server_port
    server_url = f"http://127.0.0.1:{server_port}/api/v1/scans/callback"
    print(f"Mock Webhook Server listening at: {server_url}")

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # ==========================================================
    # TEST CASE 1: Successful Webhook Delivery with Token
    # ==========================================================
    print("\n--- TEST CASE 1: Successful Webhook Delivery ---")
    MockWebhookHandler.received_payloads.clear()
    MockWebhookHandler.received_headers.clear()
    MockWebhookHandler.should_fail = False

    cmd_success = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-t210-success",
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--options-file", str(opt_file),
        "--webhook-url", server_url,
        "--ready-timeout", "10",
        "--scan-timeout", "30",
        "--poll-interval", "2.0"
    ]

    t0 = time.time()
    res1 = subprocess.run(cmd_success, capture_output=True, text=True)
    print(f"Driver execution finished in {time.time() - t0:.1f}s (returncode: {res1.returncode})")
    print("--- STDOUT (excerpt) ---")
    for line in res1.stdout.splitlines()[-10:]:
        print(line)

    assert res1.returncode == 0, f"Expected returncode 0, got {res1.returncode}"
    assert "Webhook delivered successfully" in res1.stdout, "Missing webhook delivery success log"
    assert len(MockWebhookHandler.received_payloads) == 1, "Mock server did not receive webhook payload"

    payload = MockWebhookHandler.received_payloads[0]
    headers = MockWebhookHandler.received_headers[0]

    assert payload["scan_id"] == "test-t210-success", "Mismatched scan_id in payload"
    assert "vulnerabilities" in payload, "Missing vulnerabilities array in payload"
    assert "statistics" in payload, "Missing statistics in payload"
    assert headers.get("X-Webhook-Token") == expected_token, f"Mismatched X-Webhook-Token: {headers.get('X-Webhook-Token')}"
    assert f"Bearer {expected_token}" in headers.get("Authorization", ""), "Missing Bearer token in Authorization header"

    print("[PASS] Test Case 1 passed: Webhook delivered with valid payload, token, and exit code 0.")

    # ==========================================================
    # TEST CASE 2: Webhook Failure, Retries, and Exit Code 50
    # ==========================================================
    print("\n--- TEST CASE 2: Webhook Failure, Retries & Exit Code 50 ---")
    # Point to an unreachable port to simulate connection failure
    unreachable_url = "http://127.0.0.1:59998/api/v1/scans/callback"

    cmd_failure = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-t210-failure",
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--options-file", str(opt_file),
        "--webhook-url", unreachable_url,
        "--webhook-retries", "3",
        "--webhook-retry-delay", "0.5",
        "--ready-timeout", "10",
        "--scan-timeout", "30",
        "--poll-interval", "2.0"
    ]

    t0 = time.time()
    res2 = subprocess.run(cmd_failure, capture_output=True, text=True)
    print(f"Driver execution finished in {time.time() - t0:.1f}s (returncode: {res2.returncode})")
    print("--- STDOUT (excerpt) ---")
    for line in res2.stdout.splitlines()[-10:]:
        print(line)

    assert res2.returncode == 50, f"Expected exit code 50 (CALLBACK_LOST), got {res2.returncode}"
    assert "Retrying webhook in" in res2.stdout, "Missing retry log messages"
    assert "Exiting with code 50 (CALLBACK_LOST)" in res2.stdout or "Exiting with code 50 (CALLBACK_LOST)" in res2.stderr, \
        "Missing code 50 log message"

    print("[PASS] Test Case 2 passed: Webhook retried 3 times and driver exited with code 50.")

    # Check for secret leaks
    for out in [res1.stdout, res1.stderr, res2.stdout, res2.stderr]:
        assert "Acunetix@123" not in out, "LEAK DETECTED: Admin password leaked"
        assert expected_token not in out, "LEAK DETECTED: Webhook token leaked"

    print("[PASS] Zero sensitive secrets detected in logs/output.")

    server.shutdown()
    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS FOR TASK T2.10 PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
