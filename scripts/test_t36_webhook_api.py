#!/usr/bin/env python3
"""
Test script for Task T3.6: Webhook Receiver API (Token Hash Comparison, State Checking, Size Limit, Idempotency).
Verifies:
1. Valid webhook dispatch with correct token -> 200 OK, state transitions SCANNING -> PARSING.
2. Results persisted in scan_results table (vulnerabilities, statistics, timings).
3. Invalid token rejected with 403 Forbidden.
4. Missing token header rejected with 401 Unauthorized.
5. Unknown scan_id rejected with 404 Not Found.
6. Payload size limit enforcement -> 413 Payload Too Large.
7. Idempotency: Multiple callbacks (driver retry) return 200 Ignored without corrupting DB.
8. Zero token leakage in logs or responses.
"""

import sys
import io
import json
import sqlite3
import threading
import logging
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.db.database import Database
from backend.models.scan import ScanJob, ScanRepository, hash_webhook_token
from backend.services.webhook_service import WebhookService, MAX_WEBHOOK_PAYLOAD_SIZE
from backend.api.webhook_handler import WebhookApiHandler
from backend.logging.logger import BackendSecretMaskingFilter

TMP_DB_PATH = BASE_DIR / "tmp" / "test_t36" / "test_deepreview.db"

class MockServerHandler(BaseHTTPRequestHandler):
    handler: WebhookApiHandler = None

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b""
        headers_dict = dict(self.headers)
        status, resp_headers, resp_body = MockServerHandler.handler.handle_request(
            "POST", self.path, body, headers_in=headers_dict
        )
        self.send_response(status)
        for k, v in resp_headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp_body)

    def log_message(self, format, *args):
        pass

