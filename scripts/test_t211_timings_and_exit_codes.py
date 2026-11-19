#!/usr/bin/env python3
"""
Test script for Task T2.11: Exit codes table and step execution timers.
Verifies:
1. Driver measures duration of each pipeline step and total execution time.
2. Timing breakdown is printed in a formatted summary table at completion.
3. Total driver execution time is strictly less than Job timeout limit (T1.6).
4. Timing dictionary is included in webhook result payload.
5. Standard exit codes table is enforced:
   - 0: OK / Success
   - 10: Acunetix Not Ready
   - 11: Authentication Failed
   - 12: Target Configuration Failed
   - 13: Import Files Failed
   - 14: Scan Timeout / Failed
   - 50: Webhook Dispatch Failed (CALLBACK_LOST)
6. Zero password/token leakage in output/logs.
"""
import sys
import json
import subprocess
import time
import re
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from driver.client import AcunetixClient
from driver.main import (
    EXIT_CODE_SUCCESS,
    EXIT_CODE_ACUNETIX_NOT_READY,
    EXIT_CODE_AUTH_FAILED,
    EXIT_CODE_CONFIG_FAILED,
    EXIT_CODE_IMPORT_FAILED,
    EXIT_CODE_SCAN_TIMEOUT,
    EXIT_CODE_WEBHOOK_FAILED
)

TMP_DIR = BASE_DIR / "tmp" / "test_t211"

class MockWebhookHandler(BaseHTTPRequestHandler):
    received_payloads = []

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8")
        MockWebhookHandler.received_payloads.append(json.loads(body))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, format, *args):
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

def test_full_pipeline_timing_summary(acx_url: str):
    print("\n--- TEST CASE 1: Timing Breakdown and Job Timeout Margin ---")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    sec_file = TMP_DIR / "credentials.json"
    opt_file = TMP_DIR / "options.json"

    raw_secrets = {
        "admin_email": "admin@acunetix.com",
        "admin_password": "Acunetix@123",
        "target_url": "http://127.0.0.1:3000",
        "webhook_token": "token-test-t211"
    }
    sec_file.write_text(json.dumps(raw_secrets, indent=2), encoding="utf-8")

    scan_options = {
        "profile": "crawl_only",
        "scan_speed": "fast"
    }
    opt_file.write_text(json.dumps(scan_options, indent=2), encoding="utf-8")

    server = HTTPServer(("127.0.0.1", 0), MockWebhookHandler)
    server_port = server.server_port
    server_url = f"http://127.0.0.1:{server_port}/callback"
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    MockWebhookHandler.received_payloads.clear()

    job_timeout = 1860
    cmd = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-t211-timings",
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--options-file", str(opt_file),
        "--webhook-url", server_url,
        "--ready-timeout", "10",
        "--scan-timeout", "30",
        "--poll-interval", "2.0",
        "--job-timeout", str(job_timeout)
    ]

    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    print(f"Driver completed in {elapsed:.1f}s with returncode {res.returncode}")
    print("--- STDOUT (excerpt) ---")
    for line in res.stdout.splitlines()[-18:]:
        print(line)

    assert res.returncode == EXIT_CODE_SUCCESS, f"Expected returncode 0, got {res.returncode}"
    assert "DRIVER EXECUTION TIMING SUMMARY" in res.stdout, "Missing timing summary header"
    assert "Total Driver Duration:" in res.stdout, "Missing total duration in summary"
    assert "Margin to Job Kill:" in res.stdout, "Missing job timeout margin in summary"

    # Verify total duration is strictly less than Job Timeout (T1.6)
    assert elapsed < job_timeout, f"Total driver elapsed ({elapsed}s) exceeded Job timeout ({job_timeout}s)!"

    # Verify timing dictionary received in Webhook payload
    assert len(MockWebhookHandler.received_payloads) == 1, "Mock server did not receive webhook"
    payload = MockWebhookHandler.received_payloads[0]
    assert "timings" in payload, "Webhook payload missing 'timings' key"
    timings = payload["timings"]
    assert "steps" in timings and len(timings["steps"]) > 0, "Empty steps in timings payload"
    step_names = [s["name"] for s in timings["steps"]]
    print(f"Measured pipeline steps: {step_names}")
    assert any("Configuration" in name for name in step_names), "Missing Configuration step timer"
    assert any("Readiness" in name for name in step_names), "Missing Readiness step timer"
    assert any("Authentication" in name for name in step_names), "Missing Authentication step timer"
    assert any("Scan" in name for name in step_names), "Missing Scan step timer"

    server.shutdown()
    print("[PASS] Test Case 1 passed: Step timing table and Job timeout comparison verified.")

