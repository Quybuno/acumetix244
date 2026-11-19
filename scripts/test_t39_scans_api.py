"""
Verification Script for Task T3.9: Scan Inspection and Cancellation APIs
Validates:
1. GET /api/v1/scans:
   - Filtering by project_id, engine, status.
   - Pagination (limit, offset).
   - Zero token_hash or secret leakage across entire list.
2. GET /api/v1/scans/{id}:
   - Detailed scan status, non-secret options, UnifiedReport results.
   - Findings count, severity breakdown, scan metrics, coverage warnings, timings.
   - Proper handling of active/running scan (report is None).
   - 404 on non-existent scan ID.
   - Strict zero secrets/token_hash in response.
3. DELETE /api/v1/scans/{id}:
   - Cancels active scan (SCANNING / PARSING).
   - Calls launcher.kill() and launcher.cleanup().
   - Transitions state to FAILED with error_code='CANCELLED_BY_USER'.
   - Concurrency ceiling released immediately.
   - Rejection (409 Conflict) when cancelling already finished scan (COMPLETED or FAILED).
   - 404 on non-existent scan ID.
"""

import sys
import os
import json
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.database import Database
from backend.models.scan import (
    ScanJob,
    ScanOptionsConfig,
    ScanResult,
    ScanRepository,
    hash_webhook_token
)
from backend.services.state_machine import ScanStateMachine
from backend.parsers.acunetix_parser import AcunetixReportParser
from backend.services.scan_service import ScanService
from backend.api.scan_handler import ScanApiHandler

class MockLauncherTracker:
    def __init__(self):
        self.launched = []
        self.killed = []
        self.cleaned = []

    def launch(self, scan_id, secrets, inputs=None, options=None):
        self.launched.append(scan_id)
        return {"status": "LAUNCHED", "scan_id": scan_id}

    def status(self, scan_id):
        return {"status": "RUNNING", "scan_id": scan_id}

    def kill(self, scan_id):
        self.killed.append(scan_id)
        return True

    def cleanup(self, scan_id):
        self.cleaned.append(scan_id)
        return True

class MockServerHandler(BaseHTTPRequestHandler):
    handler: ScanApiHandler = None

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")

    def _dispatch(self, method: str):
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
        headers_in = {k: v for k, v in self.headers.items()}

        status_code, resp_headers, resp_body = self.handler.handle_request(
            method=method,
            path=self.path,
            body_bytes=body_bytes,
            headers_in=headers_in
        )

        self.send_response(status_code)
        for k, v in resp_headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp_body)

    def log_message(self, format, *args):
        pass

def http_req(url: str, method: str = "GET", data: dict = None) -> tuple[int, dict]:
    body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"} if body_bytes else {}
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
        return e.code, body

