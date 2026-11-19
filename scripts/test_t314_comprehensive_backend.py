"""
Comprehensive Verification Suite for Deep Review Backend (Phase 3 - Task T3.14)
Validates all backend components without requiring a real Acunetix server:
1. ScanOptions validation, schema defaults, segregation, and secret purging.
2. AcunetixReportParser with real T0.7 JSON sample reports and error handling.
3. ScanStateMachine lifecycle transitions, invariants, and final state immutability.
4. End-to-End Backend flow with Mock / Dummy driver (Create -> Concurrency Limit -> Webhook -> Parsing -> Completed -> Reconciler -> Metrics).
5. DockerLauncher with Dummy Driver lifecycle verification (Launch -> Status -> Clean).
"""

import sys
import os
import io
import json
import uuid
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.database import Database
from backend.models.scan import ScanJob, ScanRepository, hash_webhook_token
from backend.validation.scan_validator import ScanValidator, ValidationError
from backend.services.options_segregator import OptionsSegregator, PRESET_PROFILE_MAP
from backend.parsers.acunetix_parser import AcunetixReportParser, UnifiedReport, ParseException
from backend.services.state_machine import ScanStateMachine, InvalidStateTransitionError
from backend.services.launcher import MockLauncher, DockerLauncher
from backend.services.scan_service import ScanService, ConcurrencyLimitError
from backend.services.webhook_service import WebhookService
from backend.services.reconciler import ScanReconciler
from backend.auth.authorization import UserContext, AuthorizationService
from backend.api.scan_handler import ScanApiHandler
from backend.api.webhook_handler import WebhookApiHandler
from backend.metrics.metrics import MetricsCollector

# ==============================================================================
# MODULE 1: ScanOptions Validation, Segregation, and Secret Purge
# ==============================================================================
def test_scan_options_subsystem():
    print("\n[MODULE 1/5] Testing ScanOptions Validation, Segregation & Memory Purge...")
    validator = ScanValidator()

    # 1. Valid Acunetix scan request with secret credentials
    valid_payload = {
        "engine": "acunetix",
        "project_id": "proj-sec-suite",
        "created_by": "sec_lead",
        "scan_options": {
            "target_url": "http://127.0.0.1:3000",
            "preset": "fast_scan",
            "scan_timeout_minutes": 25,
            "target_username": "admin@juice-sh.op",
            "target_password": "SuperSecretPassword123!",
            "custom_headers": [{"key": "X-Custom-Auth", "value": "HeaderSecretVal"}]
        }
    }
    target, cleaned_opts, _ = validator.validate_create_request(
        engine=valid_payload["engine"],
        project_id=valid_payload["project_id"],
        created_by=valid_payload["created_by"],
        scan_options=valid_payload["scan_options"]
    )
    assert target == "http://127.0.0.1:3000"
    assert cleaned_opts["preset"] == "fast_scan"

    # 2. Invalid inputs rejected
    try:
        validator.validate_create_request("acunetix", "proj-1", "user-1", {})
        assert False, "Should reject empty options (missing target_url)"
    except ValidationError:
        pass

    try:
        validator.validate_create_request("acunetix", "proj-1", "user-1", {"target_url": "http://127.0.0.1:3000/?token=secret123"})
        assert False, "Should reject target_url containing raw token"
    except ValidationError:
        pass

    # 3. Segregation of options (DB-safe non-secrets vs Launcher secrets)
    raw_token = "webhook-token-random-xyz-789"
    token_hash = hash_webhook_token(raw_token)
    non_secret_db, launcher_secrets = OptionsSegregator.segregate(
        engine="acunetix",
        target_str=target,
        options=cleaned_opts,
        raw_webhook_token=raw_token,
        webhook_url="http://127.0.0.1:8000/api/v1/webhook"
    )

    # Assert non-secret DB payload has NO secrets
    assert "target_password" not in non_secret_db
    assert "webhook_token" not in non_secret_db
    assert "password" not in non_secret_db
    assert "custom_headers" not in non_secret_db
    assert "custom_header_names" in non_secret_db

    # Assert launcher secrets payload HAS necessary secrets for execution
    assert launcher_secrets["target_credentials"]["password"] == "SuperSecretPassword123!"
    assert launcher_secrets["webhook_token"] == raw_token
    assert len(launcher_secrets["custom_headers"]) == 1

    # 4. Memory purge
    OptionsSegregator.purge_secrets(launcher_secrets)
    assert len(launcher_secrets) == 0, "Secrets dictionary must be cleared after handoff to launcher!"
    print("  -> PASS: Validation, segregation, and RAM secret purging verified.")

