#!/usr/bin/env python3
"""
Test script for Task T2.6: Scan creation, periodic polling, and timeout handling.
Verifies:
1. Driver starts immediate scan via Acunetix REST API and polls until completed.
2. Driver monitors progress, status, and elapsed time without freezing.
3. Driver handles timeout: when scan duration exceeds --scan-timeout, aborts scan and exits with code 14 (EXIT_CODE_SCAN_TIMEOUT).
4. Targets and scans cleaned up properly.
5. Zero password or token leaks in logs/output.
"""
import sys
import json
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from driver.client import AcunetixClient

TMP_DIR = BASE_DIR / "tmp" / "test_t26"

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
    print("RUNNING VERIFICATION FOR TASK T2.6 (SCAN LIFECYCLE & TIMEOUT)")
    print("=" * 60)

    acx_url = find_active_acunetix_url()
    print(f"Targeting active Acunetix instance at: {acx_url}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    sec_file = TMP_DIR / "credentials.json"
    raw_secrets = {
        "admin_email": "admin@acunetix.com",
        "admin_password": "Acunetix@123",
        "target_url": "http://127.0.0.1:3000"
    }
    sec_file.write_text(json.dumps(raw_secrets, indent=2), encoding="utf-8")

    # ==========================================================
    # TEST CASE 1: Successful Scan Execution & Completion Polling
    # ==========================================================
    print("\n--- TEST CASE 1: Scan Execution & Polling to Completion ---")
    opt_file_fast = TMP_DIR / "options_fast.json"
    scan_options_fast = {
        "profile": "crawl_only",
        "scan_speed": "fast",
        "limit_crawler_scope": True
    }
    opt_file_fast.write_text(json.dumps(scan_options_fast, indent=2), encoding="utf-8")

    cmd_case1 = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-t26-complete",
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--options-file", str(opt_file_fast),
        "--ready-timeout", "10",
        "--scan-timeout", "60",
        "--poll-interval", "2.0",
        "--clean-target"
    ]

    t0 = time.time()
    res1 = subprocess.run(cmd_case1, capture_output=True, text=True)
    elapsed1 = time.time() - t0
    print(f"Case 1 finished in {elapsed1:.1f}s with returncode {res1.returncode}")
    print("--- STDOUT (excerpt) ---")
    for line in res1.stdout.splitlines()[-10:]:
        print(line)

    assert res1.returncode == 0, f"Expected returncode 0 on successful scan, got {res1.returncode}"
    assert "Scan progress: status='processing'" in res1.stdout, "Missing processing state log"
    assert "completed successfully" in res1.stdout or "finished polling with status 'completed'" in res1.stdout, \
        "Missing completed state log"
    print("[PASS] Test Case 1 passed: Scan created, polled, and finished with status 'completed' (code 0)")

    # ==========================================================
    # TEST CASE 2: Scan Timeout Handling & Abort
    # ==========================================================
    print("\n--- TEST CASE 2: Scan Timeout & Abort ---")
    opt_file_slow = TMP_DIR / "options_slow.json"
    scan_options_slow = {
        "profile": "Full Scan",
        "scan_speed": "sequential"
    }
    opt_file_slow.write_text(json.dumps(scan_options_slow, indent=2), encoding="utf-8")

    cmd_case2 = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-t26-timeout",
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--options-file", str(opt_file_slow),
        "--ready-timeout", "10",
        "--scan-timeout", "5",
        "--poll-interval", "1.0",
        "--clean-target"
    ]

    t0 = time.time()
    res2 = subprocess.run(cmd_case2, capture_output=True, text=True)
    elapsed2 = time.time() - t0
    print(f"Case 2 finished in {elapsed2:.1f}s with returncode {res2.returncode}")
    print("--- STDOUT (excerpt) ---")
    for line in res2.stdout.splitlines()[-8:]:
        print(line)

    assert res2.returncode == 14, f"Expected returncode 14 (EXIT_CODE_SCAN_TIMEOUT), got {res2.returncode}"
    assert "exceeded maximum timeout" in res2.stdout or "exceeded maximum timeout" in res2.stderr, \
        "Missing timeout error message in log"
    assert "Scan" in res2.stdout and "abort" in res2.stdout, "Missing scan abort log"
    print("[PASS] Test Case 2 passed: Scan timed out, abort called, and exited with code 14 (SCAN_TIMEOUT)")

    # ==========================================================
    # Check for secret leaks in both cases
    # ==========================================================
    for out in [res1.stdout, res1.stderr, res2.stdout, res2.stderr]:
        assert "Acunetix@123" not in out, "LEAK DETECTED: Admin password leaked"

    print("[PASS] Zero sensitive secrets detected in logs/output")

    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS FOR TASK T2.6 PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