def check_zero_secrets(data: any, path: str = "root"):
    """Recursively verify no token_hash, passwords, or raw tokens appear in data."""
    forbidden = ["token_hash", "admin_password", "target_password", "raw_token", "webhook_token"]
    if isinstance(data, dict):
        for k, v in data.items():
            for f in forbidden:
                assert f not in k.lower(), f"Security violation: Forbidden key '{k}' found at {path}"
            if "password" in k.lower() and v:
                assert False, f"Security violation: Password field '{k}' has value at {path}"
            check_zero_secrets(v, f"{path}.{k}")
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            check_zero_secrets(item, f"{path}[{idx}]")

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.9 (SCANS API & CANCELLATION)")
    print("=" * 70)

    tmp_db = PROJECT_ROOT / "tmp" / "test_t39_scans_api.db"
    tmp_db.parent.mkdir(parents=True, exist_ok=True)
    if tmp_db.exists():
        tmp_db.unlink()

    db = Database(str(tmp_db))
    db.init_schema()
    repo = ScanRepository(db)
    launcher = MockLauncherTracker()
    state_machine = ScanStateMachine(repo)
    parser = AcunetixReportParser()

    scan_service = ScanService(
        repo=repo,
        launcher=launcher,
        state_machine=state_machine,
        parser=parser,
        max_concurrent_scans=1
    )

    api_handler = ScanApiHandler(scan_service)
    MockServerHandler.handler = api_handler

    server = HTTPServer(("127.0.0.1", 0), MockServerHandler)
    server_port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server_port}/api/v1/scans"
    print(f"Test server running on {base_url}")

    # Seed data
    # Scan 1: COMPLETED with results (WebApp)
    s1 = ScanJob("scan-001", "proj-alpha", "acunetix", "alice", "COMPLETED", "http://127.0.0.1:3000", hash_webhook_token("tok1"))
    repo.create_scan(s1)
    repo.save_options_config(ScanOptionsConfig("scan-001", "1.0", {"preset": "fast_scan", "description": "Alpha Scan", "custom_header_names": ["X-Test"]}))
    repo.save_scan_result(ScanResult(
        scan_id="scan-001",
        status="COMPLETED",
        vulnerabilities_count=2,
        severity_counts={"CRITICAL": 1, "HIGH": 1, "MEDIUM": 0, "LOW": 0, "INFO": 0},
        vulnerabilities=[
            {"vt_name": "SQL Injection", "severity": 4, "affects_url": "http://127.0.0.1:3000/login", "tags": ["CWE-89"]},
            {"vt_name": "XSS", "severity": 3, "affects_url": "http://127.0.0.1:3000/search", "tags": ["CWE-79"]}
        ],
        statistics={"locations": 80, "requests": 500, "duration": 120.0},
        timings={"total_duration_seconds": 125.0},
        coverage_warnings=["LOW_COVERAGE"]
    ))

    # Scan 2: FAILED with error code
    s2 = ScanJob("scan-002", "proj-alpha", "acunetix", "alice", "FAILED", "http://127.0.0.1:3000", hash_webhook_token("tok2"), error_code="LOGIN_FAILED")
    repo.create_scan(s2)

    # Scan 3: Fortify engine scan
    s3 = ScanJob("scan-003", "proj-beta", "fortify", "bob", "COMPLETED", "git://repo.git", hash_webhook_token("tok3"))
    repo.create_scan(s3)

    # ==========================================================
    # TEST 1: GET /api/v1/scans (List Scans, Filters, Pagination)
    # ==========================================================
    print("\n--- TEST 1: GET /api/v1/scans (List, Filter, Pagination & Zero Secrets) ---")
    st, res = http_req(base_url)
    assert st == 200
    assert res["total"] == 3
    assert len(res["scans"]) == 3
    print(f"Total scans: {res['total']}, returned: {len(res['scans'])}")

    # Check zero secrets across entire list
    check_zero_secrets(res)
    for item in res["scans"]:
        assert "token_hash" not in item, "token_hash must not be present in public list"
    print("[OK] Confirmed zero token_hash or secrets in scans list.")

    # Filter by project_id
    st_p, res_p = http_req(f"{base_url}?project_id=proj-alpha")
    assert st_p == 200
    assert res_p["total"] == 2
    assert all(s["project_id"] == "proj-alpha" for s in res_p["scans"])
    print(f"[OK] Filter project_id=proj-alpha returned {res_p['total']} scans.")

    # Filter by engine
    st_e, res_e = http_req(f"{base_url}?engine=fortify")
    assert st_e == 200
    assert res_e["total"] == 1
    assert res_e["scans"][0]["engine"] == "fortify"
    print(f"[OK] Filter engine=fortify returned {res_e['total']} scans.")

    # Filter by status
    st_s, res_s = http_req(f"{base_url}?status=FAILED")
    assert st_s == 200
    assert res_s["total"] == 1
    assert res_s["scans"][0]["error_code"] == "LOGIN_FAILED"
    print(f"[OK] Filter status=FAILED returned scan with error_code='LOGIN_FAILED'.")

    # Pagination: limit=1, offset=1
    st_pg, res_pg = http_req(f"{base_url}?limit=1&offset=1")
    assert st_pg == 200
    assert len(res_pg["scans"]) == 1
    assert res_pg["limit"] == 1
    assert res_pg["offset"] == 1
    print("[PASS] Test 1 passed: List API with filtering, pagination, and zero secrets verified.")

    # ==========================================================
    # TEST 2: GET /api/v1/scans/{id} (Detailed Report with UnifiedReport)
    # ==========================================================
    print("\n--- TEST 2: GET /api/v1/scans/{id} (Detailed Report & UnifiedReport) ---")
    st2, res2 = http_req(f"{base_url}/scan-001")
    assert st2 == 200
    print(f"Scan ID: {res2['scan_id']} | Status: {res2['status']}")
    print(f"Summary: {res2['summary']}")
    print(f"Coverage warnings: {res2['coverage_warnings']}")
    print(f"Options keys: {list(res2['options'].keys())}")

    assert res2["scan_id"] == "scan-001"
    assert res2["status"] == "COMPLETED"
    assert res2["findings_count"] == 2
    assert res2["summary"]["severity_breakdown"]["CRITICAL"] == 1
    assert res2["summary"]["severity_breakdown"]["HIGH"] == 1
    assert "LOW_COVERAGE" in res2["coverage_warnings"]
    assert res2["options"]["preset"] == "fast_scan"
    assert res2["report"]["engine"] == "acunetix"
    assert len(res2["report"]["findings"]) == 2

    # Verify zero secrets in detail
    check_zero_secrets(res2)
    assert "token_hash" not in res2
    print("[PASS] Test 2 passed: Detailed scan report parsed with UnifiedReport and zero secrets.")

    # ==========================================================
    # TEST 3: GET /api/v1/scans/{id} for Active Scan Without Results
    # ==========================================================
    print("\n--- TEST 3: GET /api/v1/scans/{id} for Active Scan (report is None) ---")
    # Seed active scan
    s_act = ScanJob("scan-active-004", "proj-alpha", "acunetix", "alice", "SCANNING", "http://127.0.0.1:3000", hash_webhook_token("tok4"))
    repo.create_scan(s_act)
    st3, res3 = http_req(f"{base_url}/scan-active-004")
    assert st3 == 200
    assert res3["status"] == "SCANNING"
    assert res3["report"] is None
    assert res3["summary"] is None
    assert res3["coverage_warnings"] == []
    print(f"[PASS] Test 3 passed: Active scan gracefully returns status without results.")

    # ==========================================================
    # TEST 4: GET /api/v1/scans/{id} (Non-existent Scan ID -> 404)
    # ==========================================================
    print("\n--- TEST 4: GET /api/v1/scans/{id} (Non-existent -> 404) ---")
    st4, res4 = http_req(f"{base_url}/non-existent-scan-id")
    assert st4 == 404
    assert "not found" in res4["error"].lower()
    print(f"[PASS] Test 4 passed: Unknown scan rejected with 404 ({res4['error']}).")

    # ==========================================================
    # TEST 5: DELETE /api/v1/scans/{id} (Cancel Active Scan)
    # ==========================================================
    print("\n--- TEST 5: DELETE /api/v1/scans/{id} (Cancel Active Scan) ---")
    assert repo.count_active_scans() == 1  # scan-active-004 is SCANNING
    st5, res5 = http_req(f"{base_url}/scan-active-004", method="DELETE")
    print(f"Cancel response ({st5}): {res5}")
    assert st5 == 200
    assert res5["status"] == "success"
    assert res5["state"] == "FAILED"
    assert res5["error_code"] == "CANCELLED_BY_USER"

    # Verify launcher was called
    assert "scan-active-004" in launcher.killed
    assert "scan-active-004" in launcher.cleaned
    print(f"[OK] Verified launcher.kill() and launcher.cleanup() were called.")

    # Verify DB state
    updated_s = repo.get_scan("scan-active-004")
    assert updated_s.status == "FAILED"
    assert updated_s.error_code == "CANCELLED_BY_USER"
    assert updated_s.completed_at is not None
    print(f"[OK] DB status updated: {updated_s.status} (error_code='{updated_s.error_code}').")

    # Verify concurrency ceiling released
    assert repo.count_active_scans() == 0
    print(f"[OK] Concurrency ceiling released: active scans = {repo.count_active_scans()}.")
    print("[PASS] Test 5 passed: Scan cancellation completely cleans up and transitions state.")

    # ==========================================================
    # TEST 6: DELETE /api/v1/scans/{id} (Reject Cancel for Finished Scan -> 409)
    # ==========================================================
    print("\n--- TEST 6: DELETE /api/v1/scans/{id} (Reject Cancel on Finished Scan) ---")
    # Attempt to cancel COMPLETED scan-001
    st6_comp, res6_comp = http_req(f"{base_url}/scan-001", method="DELETE")
    assert st6_comp == 409
    assert "Cannot cancel scan 'scan-001' in terminal state 'COMPLETED'" in res6_comp["error"]
    print(f"[OK] Rejected cancelling COMPLETED scan with 409: {res6_comp['error']}")

    # Attempt to cancel already FAILED scan-002
    st6_fail, res6_fail = http_req(f"{base_url}/scan-002", method="DELETE")
    assert st6_fail == 409
    assert "Cannot cancel scan 'scan-002' in terminal state 'FAILED'" in res6_fail["error"]
    print(f"[OK] Rejected cancelling FAILED scan with 409: {res6_fail['error']}")
    print("[PASS] Test 6 passed: Cannot cancel scans already in terminal states.")

    # ==========================================================
    # TEST 7: DELETE /api/v1/scans/{id} (Non-existent Scan ID -> 404)
    # ==========================================================
    print("\n--- TEST 7: DELETE /api/v1/scans/{id} (Non-existent -> 404) ---")
    st7, res7 = http_req(f"{base_url}/non-existent-scan-id", method="DELETE")
    assert st7 == 404
    assert "not found" in res7["error"].lower()
    print(f"[PASS] Test 7 passed: Cancelling unknown scan rejected with 404.")

    # Cleanup temp db
    server.shutdown()
    if tmp_db.exists():
        tmp_db.unlink()

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.9 PASSED SUCCESSFULLY (100%)!")
    print("=" * 70)

if __name__ == "__main__":
    main()