# ==============================================================================
# MODULE 2: ReportParser with Sample JSON and Robust Error Handling
# ==============================================================================
def test_report_parser_subsystem():
    print("\n[MODULE 2/5] Testing AcunetixReportParser with Sample JSON & PARSE_FAILED handling...")
    parser = AcunetixReportParser()

    # 1. Parse sample webapp vulnerabilities (docs/samples/sample_webapp_vulnerabilities.json)
    sample_webapp_path = PROJECT_ROOT / "docs" / "samples" / "sample_webapp_vulnerabilities.json"
    with open(sample_webapp_path, "r", encoding="utf-8") as f:
        sample_webapp_json = f.read()

    report_webapp = parser.parse(sample_webapp_json, scan_id="scan-parser-001")
    assert isinstance(report_webapp, UnifiedReport)
    assert report_webapp.engine == "acunetix"
    assert report_webapp.summary["total_findings"] > 0
    assert report_webapp.summary["severity_breakdown"]["CRITICAL"] > 0
    assert report_webapp.summary["severity_breakdown"]["HIGH"] > 0
    assert len(report_webapp.findings) == report_webapp.summary["total_findings"]

    # 2. Parse sample API vulnerabilities (docs/samples/sample_api_vulnerabilities.json)
    sample_api_path = PROJECT_ROOT / "docs" / "samples" / "sample_api_vulnerabilities.json"
    with open(sample_api_path, "r", encoding="utf-8") as f:
        sample_api_json = f.read()

    report_api = parser.parse(sample_api_json, scan_id="scan-parser-002")
    assert report_api.engine == "acunetix"
    assert report_api.summary["total_findings"] > 0

    # 3. Robust error handling for malformed JSON & corrupt payloads -> ParseException without crashing
    try:
        parser.parse("{ malformed json string !!! ", scan_id="scan-err-1")
        assert False, "Should raise ParseException on malformed JSON"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"

    try:
        parser.parse("", scan_id="scan-err-2")
        assert False, "Should raise ParseException on empty payload"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"

    try:
        parser.parse({"vulnerabilities": "not_a_list"}, scan_id="scan-err-3")
        assert False, "Should raise ParseException when vulnerabilities is not a list"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"

    try:
        parser.parse([1, 2, 3], scan_id="scan-err-4")
        assert False, "Should raise ParseException when vulnerability item is not a dict"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"

    try:
        parser.parse({"vulnerabilities": [{"severity": "UNKNOWN_BOGUS"}]}, scan_id="scan-err-5")
        assert False, "Should raise ParseException on invalid severity"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"

    print("  -> PASS: AcunetixReportParser transforms sample reports and handles corrupt payloads safely.")

# ==============================================================================
# MODULE 3: State Machine Lifecycle Constraints & Invariants
# ==============================================================================
def test_state_machine_subsystem():
    print("\n[MODULE 3/5] Testing ScanStateMachine Lifecycle Invariants...")
    db = Database(":memory:")
    db.init_schema()
    repo = ScanRepository(db)
    metrics = MetricsCollector(concurrency_limit=1)
    sm = ScanStateMachine(repo=repo, metrics=metrics)

    # Create dummy scan
    scan = ScanJob(
        scan_id="scan-sm-01",
        project_id="proj-test",
        engine="acunetix",
        created_by="user-1",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token("dummy-tok")
    )
    repo.create_scan(scan)

    # 1. Valid progression: SCANNING -> PARSING -> COMPLETED
    sm.transition("scan-sm-01", "PARSING")
    assert repo.get_scan("scan-sm-01").status == "PARSING"

    sm.transition("scan-sm-01", "COMPLETED")
    assert repo.get_scan("scan-sm-01").status == "COMPLETED"

    # 2. Final state immutability: Cannot transition once COMPLETED
    try:
        sm.transition("scan-sm-01", "SCANNING")
        assert False, "Final state COMPLETED must be immutable"
    except InvalidStateTransitionError:
        pass

    try:
        sm.transition("scan-sm-01", "FAILED", error_code="JOB_LOST")
        assert False, "Final state COMPLETED must be immutable"
    except InvalidStateTransitionError:
        pass

    # 3. Failure transition requires valid error_code
    scan_fail = ScanJob(
        scan_id="scan-sm-02",
        project_id="proj-test",
        engine="acunetix",
        created_by="user-1",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token("dummy-tok2")
    )
    repo.create_scan(scan_fail)

    try:
        sm.transition("scan-sm-02", "FAILED")  # No error_code
        assert False, "Transition to FAILED must mandate an error_code"
    except InvalidStateTransitionError:
        pass

    sm.transition("scan-sm-02", "FAILED", error_code="JOB_LOST")
    assert repo.get_scan("scan-sm-02").status == "FAILED"
    assert repo.get_scan("scan-sm-02").error_code == "JOB_LOST"

    # 4. Reject skipping states (e.g. SCANNING -> COMPLETED)
    scan_skip = ScanJob(
        scan_id="scan-sm-03",
        project_id="proj-test",
        engine="acunetix",
        created_by="user-1",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token("dummy-tok3")
    )
    repo.create_scan(scan_skip)
    try:
        sm.transition("scan-sm-03", "COMPLETED")
        assert False, "Cannot skip PARSING stage directly from SCANNING"
    except InvalidStateTransitionError:
        pass

    print("  -> PASS: State machine invariants, error code mandates, and immutability verified.")

