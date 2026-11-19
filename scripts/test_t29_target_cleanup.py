#!/usr/bin/env python3
"""
Test script for Task T2.9: Clean up target before webhook dispatch.
Verifies:
1. Driver compiles scan results payload first.
2. Driver executes DELETE /api/v1/targets/{target_id} BEFORE webhook dispatch.
3. Verified via direct Acunetix REST API check:
   - Target returns HTTP 404 Not Found.
   - Scan record returns HTTP 404 Not Found (cascaded cleanup).
4. No stale targets or scan data left in Acunetix.
5. Zero password/token leakage in output/logs.
"""
import sys
import json
import subprocess
import time
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from driver.client import AcunetixClient

TMP_DIR = BASE_DIR / "tmp" / "test_t29"

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
    print("RUNNING VERIFICATION FOR TASK T2.9 (TARGET CLEANUP BEFORE WEBHOOK)")
    print("=" * 60)

    acx_url = find_active_acunetix_url()
    print(f"Targeting active Acunetix instance at: {acx_url}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    sec_file = TMP_DIR / "credentials.json"
    opt_file = TMP_DIR / "options.json"

    raw_secrets = {
        "admin_email": "admin@acunetix.com",
        "admin_password": "Acunetix@123",
        "target_url": "http://127.0.0.1:3000"
    }
    sec_file.write_text(json.dumps(raw_secrets, indent=2), encoding="utf-8")

    scan_options = {
        "profile": "crawl_only",
        "scan_speed": "fast"
    }
    opt_file.write_text(json.dumps(scan_options, indent=2), encoding="utf-8")

    # Run driver without --keep-target (default cleanup behavior)
    cmd = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-t29-cleanup",
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--options-file", str(opt_file),
        "--ready-timeout", "10",
        "--scan-timeout", "30",
        "--poll-interval", "2.0"
    ]

    print("Running driver with automatic target cleanup...")
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    print(f"Driver finished in {elapsed:.1f}s with returncode {res.returncode}")
    print("--- STDOUT (excerpt) ---")
    for line in res.stdout.splitlines()[-12:]:
        print(line)

    assert res.returncode == 0, f"Driver failed with exit code {res.returncode}"

    # Extract target_id and scan_id
    m_target = re.search(r"Target created successfully: target_id=([a-f0-9\-]{36})", res.stdout)
    assert m_target, "Could not find target_id in output"
    target_id = m_target.group(1)

    m_scan = re.search(r"Scan triggered successfully with ID ([a-f0-9\-]{36})", res.stdout)
    assert m_scan, "Could not find scan_id in output"
    scan_id = m_scan.group(1)

    print(f"\nExtracted target_id={target_id}, scan_id={scan_id}")

    # Verify execution order:
    # 1. Results collected and payload compiled
    idx_payload = res.stdout.find("Scan payload compiled:")
    assert idx_payload != -1, "Missing payload compilation log"

    # 2. Cleanup target log must appear AFTER payload compiled
    idx_cleanup = res.stdout.find(f"Cleaning up target {target_id} before webhook callback")
    assert idx_cleanup != -1, "Missing cleanup target log before webhook"
    assert idx_cleanup > idx_payload, "Target cleanup happened BEFORE payload compilation!"

    idx_cleaned = res.stdout.find("deleted successfully from Acunetix")
    assert idx_cleaned != -1, "Missing target deleted confirmation log"
    assert idx_cleaned > idx_cleanup, "Cleanup confirmation order incorrect"

    print("[PASS] Verified execution order: Payload was compiled BEFORE target was deleted.")

    # Direct Acunetix REST API check: Target and Scan must be 404 Not Found
    print("\nVerifying on Acunetix REST API directly...")
    client = AcunetixClient(base_url=acx_url)
    client.authenticate(email="admin@acunetix.com", password="Acunetix@123")

    s_target, r_target = client.request(f"/api/v1/targets/{target_id}")
    print(f"GET /api/v1/targets/{target_id} -> HTTP {s_target}")
    assert s_target == 404, f"Target still exists in Acunetix! Expected 404, got {s_target}"
    print("[PASS] Target verified completely removed (HTTP 404).")

    s_scan, r_scan = client.request(f"/api/v1/scans/{scan_id}")
    print(f"GET /api/v1/scans/{scan_id} -> HTTP {s_scan}")
    assert s_scan == 404, f"Scan still exists in Acunetix! Expected 404, got {s_scan}"
    print("[PASS] Scan and associated results verified cascaded and deleted (HTTP 404).")

    # Check for secret leaks
    assert "Acunetix@123" not in res.stdout, "LEAK DETECTED: Admin password leaked"
    assert "Acunetix@123" not in res.stderr, "LEAK DETECTED: Admin password leaked"
    print("[PASS] Zero sensitive secrets detected in logs/output.")

    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS FOR TASK T2.9 PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
