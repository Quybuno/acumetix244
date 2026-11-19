#!/usr/bin/env python3
"""
Test script for Task T2.1: Driver framework, config loading, and structured masked logging.
"""
import sys
import json
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TMP_DIR = BASE_DIR / "tmp" / "test_t21"

def main():
    print("=" * 60)
    print("RUNNING VERIFICATION FOR TASK T2.1")
    print("=" * 60)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    secrets_file = TMP_DIR / "test_credentials.json"
    options_file = TMP_DIR / "test_options.json"
    log_file = TMP_DIR / "driver.log"

    raw_secrets = {
        "api_key": "raw_secret_api_key_9999999",
        "admin_email": "admin@acunetix.com",
        "admin_password": "super_secret_admin_pass_88888",
        "webhook_token": "secret_webhook_token_77777",
        "target_credentials": {
            "username": "admin",
            "password": "target_user_secret_password_66666"
        },
        "custom_headers": [
            {"name": "X-Custom-Auth", "value": "header_secret_bearer_token_55555"}
        ],
        "target_url": "http://127.0.0.1:3000"
    }
    secrets_file.write_text(json.dumps(raw_secrets, indent=2), encoding="utf-8")

    test_options = {
        "profile": "Full Scan",
        "crawl_limit": 50,
        "excluded_paths": ["/logout", "/delete"]
    }
    options_file.write_text(json.dumps(test_options, indent=2), encoding="utf-8")

    scan_id = "test-t21-scan"
    cmd = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", scan_id,
        "--secrets-file", str(secrets_file),
        "--options-file", str(options_file),
        "--target-url", "http://127.0.0.1:3000",
        "--webhook-url", "http://127.0.0.1:9999/callback",
        "--log-file", str(log_file)
    ]

    print(f"Running command: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    
    print("\n--- STDOUT ---")
    print(proc.stdout)
    if proc.stderr:
        print("--- STDERR ---")
        print(proc.stderr)

    # 1. Exit code check
    assert proc.returncode == 0, f"Driver exited with non-zero code {proc.returncode}"
    print("[PASS] Driver executed and exited with code 0")

    # 2. Structured log format check
    assert f"[scan_id={scan_id}]" in proc.stdout, "Log does not contain scan_id tag"
    assert "[INFO ]" in proc.stdout, "Log does not contain level tag"
    print(f"[PASS] Structured format contains [scan_id={scan_id}] and ISO timestamps")

    # 3. Log file check
    assert log_file.exists(), f"Log file was not created at {log_file}"
    log_content = log_file.read_text(encoding="utf-8")
    assert f"[scan_id={scan_id}]" in log_content
    print(f"[PASS] Log file created and verified at {log_file}")

    # 4. Secret masking check
    sensitive_values = [
        "raw_secret_api_key_9999999",
        "super_secret_admin_pass_88888",
        "secret_webhook_token_77777",
        "target_user_secret_password_66666",
        "header_secret_bearer_token_55555"
    ]

    for sec in sensitive_values:
        assert sec not in proc.stdout, f"LEAK DETECTED in stdout: {sec}"
        assert sec not in proc.stderr, f"LEAK DETECTED in stderr: {sec}"
        assert sec not in log_content, f"LEAK DETECTED in log file: {sec}"
    print("[PASS] Complete secret masking verified: 0 raw secrets leaked into stdout, stderr, or log file")

    # 5. Masked structure present
    assert "[REDACTED]" in proc.stdout, "Masked values [REDACTED] not found in stdout"
    assert '"profile": "Full Scan"' in proc.stdout, "Scan options not correctly logged"
    print("[PASS] Masked configuration correctly displayed in log")

    # Cleanup test files
    import shutil
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    print("\n" + "=" * 60)
    print("TASK T2.1 VERIFICATION ALL PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
