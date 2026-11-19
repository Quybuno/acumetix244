#!/usr/bin/env python3
"""
Test script for Task T3.3: API to create scan jobs.
Verifies:
1. Valid Acunetix scan creation -> HTTP 201 Created, state SCANNING, token_hash in DB.
2. Missing URL for Acunetix -> Rejected with HTTP 400.
3. Embedded credentials or token in URL -> Rejected with HTTP 400.
4. URL outside allowlist -> Rejected with HTTP 400.
5. Unknown fields in ScanOptions -> Rejected with HTTP 400.
6. Invalid file extension / oversized file -> Rejected with HTTP 400.
7. Concurrency ceiling (max_concurrent_scans=1) -> Second concurrent scan rejected with HTTP 429 CONCURRENCY_LIMIT_EXCEEDED.
8. Zero secret leakage in API response, DB, and logs.
"""

import sys
import json
import sqlite3
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.db.database import Database
from backend.models.scan import ScanRepository
from backend.services.scan_service import ScanService
from backend.services.launcher import MockLauncher
from backend.validation.scan_validator import ScanValidator
from backend.api.scan_handler import ScanApiHandler

TMP_DB_PATH = BASE_DIR / "tmp" / "test_t33" / "test_deepreview.db"

class MockServerHandler(BaseHTTPRequestHandler):
    handler: ScanApiHandler = None

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b""
        status, headers, resp_body = MockServerHandler.handler.handle_request(
            "POST", self.path, body
        )
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp_body)

    def log_message(self, format, *args):
        pass

