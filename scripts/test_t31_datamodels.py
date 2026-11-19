#!/usr/bin/env python3
"""
Test script for Task T3.1: Backend Data Models & Relational Schema.
Verifies:
1. Database schema creates tables: scans, scan_options_configs, scan_results.
2. STRICT SECURITY CONSTRAINT: Zero secret columns in any table (no password, raw token, api_key, etc.).
3. Token hashing: Raw token is hashed with SHA-256; only token_hash is persisted.
4. Scan options configuration versioning (version 1.0) and secret exclusion.
5. Scan result recording: vulnerabilities, severity counts, statistics, timings.
6. State transitions: SCANNING -> PARSING -> COMPLETED / FAILED.
7. Full DB dump inspection confirms zero passwords, secrets, or raw tokens.
"""

import sys
import os
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.db.database import Database
from backend.models.scan import (
    ScanJob,
    ScanOptionsConfig,
    ScanResult,
    ScanRepository,
    hash_webhook_token,
    verify_webhook_token,
    VALID_ENGINES,
    VALID_STATUSES
)

TMP_DB_PATH = BASE_DIR / "tmp" / "test_t31" / "test_deepreview.db"

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.1 (BACKEND DATA MODELS & RELATIONAL SCHEMA)")
    print("=" * 70)

    TMP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TMP_DB_PATH.exists():
        TMP_DB_PATH.unlink()

    db = Database(str(TMP_DB_PATH))
    db.init_schema()
    print("[PASS] Database initialized and schema tables created.")

    # ==========================================================
    # TEST 1: Strict Zero Secret Columns Verification
    # ==========================================================
    print("\n--- TEST 1: Strict Verification of Zero Secret Columns ---")
    table_columns = db.get_all_columns()
    print("Discovered database tables and columns:")
    for tbl, cols in table_columns.items():
        print(f"  - Table '{tbl}': {cols}")

    assert "scans" in table_columns, "Table 'scans' missing"
    assert "scan_options_configs" in table_columns, "Table 'scan_options_configs' missing"
    assert "scan_results" in table_columns, "Table 'scan_results' missing"

    # Enforce zero secret column names
    db.verify_zero_secret_columns()
    print("[PASS] Zero secret columns in database schema verified.")

    # ==========================================================
    # TEST 2: Webhook Token Hashing & Verification
    # ==========================================================
    print("\n--- TEST 2: Webhook Token SHA-256 Hashing ---")
    raw_token = "ephemeral-random-token-xyz-987"
    token_hash = hash_webhook_token(raw_token)
    assert len(token_hash) == 64, f"Expected 64-char hex SHA-256 hash, got {len(token_hash)}"
    assert token_hash != raw_token, "Token hash must differ from raw token"
    assert verify_webhook_token(raw_token, token_hash) is True, "Token verification failed for valid token"
    assert verify_webhook_token("wrong-token", token_hash) is False, "Token verification succeeded for invalid token"
    print(f"[PASS] Token SHA-256 hashing verified: {token_hash[:16]}... (raw token never stored)")

    # ==========================================================
    # TEST 3: Scan Creation and State Transitions
    # ==========================================================
    print("\n--- TEST 3: Scan Job Creation and Lifecycle Transitions ---")
    repo = ScanRepository(db)

    scan_id = "scan-acx-001"
    scan_job = ScanJob(
        scan_id=scan_id,
        project_id="proj-finance-api",
        engine="acunetix",
        created_by="user_cuong",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=token_hash
    )
    repo.create_scan(scan_job)
    print(f"[OK] Scan {scan_id} created with initial status 'SCANNING'.")

    # Fetch scan
    fetched_scan = repo.get_scan(scan_id)
    assert fetched_scan is not None, "Failed to retrieve scan from DB"
    assert fetched_scan.scan_id == scan_id
    assert fetched_scan.engine == "acunetix"
    assert fetched_scan.status == "SCANNING"
    assert fetched_scan.token_hash == token_hash

    # Transition: SCANNING -> PARSING
    repo.update_scan_status(scan_id, new_status="PARSING")
    fetched_parsing = repo.get_scan(scan_id)
    assert fetched_parsing.status == "PARSING"
    print(f"[OK] Scan transitioned: SCANNING -> PARSING.")

    # Transition: PARSING -> COMPLETED
    repo.update_scan_status(scan_id, new_status="COMPLETED", completed_at="2026-11-19T12:00:00Z")
    fetched_completed = repo.get_scan(scan_id)
    assert fetched_completed.status == "COMPLETED"
    assert fetched_completed.completed_at == "2026-11-19T12:00:00Z"
    print(f"[OK] Scan transitioned: PARSING -> COMPLETED.")

    # ==========================================================
    # TEST 4: Versioned ScanOptions Configuration (Zero Secrets)
    # ==========================================================
    print("\n--- TEST 4: Versioned ScanOptions Configuration ---")
    clean_config = {
        "profile": "Full Scan",
        "scan_speed": "fast",
        "limit_crawler_scope": True,
        "crawl_limit": 50,
        "excluded_paths": ["/logout", "/admin/delete"],
        "user_agent": "DeepReview-Agent/1.0"
    }
    opt_config = ScanOptionsConfig(
        scan_id=scan_id,
        version="1.0",
        config=clean_config
    )
    repo.save_options_config(opt_config)
    print(f"[OK] Scan options config v1.0 saved for {scan_id}.")

    fetched_opts = repo.get_options_config(scan_id)
    assert fetched_opts is not None, "Failed to retrieve options config"
    assert fetched_opts.version == "1.0"
    assert fetched_opts.config["profile"] == "Full Scan"
    assert fetched_opts.config["excluded_paths"] == ["/logout", "/admin/delete"]

    # Verify attempt to store secret in config raises security exception
    secret_leak_attempt = {
        "profile": "fast",
        "admin_password": "LeakedPassword123"
    }
    try:
        ScanOptionsConfig(scan_id="test", version="1.0", config=secret_leak_attempt)
        raise AssertionError("Security flaw: ScanOptionsConfig permitted storing 'admin_password'!")
    except ValueError as e:
        print(f"[PASS] Model rejected secret in config dict as expected: {e}")

    # ==========================================================
    # TEST 5: Scan Result Recording
    # ==========================================================
    print("\n--- TEST 5: Scan Results Persistence ---")
    mock_vulns = [
        {
            "vuln_id": "v-001",
            "vt_name": "SQL Injection",
            "severity": "high",
            "affects_url": "http://127.0.0.1:3000/rest/products"
        },
        {
            "vuln_id": "v-002",
            "vt_name": "Cross-site Scripting (XSS)",
            "severity": "medium",
            "affects_url": "http://127.0.0.1:3000/#/search"
        }
    ]
    mock_stats = {
        "duration": "105s",
        "locations_discovered": 123,
        "request_count": 450
    }
    mock_timings = {
        "total_duration_seconds": 106.88,
        "steps": [
            {"name": "Scan Execution", "duration": 85.36, "status": "SUCCESS"},
            {"name": "Target Cleanup", "duration": 0.30, "status": "SUCCESS"}
        ]
    }
    scan_res = ScanResult(
        scan_id=scan_id,
        status="COMPLETED",
        vulnerabilities_count=2,
        severity_counts={"critical": 0, "high": 1, "medium": 1, "low": 0, "info": 0},
        vulnerabilities=mock_vulns,
        statistics=mock_stats,
        timings=mock_timings,
        coverage_warnings=[]
    )
    repo.save_scan_result(scan_res)
    print(f"[OK] Scan result saved for {scan_id}.")

    fetched_res = repo.get_scan_result(scan_id)
    assert fetched_res is not None, "Failed to retrieve scan result"
    assert fetched_res.vulnerabilities_count == 2
    assert fetched_res.severity_counts["high"] == 1
    assert len(fetched_res.vulnerabilities) == 2
    assert fetched_res.statistics["locations_discovered"] == 123
    assert fetched_res.timings["total_duration_seconds"] == 106.88
    print("[PASS] Scan result data retrieved and validated successfully.")

    # ==========================================================
    # TEST 6: Raw DB Inspection (Zero Secret Leakage Verification)
    # ==========================================================
    print("\n--- TEST 6: Exhaustive Raw DB Dump Inspection ---")
    conn = sqlite3.connect(str(TMP_DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scans;")
    scans_dump = cursor.fetchall()
    cursor.execute("SELECT * FROM scan_options_configs;")
    opts_dump = cursor.fetchall()
    cursor.execute("SELECT * FROM scan_results;")
    res_dump = cursor.fetchall()
    conn.close()

    raw_dump_str = json.dumps({"scans": [list(r) for r in scans_dump], "opts": [list(r) for r in opts_dump], "res": [list(r) for r in res_dump]})

    forbidden_patterns = [
        raw_token,
        "Acunetix@123",
        "JuicePassword123",
        "LeakedPassword123"
    ]
    for pattern in forbidden_patterns:
        assert pattern not in raw_dump_str, f"LEAK DETECTED: Found secret '{pattern}' in database records!"

    print("[PASS] Raw database dump verified: Zero passwords, raw tokens, or secrets exist anywhere in DB.")

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.1 PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    main()
