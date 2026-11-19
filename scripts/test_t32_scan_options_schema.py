#!/usr/bin/env python3
"""
Test script for Task T3.2: Versioned ScanOptions schema for each engine and API handler.
Verifies:
1. Versioned schema for Acunetix (v1.0): 7 field groups, types, presets, dependencies, secret flags.
2. STRICT SECURITY & ABSTRACTION CHECK: Zero Acunetix internal field names leaked in schema.
3. Versioned schema for Fortify (v1.0): SAST fields, branch target.
4. HTTP API Endpoints tested live via HTTP server:
   - GET /api/v1/schemas/engines -> 200 OK
   - GET /api/v1/schemas/scan-options?engine=acunetix -> 200 OK
   - GET /api/v1/schemas/scan-options?engine=fortify -> 200 OK
   - GET /api/v1/schemas/scan-options?engine=invalid -> 400 Bad Request
   - GET /api/v1/schemas/scan-options (missing engine) -> 400 Bad Request
"""

import sys
import json
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.schemas.scan_options import (
    get_scan_options_schema,
    list_supported_engines,
    ACUNETIX_SCAN_OPTIONS_SCHEMA,
    FORTIFY_SCAN_OPTIONS_SCHEMA,
    ACUNETIX_INTERNAL_KEYWORDS,
    SCHEMA_VERSION
)
from backend.api.schema_handler import SchemaApiHandler

class MockHttpServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, headers, body = SchemaApiHandler.handle_request("GET", self.path)
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        status, headers, body = SchemaApiHandler.handle_request("OPTIONS", self.path)
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default server access logs in test output

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.2 (SCAN OPTIONS SCHEMAS & API)")
    print("=" * 70)

    # ==========================================================
    # TEST 1: Acunetix Schema Structure & Presets
    # ==========================================================
    print("\n--- TEST 1: Acunetix Schema Structure & Field Groups ---")
    acx_schema = get_scan_options_schema("acunetix")
    assert acx_schema["version"] == SCHEMA_VERSION, f"Expected version {SCHEMA_VERSION}"
    assert acx_schema["engine"] == "acunetix"
    assert len(acx_schema["groups"]) == 7, f"Expected 7 groups, got {len(acx_schema['groups'])}"

    group_ids = [g["id"] for g in acx_schema["groups"]]
    print(f"Group IDs: {group_ids}")
    expected_groups = ["target", "preset", "authentication", "imports", "headers", "scope", "advanced"]
    assert group_ids == expected_groups, f"Group IDs mismatch: {group_ids}"

    # Verify Target group
    target_fields = {f["name"]: f for f in acx_schema["groups"][0]["fields"]}
    assert "target_url" in target_fields, "Missing target_url field"
    assert target_fields["target_url"]["type"] == "url"
    assert target_fields["target_url"]["required"] is True

    # Verify Preset options
    preset_field = acx_schema["groups"][1]["fields"][0]
    preset_values = [opt["value"] for opt in preset_field["options"]]
    print(f"Preset options: {preset_values}")
    assert "fast_scan" in preset_values
    assert "deep_scan" in preset_values
    assert "crawl_only" in preset_values
    assert "owasp_top10" in preset_values

    # Verify Authentication & Conditional Dependencies
    auth_fields = {f["name"]: f for f in acx_schema["groups"][2]["fields"]}
    assert "login_type" in auth_fields
    assert "target_password" in auth_fields
    assert auth_fields["target_password"]["is_secret"] is True, "target_password must have is_secret=True"
    assert auth_fields["target_password"]["depends_on"] == {"field": "login_type", "value": "automatic"}
    assert auth_fields["login_sequence_file"]["depends_on"] == {"field": "login_type", "value": "sequence"}

    # Verify Custom Headers secret flag
    headers_field = acx_schema["groups"][4]["fields"][0]
    assert headers_field["name"] == "custom_headers"
    assert headers_field["is_secret"] is True, "custom_headers must have is_secret=True"

    print("[PASS] Acunetix schema structure, groups, dependencies, and secret flags verified.")

    # ==========================================================
    # TEST 2: STRICT CHECK - Zero Acunetix Internal Names Leaked
    # ==========================================================
    print("\n--- TEST 2: Strict Check: Zero Acunetix Internal Field Names in Schema ---")
    schema_dump = json.dumps(acx_schema)
    for kw in ACUNETIX_INTERNAL_KEYWORDS:
        assert kw not in schema_dump, f"LEAK DETECTED: Internal keyword '{kw}' found in public schema!"
    print(f"[PASS] Verified zero internal Acunetix field names ({len(ACUNETIX_INTERNAL_KEYWORDS)} keywords checked).")

    # ==========================================================
    # TEST 3: Fortify Schema Compatibility
    # ==========================================================
    print("\n--- TEST 3: Fortify Schema Compatibility ---")
    fortify_schema = get_scan_options_schema("fortify")
    assert fortify_schema["version"] == SCHEMA_VERSION
    assert fortify_schema["engine"] == "fortify"
    target_field = fortify_schema["groups"][0]["fields"][0]
    assert target_field["name"] == "git_branch"
    print("[PASS] Fortify schema compatibility verified.")

    # ==========================================================
    # TEST 4: Live HTTP API Endpoints
    # ==========================================================
    print("\n--- TEST 4: Live HTTP Schema API Endpoints ---")
    server = HTTPServer(("127.0.0.1", 0), MockHttpServerHandler)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{port}"
    print(f"Mock HTTP Server running on {base_url}")

    # Subtest 4.1: GET /api/v1/schemas/engines
    req1 = urllib.request.Request(f"{base_url}/api/v1/schemas/engines")
    with urllib.request.urlopen(req1) as resp:
        assert resp.status == 200
        data1 = json.loads(resp.read().decode())
        assert data1["status"] == "success"
        engines = [e["engine"] for e in data1["engines"]]
        assert "acunetix" in engines
        assert "fortify" in engines
        print(f"[OK] GET /api/v1/schemas/engines -> 200 OK (engines: {engines})")

    # Subtest 4.2: GET /api/v1/schemas/scan-options?engine=acunetix
    req2 = urllib.request.Request(f"{base_url}/api/v1/schemas/scan-options?engine=acunetix")
    with urllib.request.urlopen(req2) as resp:
        assert resp.status == 200
        data2 = json.loads(resp.read().decode())
        assert data2["status"] == "success"
        assert data2["schema"]["engine"] == "acunetix"
        assert data2["schema"]["version"] == "1.0"
        print("[OK] GET /api/v1/schemas/scan-options?engine=acunetix -> 200 OK")

    # Subtest 4.3: GET /api/v1/schemas/scan-options?engine=fortify
    req3 = urllib.request.Request(f"{base_url}/api/v1/schemas/scan-options?engine=fortify")
    with urllib.request.urlopen(req3) as resp:
        assert resp.status == 200
        data3 = json.loads(resp.read().decode())
        assert data3["status"] == "success"
        assert data3["schema"]["engine"] == "fortify"
        print("[OK] GET /api/v1/schemas/scan-options?engine=fortify -> 200 OK")

    # Subtest 4.4: GET /api/v1/schemas/scan-options?engine=invalid_engine (Expect 400)
    try:
        req4 = urllib.request.Request(f"{base_url}/api/v1/schemas/scan-options?engine=invalid_engine")
        urllib.request.urlopen(req4)
        raise AssertionError("Expected 400 Bad Request for unsupported engine!")
    except urllib.error.HTTPError as e:
        assert e.code == 400
        err_data = json.loads(e.read().decode())
        assert "Unsupported engine" in err_data["error"]
        print("[OK] GET /api/v1/schemas/scan-options?engine=invalid_engine -> 400 Bad Request (handled correctly)")

    # Subtest 4.5: GET /api/v1/schemas/scan-options (Missing engine param, Expect 400)
    try:
        req5 = urllib.request.Request(f"{base_url}/api/v1/schemas/scan-options")
        urllib.request.urlopen(req5)
        raise AssertionError("Expected 400 Bad Request for missing engine param!")
    except urllib.error.HTTPError as e:
        assert e.code == 400
        err_data = json.loads(e.read().decode())
        assert "Missing required query parameter" in err_data["error"]
        print("[OK] GET /api/v1/schemas/scan-options (missing engine) -> 400 Bad Request (handled correctly)")

    server.shutdown()
    print("[PASS] All live HTTP API endpoints verified successfully.")

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.2 PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    main()