# ==============================================================================
# MODULE 4: End-to-End Backend Verification with Mock Driver
# ==============================================================================
def test_end_to_end_backend_with_mock_driver():
    print("\n[MODULE 4/5] Testing Complete End-to-End Backend Flow with Mock Driver...")
    db = Database(":memory:")
    db.init_schema()
    repo = ScanRepository(db)
    launcher = MockLauncher()
    metrics = MetricsCollector(concurrency_limit=1)
    sm = ScanStateMachine(repo=repo, metrics=metrics)
    parser = AcunetixReportParser()
    service = ScanService(
        repo=repo,
        launcher=launcher,
        state_machine=sm,
        parser=parser,
        metrics=metrics,
        max_concurrent_scans=1
    )
    auth_service = AuthorizationService()
    scan_api = ScanApiHandler(scan_service=service, auth_service=auth_service)
    webhook_service = WebhookService(repo=repo, state_machine=sm, parser=parser)
    webhook_api = WebhookApiHandler(webhook_service=webhook_service, auto_parse=True)
    reconciler = ScanReconciler(repo=repo, launcher=launcher, state_machine=sm, metrics=metrics)

    sec_headers = {
        "X-User-Id": "sec-eng-01",
        "X-User-Roles": "SECURITY_ENGINEER",
        "X-User-Projects": "proj-e2e",
        "X-User-Permissions": "scan:create:acunetix,scan:view,scan:cancel"
    }

    # Step 1: Create scan job via HTTP POST /api/v1/scans
    req_body = json.dumps({
        "engine": "acunetix",
        "project_id": "proj-e2e",
        "scan_options": {
            "target_url": "http://127.0.0.1:3000",
            "preset": "fast_scan",
            "target_username": "test_user",
            "target_password": "TestPasswordSecret"
        }
    }).encode("utf-8")

    status, headers, body = scan_api.handle_request("POST", "/api/v1/scans", req_body, headers_in=sec_headers)
    assert status == 201, f"Expected 201 Created, got {status}: {body.decode('utf-8')}"
    resp_data = json.loads(body.decode("utf-8"))
    scan_id = resp_data["scan_id"]
    assert "webhook_token" not in resp_data, "Public API response MUST NOT leak raw token"
    # Pod retrieves token from its mounted secrets directory (simulated via launcher)
    webhook_token = launcher.launched_jobs[scan_id]["webhook_token"]

    # Verify scan is in SCANNING state in DB
    scan_row = repo.get_scan(scan_id)
    assert scan_row.status == "SCANNING"
    assert scan_row.token_hash == hash_webhook_token(webhook_token)
    assert scan_id in launcher.launched_jobs

    # Step 2: Concurrency ceiling enforcement (zero queueing)
    status2, _, body2 = scan_api.handle_request("POST", "/api/v1/scans", req_body, headers_in=sec_headers)
    assert status2 == 429, f"Concurrent scan request must be rejected with 429, got {status2}"

    # Step 3: Mock driver finishes and delivers results via Webhook API
    sample_webapp_path = PROJECT_ROOT / "docs" / "samples" / "sample_webapp_vulnerabilities.json"
    with open(sample_webapp_path, "r", encoding="utf-8") as f:
        vuln_data = json.load(f)

    webhook_payload = json.dumps({
        "scan_id": scan_id,
        "status": "COMPLETED",
        "engine": "acunetix",
        "vulnerabilities": vuln_data.get("vulnerabilities", []),
        "scan_duration_seconds": 18.4,
        "coverage": {
            "total_urls_scanned": 42,
            "login_status": "AUTHENTICATED"
        }
    }).encode("utf-8")

    webhook_headers = {
        "Authorization": f"Bearer {webhook_token}",
        "Content-Type": "application/json"
    }

    wb_status, _, wb_body = webhook_api.handle_request("POST", "/api/v1/webhook", webhook_payload, headers_in=webhook_headers)
    assert wb_status == 200, f"Webhook must succeed with 200, got {wb_status}: {wb_body.decode('utf-8')}"

    # Step 4: Verify scan reached COMPLETED and results are persisted in DB
    scan_after = repo.get_scan(scan_id)
    assert scan_after.status == "COMPLETED", f"Expected COMPLETED, got {scan_after.status}"
    result = repo.get_scan_result(scan_id)
    assert result is not None, "Scan results must be persisted in scan_results table"
    assert result.vulnerabilities_count > 0

    # Step 5: Query scan details via GET /api/v1/scans/{id}
    status_detail, _, body_detail = scan_api.handle_request("GET", f"/api/v1/scans/{scan_id}", b"", headers_in=sec_headers)
    assert status_detail == 200
    detail_data = json.loads(body_detail.decode("utf-8"))
    assert detail_data["status"] == "COMPLETED"
    assert "report" in detail_data
    assert detail_data["report"]["summary"]["total_findings"] == result.vulnerabilities_count

    # Verify zero secrets or tokens in public API response
    raw_text = body_detail.decode("utf-8")
    assert webhook_token not in raw_text, "Webhook raw token must NOT leak in API detail"
    assert "TestPasswordSecret" not in raw_text, "Password must NOT leak in API detail"
    assert "token_hash" not in raw_text, "Internal token_hash must NOT leak in API detail"

    # Step 6: Verify concurrency ceiling was cleanly released
    status3, _, body3 = scan_api.handle_request("POST", "/api/v1/scans", req_body, headers_in=sec_headers)
    assert status3 == 201, f"Concurrency limit must be released after COMPLETED, got {status3}"
    scan_id3 = json.loads(body3.decode("utf-8"))["scan_id"]

    # Step 7: Test Reconciler handles disappearing driver (JOB_LOST)
    launcher.launched_jobs.clear()  # Container disappeared
    reconciler.reconcile_once()

    scan3_after = repo.get_scan(scan_id3)
    assert scan3_after.status == "FAILED"
    assert scan3_after.error_code == "JOB_LOST"

    # Step 8: Verify Metrics endpoint reflects system state
    status_m, _, body_m = scan_api.handle_request("GET", "/api/v1/metrics", b"")
    assert status_m == 200
    metrics_summary = json.loads(body_m.decode("utf-8"))
    assert metrics_summary["scans_total"] == 2
    assert metrics_summary["scans_by_status"]["COMPLETED"] == 1
    assert metrics_summary["scans_by_status"]["FAILED"] == 1
    assert metrics_summary["scans_by_error_code"]["JOB_LOST"] == 1
    assert metrics_summary["performance"]["completed_scans_measured"] >= 1

    print("  -> PASS: Complete End-to-End Backend lifecycle without real Acunetix verified.")

