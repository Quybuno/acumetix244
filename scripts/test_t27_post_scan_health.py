#!/usr/bin/env python3
"""
Test script for Task T2.7: Post-scan business health checks.
Verifies that Acunetix's "Completed" status is NOT treated as a success if:
1. LOW_COVERAGE: Discovered crawler locations is below threshold (e.g. unreachable or blocked crawler).
2. LOGIN_FAILED: Login credentials/sequence failed to authenticate.
3. MANUAL_INTERVENTION: Scan requires human intervention (CAPTCHA, MFA).
And verifies that a healthy scan passes all checks.
Zero password/token leakage.
"""
import sys
import json
import subprocess
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from driver.client import AcunetixClient

TMP_DIR = BASE_DIR / "tmp" / "test_t27"

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

def test_live_low_coverage_rejection(acx_url: str):
    print("\n--- TEST CASE 1: Live Low Coverage Rejection (Driver CLI) ---")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    sec_file = TMP_DIR / "credentials_live.json"
    opt_file = TMP_DIR / "options_live.json"

    raw_secrets = {
        "admin_email": "admin@acunetix.com",
        "admin_password": "Acunetix@123",
        "target_url": "http://127.0.0.1:3000"
    }
    sec_file.write_text(json.dumps(raw_secrets, indent=2), encoding="utf-8")

    # Target unreachable inside container produces locations=2, which is < min_locations=5
    scan_options = {
        "profile": "crawl_only",
        "scan_speed": "fast",
        "min_locations": 5
    }
    opt_file.write_text(json.dumps(scan_options, indent=2), encoding="utf-8")

    cmd = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-t27-low-coverage",
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--options-file", str(opt_file),
        "--ready-timeout", "10",
        "--scan-timeout", "30",
        "--poll-interval", "2.0",
        "--clean-target"
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    print("--- STDOUT (excerpt) ---")
    for line in res.stdout.splitlines()[-10:]:
        print(line)

    assert "Post-scan verification REJECTED Acunetix 'completed' status!" in res.stdout, \
        "Driver failed to reject Acunetix completed status on low coverage"
    assert "LOW_COVERAGE" in res.stdout, "Missing error_code='LOW_COVERAGE'"
    print("[PASS] Test Case 1 passed: Driver rejected 'completed' status due to LOW_COVERAGE.")

def test_unit_health_conditions(acx_url: str):
    print("\n--- TEST CASE 2: Unit Verification for LOGIN_FAILED ---")
    client = AcunetixClient(base_url=acx_url)

    dummy_scan_info = {
        "manual_intervention": False,
        "current_session": {"status": "completed", "scan_session_id": "dummy-session"}
    }
    dummy_target_config = {
        "login": {
            "kind": "automatic",
            "credentials": {"enabled": True, "username": "admin", "password": "xyz"}
        }
    }
    dummy_stats_login_failed = {
        "scanning_app": {
            "wvs": {
                "main": {
                    "web_scan_status": {"locations": 50, "request_count": 500},
                    "messages": [
                        {"kind": "autologin_failed", "data": "Failed to log in with supplied credentials."}
                    ]
                }
            }
        }
    }

    is_healthy, err, details = client.check_post_scan_health(
        scan_id="unit-login-fail",
        scan_info=dummy_scan_info,
        statistics=dummy_stats_login_failed,
        scan_options={"min_locations": 3},
        target_config=dummy_target_config
    )
    print(f"Login failed check: is_healthy={is_healthy}, error_code={err}, details={details}")
    assert is_healthy is False, "Expected is_healthy=False for login failure"
    assert err == "LOGIN_FAILED", f"Expected error_code='LOGIN_FAILED', got {err}"
    print("[PASS] Test Case 2 passed: Successfully flagged LOGIN_FAILED.")

    print("\n--- TEST CASE 3: Unit Verification for MANUAL_INTERVENTION ---")
    dummy_scan_info_mi = {
        "manual_intervention": True,
        "current_session": {"status": "completed", "scan_session_id": "dummy-session"}
    }
    dummy_stats_ok = {
        "scanning_app": {
            "wvs": {
                "main": {
                    "web_scan_status": {"locations": 50, "request_count": 500},
                    "messages": []
                }
            }
        }
    }
    is_healthy, err, details = client.check_post_scan_health(
        scan_id="unit-mi",
        scan_info=dummy_scan_info_mi,
        statistics=dummy_stats_ok,
        scan_options={"min_locations": 3},
        target_config={"login": {"kind": "none"}}
    )
    print(f"Manual intervention check: is_healthy={is_healthy}, error_code={err}")
    assert is_healthy is False, "Expected is_healthy=False for manual intervention"
    assert err == "MANUAL_INTERVENTION", f"Expected error_code='MANUAL_INTERVENTION', got {err}"
    print("[PASS] Test Case 3 passed: Successfully flagged MANUAL_INTERVENTION.")

    print("\n--- TEST CASE 4: Unit Verification for HEALTHY SCAN ---")
    dummy_scan_info_healthy = {
        "manual_intervention": False,
        "current_session": {"status": "completed", "scan_session_id": "dummy-session"}
    }
    is_healthy, err, details = client.check_post_scan_health(
        scan_id="unit-healthy",
        scan_info=dummy_scan_info_healthy,
        statistics=dummy_stats_ok,
        scan_options={"min_locations": 10},
        target_config={"login": {"kind": "none"}}
    )
    print(f"Healthy scan check: is_healthy={is_healthy}, error_code={err}")
    assert is_healthy is True, "Expected is_healthy=True for valid healthy scan"
    assert err is None, f"Expected error_code=None, got {err}"
    print("[PASS] Test Case 4 passed: Healthy scan successfully accepted.")

def main():
    print("=" * 60)
    print("RUNNING VERIFICATION FOR TASK T2.7 (POST-SCAN HEALTH CHECKS)")
    print("=" * 60)

    acx_url = find_active_acunetix_url()
    print(f"Targeting active Acunetix instance at: {acx_url}")

    test_live_low_coverage_rejection(acx_url)
    test_unit_health_conditions(acx_url)

    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS FOR TASK T2.7 PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
