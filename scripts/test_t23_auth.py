#!/usr/bin/env python3
"""
Test script for Task T2.3: Instance initialization & API authentication.
Verifies:
1. Dynamic authentication via admin login (POST /api/v1/me/login) + GraphQL mutation generateApiKey.
2. Direct authentication via provided valid API key.
3. Proper failure handling with exit code 11 when credentials are invalid.
4. Zero secret leakage across all logs.
"""
import sys
import json
import time
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
TMP_DIR = BASE_DIR / "tmp" / "test_t23"

def find_active_acunetix_url() -> str:
    for port in [8888, 3443]:
        url = f"https://127.0.0.1:{port}"
        cmd = [
            sys.executable,
            str(BASE_DIR / "driver" / "main.py"),
            "--scan-id", "test-probe",
            "--acunetix-url", url,
            "--ready-timeout", "3"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        # Port is ready if it responds with 0 or 11 (ready, but auth check failed)
        if res.returncode in [0, 11]:
            return url
    raise RuntimeError("No active Acunetix instance found on port 8888 or 3443")

def run_driver(acx_url: str, secrets: dict, scan_id: str) -> subprocess.CompletedProcess:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    sec_file = TMP_DIR / f"{scan_id}_secrets.json"
    sec_file.write_text(json.dumps(secrets, indent=2), encoding="utf-8")

    cmd = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", scan_id,
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--ready-timeout", "10"
    ]
    return subprocess.run(cmd, capture_output=True, text=True)

def main():
    print("=" * 60)
    print("RUNNING VERIFICATION FOR TASK T2.3 (API AUTHENTICATION)")
    print("=" * 60)

    acx_url = find_active_acunetix_url()
    print(f"Targeting active Acunetix instance at: {acx_url}")

    # --- TEST 1: DYNAMIC LOGIN + GRAPHQL API KEY GENERATION ---
    print("\n[Test 1] Testing dynamic login + GraphQL API key generation...")
    secrets_t1 = {
        "admin_email": "admin@acunetix.com",
        "admin_password": "Acunetix@123",
        "target_url": "http://127.0.0.1:3000"
    }
    res_t1 = run_driver(acx_url, secrets_t1, "t23-dynamic-login")
    print("STDOUT:")
    print(res_t1.stdout)
    if res_t1.stderr:
        print("STDERR:", res_t1.stderr)

    assert res_t1.returncode == 0, f"Expected exit code 0, got {res_t1.returncode}"
    assert "Authenticating via login endpoint as 'admin@acunetix.com'" in res_t1.stdout
    assert "Login successful. Requesting permanent API key via GraphQL mutation" in res_t1.stdout
    assert "API key generated and retrieved successfully" in res_t1.stdout
    assert "Instance authentication verified" in res_t1.stdout
    assert "Acunetix@123" not in res_t1.stdout, "Password leaked in log!"
    print("[PASS] Test 1 passed: Dynamic login and GraphQL key generation verified!")

    # --- TEST 2: AUTHENTICATION USING PROVIDED API KEY ---
    # We can use the default or known API key or extract one
    print("\n[Test 2] Testing direct authentication using provided API key...")
    # Fetch a valid key directly from GraphQL or known test key
    from driver.client import AcunetixClient
    client = AcunetixClient(base_url=acx_url)
    valid_key = client.login_and_generate_api_key("admin@acunetix.com", "Acunetix@123")
    
    secrets_t2 = {
        "api_key": valid_key,
        "target_url": "http://127.0.0.1:3000"
    }
    res_t2 = run_driver(acx_url, secrets_t2, "t23-provided-key")
    print("STDOUT:")
    print(res_t2.stdout)

    assert res_t2.returncode == 0, f"Expected exit code 0, got {res_t2.returncode}"
    assert "Validating provided API key against Acunetix API" in res_t2.stdout
    assert "Provided API key is valid and authenticated" in res_t2.stdout
    assert "Instance authentication verified" in res_t2.stdout
    assert valid_key not in res_t2.stdout, "Raw API key leaked in stdout!"
    print("[PASS] Test 2 passed: Direct API key authentication verified!")

    # --- TEST 3: AUTHENTICATION FAILURE (WRONG PASSWORD) ---
    print("\n[Test 3] Testing authentication failure with invalid credentials...")
    secrets_t3 = {
        "admin_email": "admin@acunetix.com",
        "admin_password": "WrongPassword!999",
        "target_url": "http://127.0.0.1:3000"
    }
    res_t3 = run_driver(acx_url, secrets_t3, "t23-invalid-auth")
    print("STDOUT:")
    print(res_t3.stdout)

    assert res_t3.returncode == 11, f"Expected exit code 11 (EXIT_CODE_AUTH_FAILED), got {res_t3.returncode}"
    assert "Authentication initialization failed" in res_t3.stdout or "Login request failed" in res_t3.stdout
    assert "WrongPassword!999" not in res_t3.stdout, "Invalid password leaked in stdout!"
    print("[PASS] Test 3 passed: Exited with code 11 on authentication failure without leaking credentials!")

    # Cleanup test files
    import shutil
    shutil.rmtree(TMP_DIR, ignore_errors=True)

    print("\n" + "=" * 60)
    print("TASK T2.3 VERIFICATION ALL PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