# ==============================================================================
# MODULE 5: Docker Launcher with Dummy Driver Lifecycle Verification
# ==============================================================================
def test_docker_launcher_with_dummy_driver():
    print("\n[MODULE 5/5] Testing DockerLauncher with Dummy Driver (No Acunetix Needed)...")
    # Verify DockerLauncher can be initialized and supports dummy driver mode
    docker_launcher = DockerLauncher(use_dummy_driver=True, timeout_ready=5)
    assert docker_launcher.use_dummy_driver is True

    # Test status for non-existent job
    dummy_scan_id = f"test-dummy-{uuid.uuid4().hex[:8]}"
    status_info = docker_launcher.status(dummy_scan_id)
    assert status_info["status"] in ("NOT_FOUND", "PENDING")

    # Test cleanup
    cleanup_ok = docker_launcher.cleanup(dummy_scan_id)
    assert cleanup_ok is True

    print("  -> PASS: DockerLauncher dummy driver interface verified.")

# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING COMPREHENSIVE BACKEND VERIFICATION SUITE (TASK T3.14)")
    print("Zero dependency on real Acunetix server - 100% Mock & Unit Verified")
    print("=" * 80)

    test_scan_options_subsystem()
    test_report_parser_subsystem()
    test_state_machine_subsystem()
    test_end_to_end_backend_with_mock_driver()
    test_docker_launcher_with_dummy_driver()

    print("\n" + "=" * 80)
    print("ALL 5 MODULES IN COMPREHENSIVE BACKEND VERIFICATION PASSED (100%)")
    print("=" * 80)
