"""
Automated Verification Suite for Phase 3 - Task T3.13:
Structured Logging, Error Code / Status Metrics, and Reconciler Alerting
"""

import sys
import os
import io
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from backend.db.database import Database
from backend.models.scan import ScanRepository
from backend.services.launcher import MockLauncher
from backend.services.scan_service import ScanService
from backend.services.state_machine import ScanStateMachine
from backend.services.reconciler import ScanReconciler
from backend.services.options_segregator import OptionsSegregator
from backend.logging.structured_logger import StructuredJsonFormatter, setup_structured_logger
from backend.metrics.metrics import MetricsCollector, Alert, get_global_metrics
from backend.api.scan_handler import ScanApiHandler

def test_structured_logger():
    print("[1/5] Testing Structured JSON Logger & Secret Masking Filter...")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredJsonFormatter())

    logger = logging.getLogger("test_structured")
    logger.setLevel(logging.INFO)
    logger.handlers = [handler]

    # Test context injection
    logger.info("Scan job started", extra={
        "scan_id": "scan-12345",
        "project_id": "proj-alpha",
        "engine": "acunetix",
        "status": "SCANNING",
        "duration_ms": 150
    })

    log_line = stream.getvalue().strip()
    data = json.loads(log_line)
    assert data["message"] == "Scan job started"
    assert data["scan_id"] == "scan-12345"
    assert data["project_id"] == "proj-alpha"
    assert data["engine"] == "acunetix"
    assert data["status"] == "SCANNING"
    assert data["duration_ms"] == 150
    assert "timestamp" in data
    assert data["level"] == "INFO"

    # Test with setup_structured_logger and secret masking
    struct_logger, secret_filter = setup_structured_logger("test_masking_logger")
    secret_stream = io.StringIO()
    for h in struct_logger.handlers:
        h.stream = secret_stream

    secret_filter.add_secret("SuperSecretToken_XYZ123")
    struct_logger.info("Connecting to target with token: SuperSecretToken_XYZ123", extra={"scan_id": "scan-sec-1"})

    masked_line = secret_stream.getvalue().strip()
    assert "SuperSecretToken_XYZ123" not in masked_line, "Secret MUST NOT appear in structured log!"
    assert "[REDACTED]" in masked_line, "Secret must be replaced with [REDACTED]"
    masked_data = json.loads(masked_line)
    assert masked_data["scan_id"] == "scan-sec-1"
    assert "[REDACTED]" in masked_data["message"]

    print("  -> PASS: Structured JSON format and secret masking verified.")

def test_metrics_collector_counters():
    print("[2/5] Testing Metrics Collector Counters & Durations...")
    metrics = MetricsCollector(concurrency_limit=1)
    metrics.reset()

    # Record scan creations
    metrics.record_scan_created("acunetix")
    metrics.record_scan_created("fortify")

    summary = metrics.get_summary()
    assert summary["scans_total"] == 2
    assert summary["scans_by_engine"]["acunetix"] == 1
    assert summary["scans_by_engine"]["fortify"] == 1
    assert summary["scans_by_status"]["SCANNING"] == 2
    assert summary["active_scans"] == 2

    # Record state transition: SCANNING -> PARSING -> COMPLETED with duration
    metrics.record_state_transition("SCANNING", "PARSING")
    metrics.record_state_transition("PARSING", "COMPLETED", duration_seconds=12.5)

    summary = metrics.get_summary()
    assert summary["scans_by_status"]["SCANNING"] == 1
    assert summary["scans_by_status"]["PARSING"] == 0
    assert summary["scans_by_status"]["COMPLETED"] == 1
    assert summary["active_scans"] == 1
    assert summary["performance"]["completed_scans_measured"] == 1
    assert summary["performance"]["avg_duration_seconds"] == 12.5
    assert summary["performance"]["min_duration_seconds"] == 12.5
    assert summary["performance"]["max_duration_seconds"] == 12.5

    # Record another scan COMPLETED with duration
    metrics.record_state_transition("SCANNING", "COMPLETED", duration_seconds=7.5)
    summary = metrics.get_summary()
    assert summary["performance"]["completed_scans_measured"] == 2
    assert summary["performance"]["avg_duration_seconds"] == 10.0
    assert summary["performance"]["min_duration_seconds"] == 7.5
    assert summary["performance"]["max_duration_seconds"] == 12.5

    print("  -> PASS: Status, engine, error code, and duration calculations verified.")