def send_webhook_post(url: str, data: dict, token: str = None, auth_header: str = None, raw_body_override: bytes = None) -> tuple[int, dict]:
    body_bytes = raw_body_override if raw_body_override is not None else json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Webhook-Token"] = token
    if auth_header:
        headers["Authorization"] = auth_header

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
        return e.code, body

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.6 (WEBHOOK RECEIVER API)")
    print("=" * 70)

    TMP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TMP_DB_PATH.exists():
        TMP_DB_PATH.unlink()

    db = Database(str(TMP_DB_PATH))
    db.init_schema()
    repo = ScanRepository(db)

    # Setup logger with secret masking filter
    log_capture = io.StringIO()
    logger = logging.getLogger("test_webhook_logger")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    sh = logging.StreamHandler(log_capture)
    masking_filter = BackendSecretMaskingFilter()
    sh.addFilter(masking_filter)
    logger.addHandler(sh)

    webhook_service = WebhookService(
        repo=repo,
        logger=logger,
        max_payload_size=1024 * 1024  # 1MB limit for unit test demonstration
    )
    MockServerHandler.handler = WebhookApiHandler(webhook_service)

    server = HTTPServer(("127.0.0.1", 0), MockServerHandler)
    server_port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    webhook_url = f"http://127.0.0.1:{server_port}/api/v1/webhook"
    print(f"Webhook receiver listening on {webhook_url}")

    # Seed an active scan in SCANNING state
    scan_id = "scan-wb-001"
    raw_token = "secure-random-webhook-token-777888999"
    token_hash = hash_webhook_token(raw_token)
    masking_filter.add_secret(raw_token)

    scan_job = ScanJob(
        scan_id=scan_id,
        project_id="proj-finance",
        engine="acunetix",
        created_by="cuong.tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=token_hash
    )
    repo.create_scan(scan_job)
    print(f"Seeded scan {scan_id} with status 'SCANNING' and token_hash {token_hash[:16]}...")

    # Sample result payload from driver
    sample_payload = {
        "scan_id": scan_id,
        "status": "COMPLETED",
        "target_id": "target-uuid-123",
        "target_url": "http://127.0.0.1:3000",
        "vulnerabilities": [
            {"vuln_id": "vuln-01", "name": "SQL Injection", "severity": "high"}
        ],
        "severity_counts": {"critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0},
        "statistics": {"locations": 85, "requests": 210},
        "timings": {"total_duration_seconds": 65.4, "steps": []}
    }

    # ==========================================================
    # TEST 1: Valid Webhook with X-Webhook-Token Header
    # ==========================================================
    print("\n--- TEST 1: Valid Webhook Receipt & Transition to PARSING ---")
    st1, resp1 = send_webhook_post(webhook_url, sample_payload, token=raw_token)
    print(f"Response ({st1}): {resp1}")
    assert st1 == 200, f"Expected 200 OK, got {st1}"
    assert resp1["status"] == "accepted"
    assert resp1["next_state"] == "PARSING"

    # Verify state transition in DB
    updated_scan = repo.get_scan(scan_id)
    assert updated_scan.status == "PARSING", f"Expected PARSING, got {updated_scan.status}"

    # Verify results stored in DB
    res_record = repo.get_scan_result(scan_id)
    assert res_record is not None, "ScanResult not saved in DB!"
    assert res_record.vulnerabilities_count == 1
    assert res_record.statistics["locations"] == 85
    print("[PASS] Test 1 passed: Valid webhook accepted and state transitioned to PARSING.")

    # ==========================================================
    # TEST 2: Idempotency (Duplicate Webhook Callback)
    # ==========================================================
    print("\n--- TEST 2: Idempotency with Duplicate Callback ---")
    # Scan is now in 'PARSING' state. Driver retries sending exact same payload.
    st2, resp2 = send_webhook_post(webhook_url, sample_payload, token=raw_token)
    print(f"Duplicate callback response ({st2}): {resp2}")
    assert st2 == 200, f"Expected 200 OK for duplicate, got {st2}"
    assert resp2["status"] == "ignored"
    assert "Duplicate callback ignored" in resp2["message"]

    # Verify DB still has PARSING and results intact
    scan_after_dup = repo.get_scan(scan_id)
    assert scan_after_dup.status == "PARSING"
    res_after_dup = repo.get_scan_result(scan_id)
    assert res_after_dup.vulnerabilities_count == 1
    print("[PASS] Test 2 passed: Duplicate callback handled idempotently with zero data corruption.")

    # ==========================================================
    # TEST 3: Invalid Token Rejected (403 Forbidden)
    # ==========================================================
    print("\n--- TEST 3: Rejection of Invalid Webhook Token ---")
    # Seed a new scan in SCANNING state
    scan_id_2 = "scan-wb-002"
    repo.create_scan(ScanJob(
        scan_id=scan_id_2,
        project_id="p2",
        engine="acunetix",
        created_by="tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=token_hash
    ))

    st3, resp3 = send_webhook_post(webhook_url, {"scan_id": scan_id_2}, token="wrong-invalid-token")
    print(f"Invalid token response ({st3}): {resp3}")
    assert st3 == 403, f"Expected 403 Forbidden, got {st3}"
    assert "Invalid webhook authentication token" in resp3["error"]
    print("[PASS] Test 3 passed: Invalid token strictly rejected with 403.")

    # ==========================================================
    # TEST 4: Missing Token Header Rejected (401 Unauthorized)
    # ==========================================================
    print("\n--- TEST 4: Rejection of Missing Token Header ---")
    st4, resp4 = send_webhook_post(webhook_url, {"scan_id": scan_id_2})
    print(f"Missing token response ({st4}): {resp4}")
    assert st4 == 401, f"Expected 401 Unauthorized, got {st4}"
    assert "Missing required authentication token header" in resp4["error"]
    print("[PASS] Test 4 passed: Missing token rejected with 401.")

    # ==========================================================
    # TEST 5: Non-existent Scan ID Rejected (404 Not Found)
    # ==========================================================
    print("\n--- TEST 5: Rejection of Non-existent Scan ID ---")
    st5, resp5 = send_webhook_post(webhook_url, {"scan_id": "non-existent-scan-id"}, token=raw_token)
    print(f"Unknown scan response ({st5}): {resp5}")
    assert st5 == 404, f"Expected 404 Not Found, got {st5}"
    assert "not found" in resp5["error"]
    print("[PASS] Test 5 passed: Non-existent scan rejected with 404.")

    # ==========================================================
    # TEST 6: Payload Size Limit Enforcement (413 Payload Too Large)
    # ==========================================================
    print("\n--- TEST 6: Payload Size Limit Enforcement ---")
    # Send oversized body (> 1MB configured in test)
    oversized_bytes = b"x" * (1024 * 1024 + 100)
    st6, resp6 = send_webhook_post(
        webhook_url,
        {},
        token=raw_token,
        raw_body_override=oversized_bytes
    )
    print(f"Oversized payload response ({st6}): {resp6}")
    assert st6 == 413, f"Expected 413 Payload Too Large, got {st6}"
    assert "exceeds maximum limit" in resp6["error"]
    print("[PASS] Test 6 passed: Oversized payload rejected with 413.")

    # ==========================================================
    # TEST 7: Zero Raw Token Leakage in Logs
    # ==========================================================
    print("\n--- TEST 7: Zero Token Leakage in Logs ---")
    logged_output = log_capture.getvalue()
    assert raw_token not in logged_output, f"CRITICAL LEAK: Raw token '{raw_token}' found in logs!"
    print("[PASS] Test 7 passed: Log verified 100% clean with zero token leaks.")

    server.shutdown()
    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.6 PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    main()
