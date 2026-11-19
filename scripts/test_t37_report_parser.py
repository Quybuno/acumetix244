"""
Verification Script for Task T3.7: Acunetix ReportParser to UnifiedReport
Validates:
1. Transforming sample Acunetix WebApp vulnerability JSON (T0.7) to UnifiedReport.
2. Severity mapping (0-4 / strings -> CRITICAL, HIGH, MEDIUM, LOW, INFO).
3. Extraction of locations (affects_url), parameters (affects_detail), CWE, CVE, CVSS.
4. Parsing sample API vulnerabilities (T0.7) and empty sample.
5. Parsing detailed single vulnerability payload (sample_vulnerability_detail_critical.json).
6. Parsing full webhook payload with statistics, timings, and coverage warnings.
7. Robust error handling on malformed JSON / missing fields -> raises ParseException (error_code='PARSE_FAILED').
8. End-to-end integration with WebhookService: parsing failure sets scan status to FAILED with error_code='PARSE_FAILED' without crashing the backend process.
"""

import os
import sys
import json
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.database import Database
from backend.models.scan import ScanJob, ScanRepository, hash_webhook_token
from backend.parsers.acunetix_parser import (
    AcunetixReportParser,
    UnifiedReport,
    UnifiedFinding,
    ParseException
)
from backend.services.webhook_service import WebhookService

def test_webapp_sample_parsing():
    print("\n--- TEST 1: Parsing WebApp Vulnerabilities Sample (sample_webapp_vulnerabilities.json) ---")
    sample_path = PROJECT_ROOT / "docs" / "samples" / "sample_webapp_vulnerabilities.json"
    assert sample_path.exists(), f"Sample file not found: {sample_path}"

    with open(sample_path, "r", encoding="utf-8") as f:
        raw_json = f.read()

    parser = AcunetixReportParser()
    report = parser.parse(raw_json, scan_id="scan-webapp-001")

    print(f"Engine: {report.engine}")
    print(f"Total findings: {report.summary['total_findings']}")
    print(f"Severity breakdown: {report.summary['severity_breakdown']}")

    assert report.engine == "acunetix"
    assert report.scan_id == "scan-webapp-001"
    assert report.summary["total_findings"] > 0
    breakdown = report.summary["severity_breakdown"]
    assert breakdown["CRITICAL"] > 0, "Expected CRITICAL vulnerabilities"
    assert breakdown["HIGH"] > 0, "Expected HIGH vulnerabilities"
    assert breakdown["MEDIUM"] > 0, "Expected MEDIUM vulnerabilities"

    # Verify first finding details (SQL Injection)
    first_finding = report.findings[0]
    print(f"Finding 0: '{first_finding.title}' | Severity: {first_finding.severity} | CWE: {first_finding.cwe_id} | URL: {first_finding.target_url}")
    assert first_finding.title == "SQL Injection"
    assert first_finding.severity == "CRITICAL"
    assert first_finding.cwe_id == "CWE-89"
    assert "https://demo.testfire.net" in first_finding.target_url
    assert first_finding.attack_parameter == "passw"

    # Verify XSS finding
    xss_findings = [f for f in report.findings if "XSS" in f.title or "Cross-site" in f.title]
    assert len(xss_findings) > 0, "Expected XSS findings in WebApp sample"
    xss = xss_findings[0]
    print(f"Finding XSS: '{xss.title}' | Severity: {xss.severity} | CWE: {xss.cwe_id} | Param: {xss.attack_parameter}")
    assert xss.severity == "HIGH"
    assert xss.cwe_id == "CWE-79"

    print("[PASS] Test 1 passed: WebApp sample successfully transformed to UnifiedReport.")

def test_api_sample_parsing():
    print("\n--- TEST 2: Parsing API Vulnerabilities Sample (sample_api_vulnerabilities.json) ---")
    sample_path = PROJECT_ROOT / "docs" / "samples" / "sample_api_vulnerabilities.json"
    assert sample_path.exists(), f"Sample file not found: {sample_path}"

    with open(sample_path, "r", encoding="utf-8") as f:
        raw_json = f.read()

    parser = AcunetixReportParser()
    report = parser.parse(raw_json, scan_id="scan-api-002")

    print(f"Total findings: {report.summary['total_findings']}")
    print(f"Severity breakdown: {report.summary['severity_breakdown']}")

    assert report.summary["total_findings"] > 0
    # Verify CWE-326 and CWE-16 extraction
    cwes = {f.cwe_id for f in report.findings if f.cwe_id}
    print(f"Extracted CWEs in API scan: {cwes}")
    assert "CWE-326" in cwes, "Expected CWE-326 in API findings"
    assert "CWE-16" in cwes, "Expected CWE-16 in API findings"

    print("[PASS] Test 2 passed: API sample successfully parsed with correct CWE extraction.")