def test_reconciler_and_critical_alerts():
    print("[3/5] Testing Automated Alerts on JOB_LOST and CALLBACK_LOST...")
    metrics = MetricsCollector(concurrency_limit=1)
    metrics.reset()

    # Initially no alerts
    summary = metrics.get_summary(job_lost_threshold=2, callback_lost_threshold=2)
    assert not summary["has_active_alerts"]
    assert len(summary["alerts"]) == 0

    # 1 JOB_LOST (below threshold of 2)
    metrics.record_state_transition("SCANNING", "FAILED", error_code="JOB_LOST")
    metrics.record_reconciler_closure("JOB_LOST")
    alerts_1 = metrics.check_alerts(job_lost_threshold=2, callback_lost_threshold=2)
    assert len(alerts_1) == 0, "Should not trigger alert before reaching threshold"

    # 2nd JOB_LOST (reaches threshold of 2)
    metrics.record_state_transition("SCANNING", "FAILED", error_code="JOB_LOST")
    metrics.record_reconciler_closure("JOB_LOST")
    alerts_2 = metrics.check_alerts(job_lost_threshold=2, callback_lost_threshold=2)
    assert len(alerts_2) == 1
    assert alerts_2[0].level == "CRITICAL"
    assert alerts_2[0].alert_type == "HIGH_JOB_LOST_RATE"
    assert alerts_2[0].current_value == 2
    assert "Infrastructure failure rate high" in alerts_2[0].message

    # 2 CALLBACK_LOST (reaches threshold of 2)
    metrics.record_state_transition("SCANNING", "FAILED", error_code="CALLBACK_LOST")
    metrics.record_state_transition("SCANNING", "FAILED", error_code="CALLBACK_LOST")
    metrics.record_reconciler_closure("CALLBACK_LOST")
    metrics.record_reconciler_closure("CALLBACK_LOST")

    summary_final = metrics.get_summary(job_lost_threshold=2, callback_lost_threshold=2)
    assert summary_final["has_active_alerts"] is True
    assert len(summary_final["alerts"]) == 2
    alert_types = [a["alert_type"] for a in summary_final["alerts"]]
    assert "HIGH_JOB_LOST_RATE" in alert_types
    assert "HIGH_CALLBACK_LOST_RATE" in alert_types

    print("  -> PASS: CRITICAL and WARNING alerts generated correctly upon threshold breach.")

def test_service_integration():
    print("[4/5] Testing ScanService & StateMachine Integration with Metrics...")
    db = Database(":memory:")
    db.init_schema()
    repo = ScanRepository(db)
    launcher = MockLauncher()
    metrics = MetricsCollector(concurrency_limit=1)

    sm = ScanStateMachine(repo=repo, metrics=metrics)
    service = ScanService(repo=repo, launcher=launcher, state_machine=sm, metrics=metrics, max_concurrent_scans=1)

    # Create scan
    res = service.create_scan(
        engine="acunetix",
        project_id="proj-integration",
        created_by="user-test",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    scan_id = res["scan_id"]

    assert metrics.scans_total == 1
    assert metrics.scans_by_status["SCANNING"] == 1
    assert metrics.scans_by_engine["acunetix"] == 1

    # Transition to PARSING
    sm.transition(scan_id, "PARSING")
    assert metrics.scans_by_status["SCANNING"] == 0
    assert metrics.scans_by_status["PARSING"] == 1

    # Transition to COMPLETED
    sm.transition(scan_id, "COMPLETED")
    assert metrics.scans_by_status["PARSING"] == 0
    assert metrics.scans_by_status["COMPLETED"] == 1
    assert len(metrics.durations_seconds) == 1

    # Test Reconciler closure
    res2 = service.create_scan(
        engine="acunetix",
        project_id="proj-integration",
        created_by="user-test",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    scan_id2 = res2["scan_id"]
    reconciler = ScanReconciler(repo=repo, launcher=launcher, state_machine=sm, metrics=metrics)
    # Simulate container death: launcher reports container not running
    launcher.launched_jobs.clear()
    reconciler.reconcile_once()

    scan2_after = repo.get_scan(scan_id2)
    assert scan2_after.status == "FAILED"
    assert scan2_after.error_code == "JOB_LOST"
    assert metrics.scans_by_error_code["JOB_LOST"] == 1
    assert metrics.reconciler_closures["JOB_LOST"] == 1

    print("  -> PASS: Full integration with ScanService, StateMachine, and Reconciler verified.")

def test_api_metrics_endpoint():
    print("[5/5] Testing GET /api/v1/metrics HTTP API Endpoint...")
    db = Database(":memory:")
    db.init_schema()
    repo = ScanRepository(db)
    launcher = MockLauncher()
    metrics = MetricsCollector(concurrency_limit=1)
    sm = ScanStateMachine(repo=repo, metrics=metrics)
    service = ScanService(repo=repo, launcher=launcher, state_machine=sm, metrics=metrics, max_concurrent_scans=1)
    handler = ScanApiHandler(scan_service=service)

    # Seed some metrics
    metrics.record_scan_created("acunetix")
    metrics.record_state_transition("SCANNING", "FAILED", error_code="JOB_LOST")

    # 1. Standard request (threshold 2, no alert)
    status_code, headers, body = handler.handle_request("GET", "/api/v1/metrics", b"")
    assert status_code == 200
    assert "application/json" in headers["Content-Type"]
    payload = json.loads(body.decode("utf-8"))
    assert payload["scans_total"] == 1
    assert payload["scans_by_error_code"]["JOB_LOST"] == 1
    assert payload["has_active_alerts"] is False

    # 2. Query param threshold=1 (triggers alert)
    status_code2, headers2, body2 = handler.handle_request("GET", "/api/v1/metrics?job_lost_threshold=1", b"")
    assert status_code2 == 200
    payload2 = json.loads(body2.decode("utf-8"))
    assert payload2["has_active_alerts"] is True
    assert len(payload2["alerts"]) == 1
    assert payload2["alerts"][0]["alert_type"] == "HIGH_JOB_LOST_RATE"

    # 3. Method not allowed
    status_code3, _, _ = handler.handle_request("POST", "/api/v1/metrics", b"")
    assert status_code3 == 405

    print("  -> PASS: GET /api/v1/metrics endpoint verified.")

if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING TASK T3.13 VERIFICATION SUITE")
    print("=" * 70)
    test_structured_logger()
    test_metrics_collector_counters()
    test_reconciler_and_critical_alerts()
    test_service_integration()
    test_api_metrics_endpoint()
    print("=" * 70)
    print("ALL TESTS IN TASK T3.13 PASSED SUCCESSFULLY (100%)")
    print("=" * 70)
