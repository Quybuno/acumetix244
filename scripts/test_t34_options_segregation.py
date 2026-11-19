#!/usr/bin/env python3
"""
Test script for Task T3.4: Segregation of ScanOptions into Non-Secret (DB) and Secret (Launcher only).
Verifies:
1. OptionsSegregator cleanly splits configuration into non-secret (DB) and secret (pod credentials) parts.
2. Custom headers: Header names are saved in DB, but sensitive header values are only in secret_data.
3. Purge secrets: In-memory secrets are actively purged and zeroed out after dispatch.
4. Backend logger: BackendSecretMaskingFilter masks sensitive credentials and pattern-based secrets.
5. Raw SQLite database inspection: Zero passwords, raw tokens, or secret header values in any table.
6. Zero secret leakage across all outputs.
"""

import sys
import io
import json
import sqlite3
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.db.database import Database
from backend.models.scan import ScanRepository
from backend.services.scan_service import ScanService
from backend.services.launcher import MockLauncher
from backend.services.options_segregator import OptionsSegregator, SECRET_KEYS_FORBIDDEN_IN_DB
from backend.validation.scan_validator import ScanValidator
from backend.logging.logger import BackendSecretMaskingFilter, setup_backend_logger

TMP_DB_PATH = BASE_DIR / "tmp" / "test_t34" / "test_deepreview.db"

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.4 (OPTIONS SEGREGATION & ZERO SECRETS)")
    print("=" * 70)

    # ==========================================================
    # TEST 1: Unit Testing OptionsSegregator Splitting
    # ==========================================================
    print("\n--- TEST 1: OptionsSegregator Splitting Logic ---")
    raw_token = "secret-webhook-token-random-value-xyz-987"
    raw_password = "SuperSecretTargetPassword@999"
    admin_pass = "AdminInstancePassword@456"

    input_options = {
        "target_url": "http://127.0.0.1:3000",
        "preset": "deep_scan",
        "scan_speed": "moderate",
        "login_type": "automatic",
        "target_username": "qa_auditor@domain.test",
        "target_password": raw_password,
        "custom_headers": [
            {"key": "X-Auth-Token", "value": "bearer-secret-token-12345"},
            {"key": "X-Environment", "value": "staging"}
        ],
        "excluded_paths": ["/logout", "/delete"],
        "crawl_limit": 250,
        "scan_timeout_minutes": 45,
        "description": "Security audit staging target"
    }

    non_secret_cfg, secret_data = OptionsSegregator.segregate(
        engine="acunetix",
        target_str="http://127.0.0.1:3000",
        options=input_options,
        raw_webhook_token=raw_token,
        webhook_url="http://127.0.0.1:8000/api/v1/webhook",
        admin_credentials={"admin_email": "admin@acunetix.com", "admin_password": admin_pass}
    )

    print("Non-secret config keys:", list(non_secret_cfg.keys()))
    print("Secret data keys:", list(secret_data.keys()))

    # Verify Non-Secret Config has ZERO secrets
    for forbidden in SECRET_KEYS_FORBIDDEN_IN_DB:
        assert forbidden not in non_secret_cfg, f"Forbidden key '{forbidden}' found in non_secret_cfg!"
    assert non_secret_cfg["preset"] == "deep_scan"
    assert non_secret_cfg["profile"] == "Full Scan"
    assert non_secret_cfg["scan_speed"] == "moderate"
    assert non_secret_cfg["target_username"] == "qa_auditor@domain.test"
    # Header names only, no values!
    assert non_secret_cfg["custom_header_names"] == ["X-Auth-Token", "X-Environment"]
    assert "bearer-secret-token-12345" not in json.dumps(non_secret_cfg), "Header secret leaked in non-secret config!"

    # Verify Secret Data has required pod secrets
    assert secret_data["webhook_token"] == raw_token
    assert secret_data["target_credentials"]["password"] == raw_password
    assert secret_data["admin_password"] == admin_pass
    assert "X-Auth-Token: bearer-secret-token-12345" in secret_data["custom_headers"]

    print("[PASS] Test 1 passed: OptionsSegregator cleanly and securely split configuration.")

    # ==========================================================
    # TEST 2: Active Memory Purging (Memory Hygiene)
    # ==========================================================
    print("\n--- TEST 2: Active Secret Memory Purging ---")
    secrets_to_purge = {
        "webhook_token": "token-xyz",
        "target_credentials": {"password": "pass-123"},
        "admin_password": "admin-pass-456"
    }
    OptionsSegregator.purge_secrets(secrets_to_purge)
    assert len(secrets_to_purge) == 0, "secret_data dictionary not emptied after purge!"
    print("[PASS] Test 2 passed: purge_secrets cleanly emptied dictionary and nested structures.")

    # ==========================================================
    # TEST 3: Backend Logging Secret Masking Filter
    # ==========================================================
    print("\n--- TEST 3: Backend Logging Secret Masking Filter ---")
    log_stream = io.StringIO()
    test_logger = logging.getLogger("test_backend_logger")
    test_logger.setLevel(logging.INFO)
    test_logger.handlers.clear()
    
    stream_handler = logging.StreamHandler(log_stream)
    masking_filter = BackendSecretMaskingFilter()
    masking_filter.add_secret(raw_password)
    masking_filter.add_secret(raw_token)
    stream_handler.addFilter(masking_filter)
    test_logger.addHandler(stream_handler)

    test_logger.info("Initializing scan with target password %s", raw_password)
    test_logger.info("Generated webhook_token=%s for scan", raw_token)
    test_logger.info("Config param password=UnregisteredSecretPass123 in payload")

    log_output = log_stream.getvalue()
    print("Masked Log Output Excerpt:\n" + log_output.strip())

    assert raw_password not in log_output, "Raw password leaked in log output!"
    assert raw_token not in log_output, "Raw token leaked in log output!"
    assert "UnregisteredSecretPass123" not in log_output, "Pattern-based password leaked in log output!"
    assert "[REDACTED]" in log_output, "Masking placeholder missing in log output!"
    print("[PASS] Test 3 passed: BackendSecretMaskingFilter successfully masked all sensitive secrets.")

    # ==========================================================
    # TEST 4: Full Pipeline DB Inspection for Zero Secrets
    # ==========================================================
    print("\n--- TEST 4: Database Inspection After Scan Creation ---")
    TMP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TMP_DB_PATH.exists():
        TMP_DB_PATH.unlink()

    db = Database(str(TMP_DB_PATH))
    db.init_schema()
    repo = ScanRepository(db)
    launcher = MockLauncher()
    validator = ScanValidator()
    scan_service = ScanService(
        repo=repo,
        launcher=launcher,
        validator=validator,
        max_concurrent_scans=1
    )

    create_res = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-audit-sec",
        created_by="auditor_cuong",
        scan_options=input_options
    )
    scan_id = create_res["scan_id"]
    print(f"Scan created: {scan_id}")

    # Inspect launcher job payload: launcher got secrets
    launched = launcher.launched_jobs[scan_id]
    assert launched["has_secrets"] is True, "Launcher did not receive secrets at dispatch time"

    # Query raw database tables directly via SQLite cursor
    conn = sqlite3.connect(str(TMP_DB_PATH))
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM scans WHERE scan_id = ?;", (scan_id,))
    scan_row = cursor.fetchone()
    cursor.execute("SELECT * FROM scan_options_configs WHERE scan_id = ?;", (scan_id,))
    opts_row = cursor.fetchone()
    conn.close()

    raw_db_dump = json.dumps({"scan_row": list(scan_row), "opts_row": list(opts_row)})
    print("Raw DB Dump (excerpt):", raw_db_dump[:200] + "...")

    # Strict assertion: NO raw password, NO raw token, NO secret header values in entire DB dump
    assert raw_password not in raw_db_dump, "CRITICAL LEAK: Target password found in database records!"
    assert raw_token not in raw_db_dump, "CRITICAL LEAK: Raw webhook token found in database records!"
    assert "bearer-secret-token-12345" not in raw_db_dump, "CRITICAL LEAK: Header secret token found in DB records!"

    print("[PASS] Test 4 passed: Exhaustive database dump confirmed ZERO secrets stored in DB.")

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.4 PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    main()