def test_empty_sample_parsing():
    print("\n--- TEST 3: Parsing Empty Sample (sample_vulnerabilities.json) ---")
    sample_path = PROJECT_ROOT / "docs" / "samples" / "sample_vulnerabilities.json"
    assert sample_path.exists(), f"Sample file not found: {sample_path}"

    with open(sample_path, "r", encoding="utf-8") as f:
        raw_json = f.read()

    parser = AcunetixReportParser()
    report = parser.parse(raw_json, scan_id="scan-empty-003")

    assert report.summary["total_findings"] == 0
    assert report.summary["severity_breakdown"] == {
        "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0
    }
    assert len(report.findings) == 0
    print(f"Empty report findings count: {len(report.findings)}")
    print("[PASS] Test 3 passed: Empty vulnerabilities list parsed cleanly.")

def test_critical_detail_sample():
    print("\n--- TEST 4: Parsing Full Critical Finding Detail (sample_vulnerability_detail_critical.json) ---")
    sample_path = PROJECT_ROOT / "docs" / "samples" / "sample_vulnerability_detail_critical.json"
    assert sample_path.exists(), f"Sample file not found: {sample_path}"

    with open(sample_path, "r", encoding="utf-8") as f:
        raw_json = f.read()

    parser = AcunetixReportParser()
    report = parser.parse(raw_json, scan_id="scan-detail-004")

    assert report.summary["total_findings"] == 1
    finding = report.findings[0]
    print(f"Title: {finding.title}")
    print(f"Severity: {finding.severity}")
    print(f"CVSS score: {finding.cvss_score}")
    print(f"CVSS4 vector: {finding.cvss4}")
    print(f"Remediation: {finding.remediation[:60]}...")
    print(f"Request: {finding.http_request[:40]}...")
    print(f"References count: {len(finding.references)}")

    assert finding.title == "SQL Injection"
    assert finding.severity == "CRITICAL"
    assert finding.cwe_id == "CWE-89"
    assert finding.cvss_score == 10.0
    assert "CVSS:4.0" in (finding.cvss4 or "")
    assert "parameterized queries" in (finding.remediation or "").lower()
    assert "POST /doLogin HTTP/1.1" in (finding.http_request or "")
    assert len(finding.references) == 6

    print("[PASS] Test 4 passed: Critical vulnerability detail parsed with all technical fields.")

def test_full_webhook_payload():
    print("\n--- TEST 5: Parsing Full Webhook Payload with Statistics & Timings ---")
    payload = {
        "scan_id": "scan-wb-full-005",
        "status": "COMPLETED",
        "target_url": "http://127.0.0.1:3000",
        "vulnerabilities": [
            {
                "vt_name": "SQL Injection",
                "severity": 4,
                "affects_url": "http://127.0.0.1:3000/rest/products/search",
                "affects_detail": "q",
                "tags": ["CWE-89", "sql_injection"]
            },
            {
                "vt_name": "Content Security Policy (CSP) Not Implemented",
                "severity": 1,
                "affects_url": "http://127.0.0.1:3000/",
                "tags": ["configuration"]
            }
        ],
        "statistics": {
            "locations_crawled": 94,
            "requests": 1420,
            "duration": 182.5
        },
        "timings": {
            "total_duration_seconds": 185.0
        },
        "health_details": {
            "locations": 94,
            "reasons": []
        },
        "coverage_warnings": ["LOW_COVERAGE"]
    }

    parser = AcunetixReportParser()
    report = parser.parse(payload)

    print(f"Report Scan ID: {report.scan_id}")
    print(f"Metrics: {report.scan_metrics}")
    print(f"Coverage warnings: {report.coverage_warnings}")

    assert report.scan_id == "scan-wb-full-005"
    assert report.summary["total_findings"] == 2
    assert report.summary["severity_breakdown"]["CRITICAL"] == 1
    assert report.summary["severity_breakdown"]["LOW"] == 1
    assert report.scan_metrics["locations_crawled"] == 94
    assert report.scan_metrics["requests_sent"] == 1420
    assert report.scan_metrics["duration_seconds"] == 185.0
    assert "LOW_COVERAGE" in report.coverage_warnings

    print("[PASS] Test 5 passed: Full webhook payload parsed with accurate metrics and coverage warnings.")

def test_parser_error_handling():
    print("\n--- TEST 6: Robust Error Handling (Malformed Data -> ParseException) ---")
    parser = AcunetixReportParser()

    # 1. Null payload
    try:
        parser.parse(None)
        assert False, "Should raise ParseException for None"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"
        print(f"[OK] Caught expected ParseException on None: {e}")

    # 2. Empty string
    try:
        parser.parse("   ")
        assert False, "Should raise ParseException for empty string"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"
        print(f"[OK] Caught expected ParseException on empty string: {e}")

    # 3. Malformed JSON
    try:
        parser.parse("{ 'invalid': json without quotes }")
        assert False, "Should raise ParseException for malformed JSON"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"
        print(f"[OK] Caught expected ParseException on malformed JSON: {e}")

    # 4. Invalid data type (integer)
    try:
        parser.parse(12345)
        assert False, "Should raise ParseException for non-dict/list payload"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"
        print(f"[OK] Caught expected ParseException on integer payload: {e}")

    # 5. Field 'vulnerabilities' is not a list
    try:
        parser.parse({"vulnerabilities": "not-a-list"})
        assert False, "Should raise ParseException when vulnerabilities is not a list"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"
        print(f"[OK] Caught expected ParseException when vulnerabilities is string: {e}")

    # 6. Finding missing required title / name
    try:
        parser.parse({"vulnerabilities": [{"severity": 3, "affects_url": "http://test.com"}]})
        assert False, "Should raise ParseException for finding without title"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"
        print(f"[OK] Caught expected ParseException for finding without title: {e}")

    # 7. Finding with invalid severity
    try:
        parser.parse({"vulnerabilities": [{"vt_name": "Test Vuln", "severity": 9999}]})
        assert False, "Should raise ParseException for unknown severity"
    except ParseException as e:
        assert e.error_code == "PARSE_FAILED"
        print(f"[OK] Caught expected ParseException for invalid severity: {e}")

    print("[PASS] Test 6 passed: All invalid/malformed payloads trigger ParseException(error_code='PARSE_FAILED').")

