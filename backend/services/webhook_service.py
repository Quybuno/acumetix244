"""
Webhook Service for Deep Review Backend (Phase 3 - Task T3.6)
Handles:
1. Webhook payload size enforcement (MAX_WEBHOOK_PAYLOAD_SIZE = 50MB).
2. Token extraction and constant-time SHA-256 hash verification against DB.
3. State checking: Only transition if currently 'SCANNING'.
4. Idempotency: Safe handling of duplicate/retry webhooks (returns 200 ignored, prevents data corruption).
5. State transition to 'PARSING' upon valid receipt.
6. Zero token leakage in logs.
"""

import json
import logging
from typing import Dict, Any, Tuple, Optional
from backend.models.scan import (
    ScanRepository,
    ScanResult,
    verify_webhook_token
)
from backend.parsers.acunetix_parser import (
    AcunetixReportParser,
    UnifiedReport,
    ParseException
)
from backend.services.state_machine import (
    ScanStateMachine,
    InvalidStateTransitionError
)

# Maximum webhook payload limit (50 MB) based on Phase 0 measurements
MAX_WEBHOOK_PAYLOAD_SIZE = 50 * 1024 * 1024  # 52,428,800 bytes

class WebhookError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class WebhookService:
    def __init__(
        self,
        repo: ScanRepository,
        logger: Optional[logging.Logger] = None,
        max_payload_size: int = MAX_WEBHOOK_PAYLOAD_SIZE,
        parser: Optional[AcunetixReportParser] = None,
        state_machine: Optional[ScanStateMachine] = None
    ):
        self.repo = repo
        self.logger = logger or logging.getLogger("deepreview_webhook")
        self.max_payload_size = max_payload_size
        self.parser = parser or AcunetixReportParser()
        self.state_machine = state_machine or ScanStateMachine(repo=self.repo, logger=self.logger)

    def process_webhook(
        self,
        headers: Dict[str, str],
        body_bytes: bytes,
        auto_parse: bool = False
    ) -> Dict[str, Any]:
        """
        Process incoming webhook from scan driver.
        Returns: Dict response with status and message.
        Raises: WebhookError with appropriate HTTP status code.
        """
        # 1. Enforce payload size limit
        content_len = len(body_bytes)
        if content_len > self.max_payload_size:
            raise WebhookError(
                f"Payload size {content_len} bytes exceeds maximum limit of {self.max_payload_size} bytes",
                status_code=413
            )

        # 2. Extract token from headers (Support X-Webhook-Token and Authorization: Bearer)
        # Note: headers dict may have case-insensitive keys
        normalized_headers = {k.lower(): v for k, v in headers.items()}
        raw_token = normalized_headers.get("x-webhook-token")
        if not raw_token:
            auth_header = normalized_headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                raw_token = auth_header[7:].strip()

        if not raw_token:
            raise WebhookError("Missing required authentication token header", status_code=401)

        # 3. Parse JSON body
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception as e:
            raise WebhookError(f"Malformed JSON payload: {e}", status_code=400)

        scan_id = payload.get("scan_id")
        if not scan_id:
            raise WebhookError("Missing 'scan_id' in webhook payload", status_code=400)

        # 4. Fetch scan from DB
        scan = self.repo.get_scan(scan_id)
        if not scan:
            raise WebhookError(f"Scan '{scan_id}' not found", status_code=404)

        # 5. Verify Token Hash (Constant-time comparison)
        # DO NOT LOG THE RAW TOKEN!
        is_token_valid = verify_webhook_token(raw_token, scan.token_hash)
        if not is_token_valid:
            self.logger.warning(
                f"Unauthorized webhook attempt for scan_id={scan_id}: token hash mismatch."
            )
            raise WebhookError("Invalid webhook authentication token", status_code=403)

        self.logger.info(
            f"Webhook token verified successfully for scan_id={scan_id}."
        )

        # 6. Idempotency Check & State Machine Enforcement
        # Only accept and transition if scan is currently in 'SCANNING' state
        if scan.status != "SCANNING":
            self.logger.info(
                f"Duplicate/late webhook callback for scan_id={scan_id} (current state: '{scan.status}'). "
                f"Ignored safely to prevent data corruption."
            )
            return {
                "status": "ignored",
                "message": f"Scan is in state '{scan.status}'. Duplicate callback ignored.",
                "scan_id": scan_id
            }

        # 7. Transition to 'PARSING' state using state machine
        self.state_machine.transition(scan_id, new_status="PARSING")

        # 8. Persist raw result record in DB
        vulns = payload.get("vulnerabilities", [])
        severity_counts = payload.get("severity_counts", {})
        statistics = payload.get("statistics")
        timings = payload.get("timings")
        coverage_warnings = payload.get("coverage_warnings", [])
        driver_status = payload.get("status", "COMPLETED")

        scan_result = ScanResult(
            scan_id=scan_id,
            status=driver_status,
            vulnerabilities_count=len(vulns),
            severity_counts=severity_counts,
            vulnerabilities=vulns,
            statistics=statistics,
            timings=timings,
            coverage_warnings=coverage_warnings
        )
        self.repo.save_scan_result(scan_result)
        self.logger.info(
            f"Saved raw scan result for scan_id={scan_id}: status={driver_status}, "
            f"vulnerabilities={len(vulns)}."
        )

        if auto_parse:
            report = self.parse_scan_report(scan_id=scan_id, raw_payload=payload)
            if report is None:
                return {
                    "status": "failed",
                    "error_code": "PARSE_FAILED",
                    "message": "Report parsing failed",
                    "scan_id": scan_id,
                    "next_state": "FAILED"
                }
            # Transition to terminal status via state machine
            final_status = "COMPLETED" if driver_status == "COMPLETED" else "FAILED"
            fail_code = payload.get("error_code") or "SCAN_FAILED" if final_status == "FAILED" else None
            self.state_machine.transition(
                scan_id=scan_id,
                new_status=final_status,
                error_code=fail_code
            )
            return {
                "status": "accepted",
                "message": f"Webhook processed and report parsed successfully (terminal state: {final_status})",
                "scan_id": scan_id,
                "next_state": final_status,
                "findings_count": report.summary.get("total_findings", 0)
            }

        return {
            "status": "accepted",
            "message": "Webhook processed successfully",
            "scan_id": scan_id,
            "next_state": "PARSING"
        }

    def parse_scan_report(
        self,
        scan_id: str,
        raw_payload: Any
    ) -> Optional[UnifiedReport]:
        """
        Parses raw scan payload into UnifiedReport using AcunetixReportParser.
        If parsing fails (ParseException or unexpected error):
        - Transitions scan to FAILED with error_code='PARSE_FAILED'.
        - Logs error safely without leaking secrets.
        - Returns None, preventing any unhandled backend crashes.
        """
        try:
            report = self.parser.parse(raw_payload, scan_id=scan_id)
            self.logger.info(
                f"Successfully parsed scan report for {scan_id} into UnifiedReport: "
                f"{report.summary['total_findings']} findings "
                f"(CRITICAL={report.summary['severity_breakdown']['CRITICAL']}, "
                f"HIGH={report.summary['severity_breakdown']['HIGH']})."
            )
            return report
        except ParseException as pe:
            self.logger.error(
                f"Report parsing failed for scan {scan_id}: {pe}. "
                f"Transitioning scan state to FAILED with error_code='PARSE_FAILED'."
            )
            try:
                self.state_machine.transition(
                    scan_id=scan_id,
                    new_status="FAILED",
                    error_code="PARSE_FAILED"
                )
            except Exception as e_trans:
                self.logger.error(f"State transition error: {e_trans}")
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error during report parsing for scan {scan_id}: {e}. "
                f"Transitioning scan state to FAILED with error_code='PARSE_FAILED'."
            )
            try:
                self.state_machine.transition(
                    scan_id=scan_id,
                    new_status="FAILED",
                    error_code="PARSE_FAILED"
                )
            except Exception as e_trans:
                self.logger.error(f"State transition error: {e_trans}")
            return None
