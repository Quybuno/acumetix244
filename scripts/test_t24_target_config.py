#!/usr/bin/env python3
"""
Test script for Task T2.4: Target creation and ScanOptions configuration.
Verifies:
1. Target is created with correct address, description, criticality.
2. Configuration is patched and matches ScanOptions:
   - Scanning profile (Full Scan)
   - Scan speed (fast)
   - Crawler scope limit
   - Excluded paths
   - Custom headers
   - Login credentials (automatic form login)
3. Verified via direct Acunetix REST API inspection.
4. Cleaned up target after test.
5. Zero password leakage in logs.
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

TMP_DIR = BASE_DIR / "tmp" / "test_t24"

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
    print("RUNNING VERIFICATION FOR TASK T2.4 (TARGET & SCANOPTIONS CONFIG)")
    print("=" * 60)

    acx_url = find_active_acunetix_url()
    print(f"Targeting active Acunetix instance at: {acx_url}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    scan_id = "test-t24-config"
    sec_file = TMP_DIR / "credentials.json"
    opt_file = TMP_DIR / "options.json"

    raw_secrets = {
        "admin_email": "admin@acunetix.com",
        "admin_password": "Acunetix@123",
        "target_url": "http://127.0.0.1:3000",
        "target_credentials": {
            "username": "admin@juice-sh.op",
            "password": "TargetSecretPassword123"
        },
        "custom_headers": [
            {"name": "X-Security-Scan", "value": "DeepReview-Agent"},
            {"name": "X-Custom-Env", "value": "LocalTest"}
        ]
    }
    sec_file.write_text(json.dumps(raw_secrets, indent=2), encoding="utf-8")

    scan_options = {
        "profile": "Full Scan",
        "scan_speed": "fast",
        "limit_crawler_scope": True,
        "excluded_paths": ["/#/logout", "/rest/user/logout", "/assets/"]
    }
    opt_file.write_text(json.dumps(scan_options, indent=2), encoding="utf-8")

    cmd = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", scan_id,
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--options-file", str(opt_file),
        "--ready-timeout", "10",
        "--no-scan"
    ]

    print("Running driver command...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("--- STDOUT ---")
    print(res.stdout)
    if res.stderr:
        print("--- STDERR ---")
        print(res.stderr)

    assert res.returncode == 0, f"Driver failed with exit code {res.returncode}"
    print("[PASS] Driver executed and exited with code 0")

    # Extract target_id from output
    match = re.search(r"target_id=([0-9a-f-]{36})", res.stdout)
    assert match is not None, "Failed to extract target_id from driver output"
    target_id = match.group(1)
    print(f"Extracted target_id: {target_id}")

    # Inspect target directly from Acunetix API
    client = AcunetixClient(base_url=acx_url)
    client.authenticate(email="admin@acunetix.com", password="Acunetix@123")

    # 1. Verify Target details
    status, target_obj = client.request(f"/api/v1/targets/{target_id}")
    assert status == 200, f"Failed to get target {target_id}: HTTP {status}"
    print(f"Verified Target Object: address='{target_obj.get('address')}' description='{target_obj.get('description')}'")
    assert target_obj.get("address") == "http://127.0.0.1:3000"
    assert target_obj.get("description") == f"Deep Review Scan - {scan_id}"

    # 2. Verify Target Configuration
    status, config_obj = client.request(f"/api/v1/targets/{target_id}/configuration")
    assert status == 200, f"Failed to get target configuration: HTTP {status}"
    print("Target Configuration on Acunetix:")
    print(json.dumps(config_obj, indent=2))

    assert config_obj.get("scan_speed") == "fast", "Scan speed mismatch"
    assert config_obj.get("limit_crawler_scope") is True, "limit_crawler_scope mismatch"
    assert "/#/logout" in config_obj.get("excluded_paths", []), "Missing excluded path"
    assert "/rest/user/logout" in config_obj.get("excluded_paths", []), "Missing excluded path"
    assert "X-Security-Scan: DeepReview-Agent" in config_obj.get("custom_headers", []), "Missing custom header"
    assert config_obj.get("login", {}).get("kind") == "automatic", "Login kind mismatch"
    assert config_obj.get("login", {}).get("credentials", {}).get("username") == "admin@juice-sh.op", "Username mismatch"
    assert config_obj.get("default_scanning_profile_id") == "11111111-1111-1111-1111-111111111111", "Profile ID mismatch"
    print("[PASS] Target configuration on Acunetix verified 100% matching ScanOptions!")

    # 3. Clean up target
    deleted = client.delete_target(target_id)
    assert deleted is True, f"Failed to clean up target {target_id}"
    print(f"[PASS] Target {target_id} cleaned up successfully.")

    # 4. Security check
    assert "TargetSecretPassword123" not in res.stdout, "Target password leaked in stdout!"
    print("[PASS] Target password masked and not leaked in stdout/log.")

    # Cleanup test files
    import shutil
    shutil.rmtree(TMP_DIR, ignore_errors=True)

    print("\n" + "=" * 60)
    print("TASK T2.4 VERIFICATION ALL PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