def test_webhook_integration_error_handling():
    print("\n--- TEST 7: WebhookService Integration - Error Handling Sets FAILED/PARSE_FAILED Without Crash ---")
    tmp_db_path = PROJECT_ROOT / "tmp" / "test_t37_webhook.db"
    tmp_db_path.parent.mkdir(parents=True, exist_ok=True)
    if tmp_db_path.exists():
        tmp_db_path.unlink()

    db = Database(str(tmp_db_path))
    db.init_schema()
    repo = ScanRepository(db)
    logger = logging.getLogger("test_t37_logger")

    webhook_service = WebhookService(repo=repo, logger=logger)

    # 1. Seed scan in SCANNING state
    scan_id = "scan-wb-err-007"
    raw_token = "token-xyz-123456789"
    scan_job = ScanJob(
        scan_id=scan_id,
        project_id="proj-finance",
        engine="acunetix",
        created_by="tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token(raw_token)
    )
    repo.create_scan(scan_job)

    # 2. Simulate webhook arrival with corrupted vulnerability data (missing title, invalid severity)
    corrupted_payload = {
        "scan_id": scan_id,
        "status": "COMPLETED",
        "vulnerabilities": [
            {"invalid_field": "no title here", "severity": "completely_unrecognized_sev"}
        ]
    }

    # Process webhook with auto_parse=True
    result = webhook_service.process_webhook(
        headers={"X-Webhook-Token": raw_token},
        body_bytes=json.dumps(corrupted_payload).encode("utf-8"),
        auto_parse=True
    )

    print(f"Webhook response on corrupted report: {result}")
    assert result["status"] == "failed"
    assert result["error_code"] == "PARSE_FAILED"
    assert result["next_state"] == "FAILED"

    # Verify DB state: scan must be FAILED with error_code='PARSE_FAILED'
    updated_scan = repo.get_scan(scan_id)
    print(f"Scan DB Status: '{updated_scan.status}' | Error code: '{updated_scan.error_code}'")
    assert updated_scan.status == "FAILED", f"Expected FAILED, got {updated_scan.status}"
    assert updated_scan.error_code == "PARSE_FAILED", f"Expected error_code PARSE_FAILED, got {updated_scan.error_code}"

    # Verify no crash occurred and BE process is completely alive
    # Now test valid payload on another scan
    scan_id_ok = "scan-wb-ok-008"
    scan_job_ok = ScanJob(
        scan_id=scan_id_ok,
        project_id="proj-finance",
        engine="acunetix",
        created_by="tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token(raw_token)
    )
    repo.create_scan(scan_job_ok)

    valid_payload = {
        "scan_id": scan_id_ok,
        "status": "COMPLETED",
        "vulnerabilities": [
            {"vt_name": "SQL Injection", "severity": 4, "affects_url": "http://127.0.0.1:3000/login"}
        ]
    }
    result_ok = webhook_service.process_webhook(
        headers={"X-Webhook-Token": raw_token},
        body_bytes=json.dumps(valid_payload).encode("utf-8"),
        auto_parse=True
    )
    print(f"Webhook response on valid report: {result_ok}")
    assert result_ok["status"] == "accepted"
    assert result_ok["next_state"] == "COMPLETED"

    updated_scan_ok = repo.get_scan(scan_id_ok)
    assert updated_scan_ok.status == "COMPLETED"
    assert updated_scan_ok.error_code is None

    # Cleanup temp db
    if tmp_db_path.exists():
        tmp_db_path.unlink()

    print("[PASS] Test 7 passed: WebhookService safely transitions scan to FAILED/PARSE_FAILED on parse failure without crashing.")

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.7 (ACUNETIX REPORT PARSER)")
    print("=" * 70)

    test_webapp_sample_parsing()
    test_api_sample_parsing()
    test_empty_sample_parsing()
    test_critical_detail_sample()
    test_full_webhook_payload()
    test_parser_error_handling()
    test_webhook_integration_error_handling()

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.7 PASSED SUCCESSFULLY (100%)!")
    print("=" * 70)

if __name__ == "__main__":
    main()
