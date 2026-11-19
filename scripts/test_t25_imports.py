#!/usr/bin/env python3
"""
Test script for Task T2.5: Import input files (OpenAPI definitions and LSR login sequences).
Verifies:
1. Driver imports OpenAPI files into Acunetix target configuration imports.
2. Driver imports LSR files into Acunetix target login sequence and sets login kind to sequence.
3. Verified via direct Acunetix REST API inspection (status: True for import).
4. Cleans up test target completely.
5. Zero password/token leakage in logs.
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

TMP_DIR = BASE_DIR / "tmp" / "test_t25"

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
    print("RUNNING VERIFICATION FOR TASK T2.5 (IMPORT OPENAPI & LSR FILES)")
    print("=" * 60)

    acx_url = find_active_acunetix_url()
    print(f"Targeting active Acunetix instance at: {acx_url}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    scan_id = "test-t25-imports"
    sec_file = TMP_DIR / "credentials.json"
    opt_file = TMP_DIR / "options.json"
    inputs_dir = TMP_DIR / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    raw_secrets = {
        "admin_email": "admin@acunetix.com",
        "admin_password": "Acunetix@123",
        "target_url": "http://127.0.0.1:3000",
        "target_credentials": {
            "username": "admin@juice-sh.op",
            "password": "TargetSecretPassword123"
        }
    }
    sec_file.write_text(json.dumps(raw_secrets, indent=2), encoding="utf-8")

    scan_options = {
        "profile": "Full Scan",
        "scan_speed": "fast"
    }
    opt_file.write_text(json.dumps(scan_options, indent=2), encoding="utf-8")

    # 1. Create sample OpenAPI definition file
    openapi_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Juice Shop Sample API",
            "version": "1.0.0"
        },
        "paths": {
            "/api/v1/test-user-endpoint": {
                "get": {
                    "summary": "Retrieve user data",
                    "responses": {"200": {"description": "OK"}}
                }
            },
            "/api/v1/test-order-endpoint": {
                "post": {
                    "summary": "Submit order",
                    "responses": {"201": {"description": "Created"}}
                }
            }
        }
    }
    openapi_file = inputs_dir / "openapi_juice.json"
    openapi_file.write_text(json.dumps(openapi_spec, indent=2), encoding="utf-8")

    # 2. Create sample valid LSR file
    lsr_content = {
        "actions": [
            {
                "type": "navigate",
                "target": "http://127.0.0.1:3000/#/login",
                "timeout": 15000,
                "parameters": {"friendly": "Navigate to Login"}
            },
            {
                "type": "change",
                "target": "//*[@id='email']",
                "parameters": {"value": "admin@juice-sh.op"}
            },
            {
                "type": "change",
                "target": "//*[@id='password']",
                "parameters": {"value": "admin123"}
            },
            {
                "type": "click",
                "target": "//*[@id='loginButton']",
                "parameters": {"friendly": "Click Login"}
            }
        ],
        "restrictions": [
            {"url": "http://127.0.0.1:3000/#/logout"}
        ],
        "config": {}
    }
    lsr_file = inputs_dir / "login_flow.lsr"
    lsr_file.write_text(json.dumps(lsr_content, indent=2), encoding="utf-8")

    # Run driver without --clean-target first so we can verify target configuration
    cmd = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", scan_id,
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--options-file", str(opt_file),
        "--inputs-dir", str(inputs_dir),
        "--ready-timeout", "10"
    ]

    print("Running driver command with inputs directory...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("--- STDOUT ---")
    print(res.stdout)
    if res.stderr:
        print("--- STDERR ---")
        print(res.stderr)

    assert res.returncode == 0, f"Driver failed with exit code {res.returncode}"
    print("[PASS] Driver executed successfully (exit code 0)")

    # Extract target_id from output
    m = re.search(r"Target ([a-f0-9\-]{36}) successfully configured", res.stdout)
    assert m, "Failed to find created target_id in driver output"
    target_id = m.group(1)
    print(f"Inspecting created target: {target_id}")

    # Verify directly via Acunetix REST API
    client = AcunetixClient(base_url=acx_url)
    client.authenticate(email="admin@acunetix.com", password="Acunetix@123")

    # 1. Verify OpenAPI file import
    status, imports_data = client.request(f"/api/v1/targets/{target_id}/configuration/imports")
    assert status == 200, f"Failed to get imports: {status} {imports_data}"
    files = imports_data.get("files", [])
    print(f"Imported files in Acunetix: {files}")
    assert any(f.get("name") == "openapi_juice.json" and f.get("status") is True for f in files), \
        "OpenAPI file openapi_juice.json not found or status is not True"
    print("[PASS] OpenAPI definition successfully imported and verified with status: True")

    # 2. Verify LSR sequence in target configuration
    status, conf_data = client.request(f"/api/v1/targets/{target_id}/configuration")
    assert status == 200, f"Failed to get configuration: {status} {conf_data}"
    login_conf = conf_data.get("login", {})
    print(f"Target login configuration: {login_conf}")
    assert login_conf.get("kind") == "sequence", f"Login kind expected 'sequence', got {login_conf.get('kind')}"
    print("[PASS] Target login mode successfully switched to 'sequence'")

    # 3. Clean up target
    del_ok = client.delete_target(target_id)
    assert del_ok, "Failed to delete target"
    print(f"[PASS] Target {target_id} cleaned up successfully")

    # 4. Check for secret leaks
    sensitive_values = ["Acunetix@123", "TargetSecretPassword123"]
    for secret in sensitive_values:
        assert secret not in res.stdout, f"LEAK DETECTED in stdout: {secret}"
        assert secret not in res.stderr, f"LEAK DETECTED in stderr: {secret}"
    print("[PASS] Zero sensitive secrets detected in logs/output")

    print("=" * 60)
    print("ALL VERIFICATIONS FOR TASK T2.5 PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