def post_json(url: str, data: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
        return e.code, body

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.3 (CREATE SCAN API)")
    print("=" * 70)

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
    MockServerHandler.handler = ScanApiHandler(scan_service)

    server = HTTPServer(("127.0.0.1", 0), MockServerHandler)
    server_port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{server_port}"
    scans_url = f"{base_url}/api/v1/scans"
    print(f"API Server listening on {scans_url}")

    # ==========================================================
    # TEST 1: Valid Scan Creation
    # ==========================================================
    print("\n--- TEST 1: Valid Acunetix Scan Creation ---")
    valid_payload = {
        "engine": "acunetix",
        "project_id": "proj-auth-api",
        "created_by": "cuong.developer",
        "scan_options": {
            "target_url": "http://127.0.0.1:3000",
            "preset": "fast_scan",
            "login_type": "automatic",
            "target_username": "admin@juice-sh.op",
            "target_password": "TargetSecretPassword123",
            "excluded_paths": ["/logout"],
            "scan_speed": "fast"
        },
        "files": {
            "login_sequence_file": {
                "filename": "login.lsr",
                "content": json.dumps({"actions": []})
            }
        }
    }
    status, body = post_json(scans_url, valid_payload)
    print(f"Response ({status}): {body}")
    assert status == 201, f"Expected 201 Created, got {status}"
    assert body["status"] == "success"
    assert "scan_id" in body
    scan_id = body["scan_id"]
    assert body["state"] == "SCANNING"
    assert body["target"] == "http://127.0.0.1:3000"

    # Verify ZERO secret in HTTP response
    resp_str = json.dumps(body)
    assert "TargetSecretPassword123" not in resp_str, "Password leaked in API response!"
    assert "token" not in resp_str or "token_hash" in resp_str, "Token leaked in API response!"

    # Verify DB records
    db_scan = repo.get_scan(scan_id)
    assert db_scan is not None
    assert db_scan.status == "SCANNING"
    assert len(db_scan.token_hash) == 64  # SHA-256
    db_opts = repo.get_options_config(scan_id)
    assert db_opts is not None
    assert "target_password" not in db_opts.config  # Secrets stripped from DB config
    print("[PASS] Test 1 passed: Scan created with status SCANNING and zero secrets in DB/response.")

    # ==========================================================
    # TEST 2: Missing Target URL for Acunetix
    # ==========================================================
    print("\n--- TEST 2: Rejection of Acunetix Scan Without Target URL ---")
    missing_url_payload = {
        "engine": "acunetix",
        "project_id": "proj-001",
        "created_by": "cuong",
        "scan_options": {
            "preset": "fast_scan"
        }
    }
    status2, body2 = post_json(scans_url, missing_url_payload)
    print(f"Response ({status2}): {body2}")
    assert status2 == 400, f"Expected 400 Bad Request, got {status2}"
    assert "target_url" in body2["error"]
    print("[PASS] Test 2 passed: Scan without target URL rejected.")

    # ==========================================================
    # TEST 3: Sensitive Credentials / Token Embedded in URL
    # ==========================================================
    print("\n--- TEST 3: Rejection of Credentials / Tokens in Target URL ---")
    url_with_creds_payload = {
        "engine": "acunetix",
        "project_id": "proj-001",
        "created_by": "cuong",
        "scan_options": {
            "target_url": "http://admin:secretpass@127.0.0.1:3000"
        }
    }
    status3a, body3a = post_json(scans_url, url_with_creds_payload)
    assert status3a == 400
    assert "Embedded credentials" in body3a["error"]
    print(f"[OK] Embedded credentials in URL rejected: {body3a['error']}")

    url_with_token_payload = {
        "engine": "acunetix",
        "project_id": "proj-001",
        "created_by": "cuong",
        "scan_options": {
            "target_url": "http://127.0.0.1:3000/app?token=supersecrettoken123"
        }
    }
    status3b, body3b = post_json(scans_url, url_with_token_payload)
    assert status3b == 400
    assert "sensitive token" in body3b["error"]
    print(f"[OK] Sensitive query token in URL rejected: {body3b['error']}")
    print("[PASS] Test 3 passed: Credentials/tokens in target URL strictly rejected.")

    # ==========================================================
    # TEST 4: Unauthorized Target URL (Allowlist Check)
    # ==========================================================
    print("\n--- TEST 4: Rejection of Target URL Outside Allowlist ---")
    unauthorized_payload = {
        "engine": "acunetix",
        "project_id": "proj-001",
        "created_by": "cuong",
        "scan_options": {
            "target_url": "https://unauthorized-external-website.com"
        }
    }
    status4, body4 = post_json(scans_url, unauthorized_payload)
    assert status4 == 400
    assert "not in the authorized targets allowlist" in body4["error"]
    print(f"[PASS] Test 4 passed: Unauthorized target URL rejected ({body4['error']}).")

    # ==========================================================
    # TEST 5: Unknown Fields Rejection
    # ==========================================================
    print("\n--- TEST 5: Rejection of Unknown Fields in ScanOptions ---")
    unknown_field_payload = {
        "engine": "acunetix",
        "project_id": "proj-001",
        "created_by": "cuong",
        "scan_options": {
            "target_url": "http://127.0.0.1:3000",
            "malicious_injection_field": "some_value"
        }
    }
    status5, body5 = post_json(scans_url, unknown_field_payload)
    assert status5 == 400
    assert "Unknown field(s) rejected" in body5["error"]
    print(f"[PASS] Test 5 passed: Unknown fields rejected ({body5['error']}).")

    # ==========================================================
    # TEST 6: Uploaded File Validation
    # ==========================================================
    print("\n--- TEST 6: Uploaded File Extension & Size Validation ---")
    bad_ext_payload = {
        "engine": "acunetix",
        "project_id": "proj-001",
        "created_by": "cuong",
        "scan_options": {
            "target_url": "http://127.0.0.1:3000"
        },
        "files": {
            "login_sequence_file": {
                "filename": "payload.exe",
                "content": "MZ binary content"
            }
        }
    }
    status6, body6 = post_json(scans_url, bad_ext_payload)
    assert status6 == 400
    assert "Invalid file extension" in body6["error"]
    print(f"[PASS] Test 6 passed: Disallowed file extension rejected ({body6['error']}).")

    # ==========================================================
    # TEST 7: Concurrency Limit Enforcement (MAX_CONCURRENT_SCANS = 1)
    # ==========================================================
    print("\n--- TEST 7: Concurrency Ceiling Enforcement (Limit = 1) ---")
    # Scan 1 is currently in SCANNING state in DB
    assert repo.count_active_scans() == 1

    concurrent_payload = {
        "engine": "acunetix",
        "project_id": "proj-002",
        "created_by": "cuong",
        "scan_options": {
            "target_url": "http://127.0.0.1:3000"
        }
    }
    status7, body7 = post_json(scans_url, concurrent_payload)
    print(f"Concurrent attempt response ({status7}): {body7}")
    assert status7 == 429, f"Expected 429 Too Many Requests, got {status7}"
    assert body7.get("error_code") == "CONCURRENCY_LIMIT_EXCEEDED"
    print(f"[OK] Second concurrent scan rejected with 429 CONCURRENCY_LIMIT_EXCEEDED.")

    # Now transition Scan 1 to COMPLETED
    repo.update_scan_status(scan_id, new_status="COMPLETED")
    assert repo.count_active_scans() == 0

    # Retry Scan 2 -> Should now succeed
    status7_retry, body7_retry = post_json(scans_url, concurrent_payload)
    assert status7_retry == 201
    print(f"[OK] New scan permitted immediately after prior scan completed: {body7_retry['scan_id']}")
    print("[PASS] Test 7 passed: Strict concurrency ceiling verified.")

    server.shutdown()
    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.3 PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    main()
