"""
Verification Script for Task T3.12: Role-Based Authorization and Project Isolation
Validates:
1. Engine permissions:
   - Only SECURITY_LEAD, SECURITY_ENGINEER, ADMIN can create Acunetix DAST scans.
   - DEVELOPER attempting to create Acunetix scan is rejected with 403 Forbidden.
   - DEVELOPER can create Fortify SAST scans.
   - AUDITOR / VIEWER rejected from creating any scans (403 Forbidden).
2. Project isolation:
   - User belonging to proj-alpha attempting to create/view/cancel scan in proj-beta is rejected with 403 Forbidden.
3. View permissions:
   - Authorized project members (DEVELOPER, AUDITOR, SECURITY_LEAD) can view results.
   - Non-members rejected with 403 Forbidden.
4. Cancellation permissions:
   - Only SECURITY_LEAD, SECURITY_ENGINEER, ADMIN can cancel scans.
   - DEVELOPER / AUDITOR attempting to cancel is rejected with 403 Forbidden.
5. ADMIN privileges:
   - ADMIN has full access across all engines and all projects.
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
from backend.models.scan import ScanJob, ScanRepository, hash_webhook_token
from backend.services.launcher import MockLauncher
from backend.services.state_machine import ScanStateMachine
from backend.services.scan_service import ScanService
from backend.auth.authorization import AuthorizationService, UserContext
from backend.api.scan_handler import ScanApiHandler

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

def send_auth_req(url: str, method: str = "GET", data: dict = None, user_id: str = "user", roles: str = "", projects: str = "") -> tuple[int, dict]:
    body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"}
    if user_id:
        headers["X-User-Id"] = user_id
    if roles:
        headers["X-User-Roles"] = roles
    if projects:
        headers["X-User-Projects"] = projects

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
        return e.code, body

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.12 (RBAC & PROJECT AUTHORIZATION)")
    print("=" * 70)

    tmp_db = PROJECT_ROOT / "tmp" / "test_t312_auth.db"
    tmp_db.parent.mkdir(parents=True, exist_ok=True)
    if tmp_db.exists():
        tmp_db.unlink()

    db = Database(str(tmp_db))
    db.init_schema()
    repo = ScanRepository(db)
    launcher = MockLauncher()
    state_machine = ScanStateMachine(repo)
    scan_service = ScanService(repo=repo, launcher=launcher, state_machine=state_machine, max_concurrent_scans=10)
    auth_service = AuthorizationService()

    api_handler = ScanApiHandler(scan_service=scan_service, auth_service=auth_service)
    MockServerHandler.handler = api_handler

    server = HTTPServer(("127.0.0.1", 0), MockServerHandler)
    server_port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server_port}/api/v1/scans"
    print(f"Auth verification server listening on {base_url}")

    # ==========================================================
    # TEST 1: Who can create Acunetix scans?
    # ==========================================================
    print("\n--- TEST 1: Engine Permission - Creating Acunetix DAST Scans ---")
    acunetix_payload = {
        "engine": "acunetix",
        "project_id": "proj-banking",
        "scan_options": {"target_url": "http://127.0.0.1:3000"}
    }

    # 1. DEVELOPER tries to create Acunetix scan -> MUST BE 403 FORBIDDEN
    st1_dev, res1_dev = send_auth_req(
        base_url, method="POST", data=acunetix_payload,
        user_id="dev_bob", roles="DEVELOPER", projects="proj-banking"
    )
    print(f"DEVELOPER Acunetix attempt ({st1_dev}): {res1_dev}")
    assert st1_dev == 403
    assert res1_dev["error_code"] == "FORBIDDEN"
    assert "lacks permission 'scan:create:acunetix'" in res1_dev["error"]
    print("[OK] DEVELOPER correctly rejected with 403 from creating Acunetix scan.")

    # 2. AUDITOR tries to create Acunetix scan -> MUST BE 403 FORBIDDEN
    st1_aud, res1_aud = send_auth_req(
        base_url, method="POST", data=acunetix_payload,
        user_id="auditor_dave", roles="AUDITOR", projects="proj-banking"
    )
    assert st1_aud == 403
    assert "lacks permission 'scan:create:acunetix'" in res1_aud["error"]
    print("[OK] AUDITOR correctly rejected with 403 from creating Acunetix scan.")

    # 3. SECURITY_ENGINEER creates Acunetix scan -> MUST BE 201 CREATED
    st1_sec, res1_sec = send_auth_req(
        base_url, method="POST", data=acunetix_payload,
        user_id="sec_alice", roles="SECURITY_ENGINEER", projects="proj-banking"
    )
    print(f"SECURITY_ENGINEER Acunetix creation ({st1_sec}): {res1_sec}")
    assert st1_sec == 201
    scan1_id = res1_sec["scan_id"]
    print(f"[OK] SECURITY_ENGINEER successfully created Acunetix scan: {scan1_id}")
    print("[PASS] Test 1 passed: Only authorized security roles can launch Acunetix scans.")

    # ==========================================================
    # TEST 2: Who can create Fortify scans?
    # ==========================================================
    print("\n--- TEST 2: Engine Permission - Creating Fortify SAST Scans ---")
    fortify_payload = {
        "engine": "fortify",
        "project_id": "proj-banking",
        "scan_options": {"git_branch": "main"}
    }

    # 1. DEVELOPER creates Fortify scan -> MUST BE 201 CREATED
    st2_dev, res2_dev = send_auth_req(
        base_url, method="POST", data=fortify_payload,
        user_id="dev_bob", roles="DEVELOPER", projects="proj-banking"
    )
    assert st2_dev == 201
    print(f"[OK] DEVELOPER permitted to create Fortify scan: {res2_dev['scan_id']}")

    # 2. VIEWER tries to create Fortify scan -> MUST BE 403 FORBIDDEN
    st2_vwr, res2_vwr = send_auth_req(
        base_url, method="POST", data=fortify_payload,
        user_id="viewer_charlie", roles="VIEWER", projects="proj-banking"
    )
    assert st2_vwr == 403
    assert "lacks permission 'scan:create:fortify'" in res2_vwr["error"]
    print("[OK] VIEWER correctly rejected from creating Fortify scan with 403.")
    print("[PASS] Test 2 passed: Fortify SAST permissions properly enforced.")

    # ==========================================================
    # TEST 3: Project-Level Isolation (Multi-tenant Boundary)
    # ==========================================================
    print("\n--- TEST 3: Project-Level Boundary Isolation ---")
    # Security engineer in proj-alpha tries to create scan in proj-secret
    foreign_project_payload = {
        "engine": "acunetix",
        "project_id": "proj-secret-payments",
        "scan_options": {"target_url": "http://127.0.0.1:3000"}
    }
    st3_proj, res3_proj = send_auth_req(
        base_url, method="POST", data=foreign_project_payload,
        user_id="sec_alice", roles="SECURITY_ENGINEER", projects="proj-banking"
    )
    print(f"Foreign project creation attempt ({st3_proj}): {res3_proj}")
    assert st3_proj == 403
    assert "does not have access to project 'proj-secret-payments'" in res3_proj["error"]
    print("[OK] Rejected scan creation across unauthorized project boundary with 403.")

    # User in proj-banking tries to list scans filtering for proj-secret-payments
    st3_list, res3_list = send_auth_req(
        f"{base_url}?project_id=proj-secret-payments",
        user_id="sec_alice", roles="SECURITY_ENGINEER", projects="proj-banking"
    )
    assert st3_list == 403
    assert "cannot list scans for unauthorized project" in res3_list["error"]
    print("[OK] Rejected scan listing for unauthorized project with 403.")
    print("[PASS] Test 3 passed: Multi-tenant project boundary strictly enforced.")

    # ==========================================================
    # TEST 4: View Permissions on Detailed Results
    # ==========================================================
    print("\n--- TEST 4: View Permissions on Scan Results ---")
    # 1. Project member (AUDITOR in proj-banking) views scan -> 200 OK
    st4_aud, res4_aud = send_auth_req(
        f"{base_url}/{scan1_id}",
        user_id="auditor_dave", roles="AUDITOR", projects="proj-banking"
    )
    assert st4_aud == 200
    assert res4_aud["scan_id"] == scan1_id
    print(f"[OK] Authorized project member (AUDITOR) viewed scan successfully.")

    # 2. Outsider (DEVELOPER in proj-healthcare) tries to view proj-banking scan -> 403 FORBIDDEN
    st4_out, res4_out = send_auth_req(
        f"{base_url}/{scan1_id}",
        user_id="dev_outsider", roles="DEVELOPER", projects="proj-healthcare"
    )
    print(f"Outsider view attempt ({st4_out}): {res4_out}")
    assert st4_out == 403
    assert "not authorized to access scan" in res4_out["error"]
    print("[OK] Outsider strictly blocked with 403 from viewing scan.")
    print("[PASS] Test 4 passed: View permissions and project boundaries enforced.")

    # ==========================================================
    # TEST 5: Cancellation Permissions
    # ==========================================================
    print("\n--- TEST 5: Scan Cancellation Permissions ---")
    # 1. DEVELOPER tries to cancel active scan -> 403 FORBIDDEN
    st5_dev, res5_dev = send_auth_req(
        f"{base_url}/{scan1_id}", method="DELETE",
        user_id="dev_bob", roles="DEVELOPER", projects="proj-banking"
    )
    print(f"DEVELOPER cancel attempt ({st5_dev}): {res5_dev}")
    assert st5_dev == 403
    assert "lacks 'scan:cancel' permission" in res5_dev["error"]
    print("[OK] DEVELOPER blocked with 403 from cancelling scan.")

    # 2. SECURITY_LEAD cancels active scan -> 200 OK
    st5_lead, res5_lead = send_auth_req(
        f"{base_url}/{scan1_id}", method="DELETE",
        user_id="lead_carol", roles="SECURITY_LEAD", projects="proj-banking"
    )
    assert st5_lead == 200
    assert res5_lead["status"] == "success"
    print("[OK] SECURITY_LEAD successfully cancelled active scan.")
    print("[PASS] Test 5 passed: Scan cancellation restricted to authorized security roles.")

    # ==========================================================
    # TEST 6: Administrator (ADMIN) Global Super-User Privileges
    # ==========================================================
    print("\n--- TEST 6: Administrator (ADMIN) Global Access ---")
    admin_payload = {
        "engine": "acunetix",
        "project_id": "proj-any-restricted",
        "scan_options": {"target_url": "http://127.0.0.1:3000"}
    }
    st6_admin, res6_admin = send_auth_req(
        base_url, method="POST", data=admin_payload,
        user_id="sysadmin", roles="ADMIN", projects="*"
    )
    assert st6_admin == 201
    admin_scan_id = res6_admin["scan_id"]
    print(f"[OK] ADMIN created Acunetix scan in any project: {admin_scan_id}")

    # ADMIN can view any scan
    st6_view, _ = send_auth_req(f"{base_url}/{admin_scan_id}", user_id="sysadmin", roles="ADMIN", projects="*")
    assert st6_view == 200

    # ADMIN can cancel any scan
    st6_cancel, _ = send_auth_req(f"{base_url}/{admin_scan_id}", method="DELETE", user_id="sysadmin", roles="ADMIN", projects="*")
    assert st6_cancel == 200
    print("[OK] ADMIN viewed and cancelled scan across all boundaries.")
    print("[PASS] Test 6 passed: ADMIN possesses unrestricted capabilities.")

    # Cleanup temp db
    server.shutdown()
    if tmp_db.exists():
        tmp_db.unlink()

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.12 PASSED SUCCESSFULLY (100%)!")
    print("=" * 70)

if __name__ == "__main__":
    main()