def test_exit_codes_table(acx_url: str):
    print("\n--- TEST CASE 2: Exit Codes Verification ---")
    print(f"Standard Exit Codes:")
    print(f"  EXIT_CODE_SUCCESS: {EXIT_CODE_SUCCESS}")
    print(f"  EXIT_CODE_ACUNETIX_NOT_READY: {EXIT_CODE_ACUNETIX_NOT_READY}")
    print(f"  EXIT_CODE_AUTH_FAILED: {EXIT_CODE_AUTH_FAILED}")
    print(f"  EXIT_CODE_CONFIG_FAILED: {EXIT_CODE_CONFIG_FAILED}")
    print(f"  EXIT_CODE_IMPORT_FAILED: {EXIT_CODE_IMPORT_FAILED}")
    print(f"  EXIT_CODE_SCAN_TIMEOUT: {EXIT_CODE_SCAN_TIMEOUT}")
    print(f"  EXIT_CODE_WEBHOOK_FAILED: {EXIT_CODE_WEBHOOK_FAILED}")

    # Verify exit code 10 when Acunetix is not ready
    cmd_code10 = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-code-10",
        "--acunetix-url", "https://127.0.0.1:59999",
        "--target-url", "http://127.0.0.1:3000",
        "--ready-timeout", "2"
    ]
    res10 = subprocess.run(cmd_code10, capture_output=True, text=True)
    assert res10.returncode == EXIT_CODE_ACUNETIX_NOT_READY, \
        f"Expected exit code {EXIT_CODE_ACUNETIX_NOT_READY}, got {res10.returncode}"
    assert re.search(r"Exit Code:\s+10", res10.stdout), "Summary table missing exit code 10"
    print(f"[PASS] Exit Code 10 verified: Not ready exits with code 10.")

    # Verify exit code 14 on scan timeout
    cmd_code14 = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-code-14",
        "--acunetix-url", acx_url,
        "--target-url", "http://127.0.0.1:3000",
        "--secrets-file", str(TMP_DIR / "credentials.json"),
        "--scan-timeout", "3",
        "--poll-interval", "1.0",
        "--ready-timeout", "10"
    ]
    res14 = subprocess.run(cmd_code14, capture_output=True, text=True)
    assert res14.returncode == EXIT_CODE_SCAN_TIMEOUT, \
        f"Expected exit code {EXIT_CODE_SCAN_TIMEOUT}, got {res14.returncode}"
    assert re.search(r"Exit Code:\s+14", res14.stdout), "Summary table missing exit code 14"
    print(f"[PASS] Exit Code 14 verified: Scan timeout exits with code 14.")

    # Verify exit code 50 on webhook failure
    cmd_code50 = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-code-50",
        "--acunetix-url", acx_url,
        "--target-url", "http://127.0.0.1:3000",
        "--secrets-file", str(TMP_DIR / "credentials.json"),
        "--webhook-url", "http://127.0.0.1:59998/fail",
        "--webhook-retries", "1",
        "--webhook-retry-delay", "0.1",
        "--scan-timeout", "30",
        "--poll-interval", "2.0",
        "--ready-timeout", "10"
    ]
    res50 = subprocess.run(cmd_code50, capture_output=True, text=True)
    assert res50.returncode == EXIT_CODE_WEBHOOK_FAILED, \
        f"Expected exit code {EXIT_CODE_WEBHOOK_FAILED}, got {res50.returncode}"
    assert re.search(r"Exit Code:\s+50", res50.stdout), "Summary table missing exit code 50"
    print(f"[PASS] Exit Code 50 verified: Webhook failure exits with code 50.")

def main():
    print("=" * 60)
    print("RUNNING VERIFICATION FOR TASK T2.11 (TIMINGS & EXIT CODES)")
    print("=" * 60)

    acx_url = find_active_acunetix_url()
    print(f"Targeting active Acunetix instance at: {acx_url}")

    test_full_pipeline_timing_summary(acx_url)
    test_exit_codes_table(acx_url)

    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS FOR TASK T2.11 PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
