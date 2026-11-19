"""
Scan Service for Deep Review Backend (Phase 3 - Task T3.3)
Orchestrates:
1. Input validation and URL allowlist verification.
2. Concurrency limit enforcement (MAX_CONCURRENT_SCANS, default=1).
3. Secure webhook token generation and SHA-256 hashing.
4. Segregation of options: Non-secret config stored in DB, secrets routed to launcher then dropped.
5. Launching jobs via LauncherInterface.
6. DB persistence in 'SCANNING' state.
"""

import os
import uuid
import secrets
import threading
from typing import Dict, Any, Optional, Tuple, List
from backend.models.scan import (
    ScanJob,
    ScanOptionsConfig,
    ScanRepository,
    hash_webhook_token
)
from backend.validation.scan_validator import ScanValidator, ValidationError
from backend.services.launcher import LauncherInterface, MockLauncher
from backend.services.options_segregator import OptionsSegregator, PRESET_PROFILE_MAP
from backend.services.state_machine import ScanStateMachine, InvalidStateTransitionError
from backend.parsers.acunetix_parser import AcunetixReportParser, UnifiedReport

class ConcurrencyLimitError(Exception):
    def __init__(self, message: str = "Concurrency limit exceeded", status_code: int = 429):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class ScanNotFoundError(Exception):
    def __init__(self, message: str = "Scan not found", status_code: int = 404):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class ScanCancellationError(Exception):
    def __init__(self, message: str = "Cannot cancel scan", status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class ScanService:
    def __init__(
        self,
        repo: ScanRepository,
        launcher: Optional[LauncherInterface] = None,
        validator: Optional[ScanValidator] = None,
        state_machine: Optional[ScanStateMachine] = None,
        parser: Optional[AcunetixReportParser] = None,
        max_concurrent_scans: Optional[int] = None,
        webhook_base_url: str = "http://127.0.0.1:8000"
    ):
        self.repo = repo
        self.launcher = launcher or MockLauncher()
        self.validator = validator or ScanValidator()
        self.state_machine = state_machine or ScanStateMachine(repo=self.repo)
        self.parser = parser or AcunetixReportParser()

        # Configurable concurrency limit (R-09 / T0.9 default: 1)
        if max_concurrent_scans is not None:
            self.max_concurrent_scans = max(1, int(max_concurrent_scans))
        else:
            env_val = os.getenv("MAX_CONCURRENT_SCANS", "1")
            try:
                self.max_concurrent_scans = max(1, int(env_val))
            except (ValueError, TypeError):
                self.max_concurrent_scans = 1

        self.webhook_base_url = webhook_base_url.rstrip("/")
        self._creation_lock = threading.Lock()

    def create_scan(
        self,
        engine: str,
        project_id: str,
        created_by: str,
        scan_options: Dict[str, Any],
        uploaded_files: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create and trigger a new scan job.
        Strictly enforces validation, concurrency limits, secret segregation, and token hashing.
        """
        # Step 1: Validate payload, target URL, and files
        target_str, cleaned_options, validated_files = self.validator.validate_create_request(
            engine=engine,
            project_id=project_id,
            created_by=created_by,
            scan_options=scan_options,
            uploaded_files=uploaded_files
        )

        # Thread-safe atomic concurrency check and scan reservation (Zero Queueing)
        with self._creation_lock:
            # Step 2: Enforce concurrency ceiling (T0.9 / T3.11)
            active_scans = self.repo.count_active_scans()
            if active_scans >= self.max_concurrent_scans:
                raise ConcurrencyLimitError(
                    f"Concurrency limit ({self.max_concurrent_scans}) reached. "
                    f"Currently {active_scans} active scan(s) running. New scan request rejected."
                )

            # Step 3: Generate unique Scan ID and Ephemeral Webhook Token
            scan_id = f"scan-{uuid.uuid4().hex[:12]}"
            raw_webhook_token = secrets.token_urlsafe(32)
            token_hash = hash_webhook_token(raw_webhook_token)

            # Step 4: Segregate ScanOptions into Non-Secret (DB) and Secret (Launcher only)
            webhook_callback_url = f"{self.webhook_base_url}/api/v1/webhook"
            non_secret_config, secret_data = OptionsSegregator.segregate(
                engine=engine,
                target_str=target_str,
                options=cleaned_options,
                raw_webhook_token=raw_webhook_token,
                webhook_url=webhook_callback_url
            )

            # Step 5: Persist initial ScanJob and Non-Secret Options in DB
            scan_job = ScanJob(
                scan_id=scan_id,
                project_id=project_id,
                engine=engine,
                created_by=created_by,
                status="SCANNING",
                target=target_str,
                token_hash=token_hash
            )
            self.repo.create_scan(scan_job)

            options_record = ScanOptionsConfig(
                scan_id=scan_id,
                version="1.0",
                config=non_secret_config
            )
            self.repo.save_options_config(options_record)

        # Step 6: Dispatch to Launcher (Secrets passed to launcher and discarded from BE memory)
        try:
            self.launcher.launch(
                scan_id=scan_id,
                secrets=secret_data,
                inputs=validated_files or {},
                options=non_secret_config
            )
        except Exception as e:
            # If launch fails, transition state to FAILED with LAUNCH_FAILED via state machine
            try:
                self.state_machine.transition(scan_id=scan_id, new_status="FAILED", error_code="LAUNCH_FAILED")
            except Exception:
                self.repo.update_scan_status(scan_id, new_status="FAILED", error_code="LAUNCH_FAILED")
            raise RuntimeError(f"Launcher failed to dispatch scan {scan_id}: {e}")
        finally:
            # Explicitly overwrite and purge secrets from memory (Task T3.4)
            OptionsSegregator.purge_secrets(secret_data)
            del secret_data

        # Step 7: Return public response (ZERO secrets or raw tokens in response)
        return {
            "status": "success",
            "scan_id": scan_id,
            "project_id": project_id,
            "engine": engine,
            "target": target_str,
            "state": "SCANNING",
            "created_at": scan_job.created_at
        }

    def _segregate_options(
        self,
        engine: str,
        target_str: str,
        options: Dict[str, Any],
        raw_token: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Split ScanOptions into:
        1. non_secret_config: to be stored in scan_options_configs DB table (Task T3.4).
        2. secret_data: to be passed only to pod secrets/credentials.json and dropped.
        """
        preset = options.get("preset", "fast_scan")
        profile = PRESET_PROFILE_MAP.get(preset, "fast")

        # Non-secret options dictionary for DB
        non_secret_config = {
            "preset": preset,
            "profile": profile,
            "scan_speed": options.get("scan_speed", "fast"),
            "limit_crawler_scope": True,
            "crawl_limit": options.get("crawl_limit", 100),
            "excluded_paths": options.get("excluded_paths", []),
            "scan_timeout_minutes": options.get("scan_timeout_minutes", 30),
            "description": options.get("description", "")
        }

        # Secret options dictionary for Launcher/Driver only
        secret_data = {
            "target_url": target_str,
            "webhook_token": raw_token,
            "webhook_url": f"{self.webhook_base_url}/api/v1/webhook"
        }

        # Handle target login credentials if provided
        username = options.get("target_username")
        password = options.get("target_password")
        if username or password:
            secret_data["target_credentials"] = {
                "username": username or "",
                "password": password or ""
            }

        # Handle custom headers (which may contain secret auth tokens)
        custom_headers = options.get("custom_headers", [])
        if custom_headers:
            secret_data["custom_headers"] = custom_headers

        return non_secret_config, secret_data

    def list_scans(
        self,
        project_id: Optional[str] = None,
        engine: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """List scans with filtering and pagination. Strips token_hash and secrets."""
        total = self.repo.count_scans(project_id=project_id, engine=engine, status=status)
        scans = self.repo.list_scans(
            project_id=project_id,
            engine=engine,
            status=status,
            limit=limit,
            offset=offset
        )
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "scans": [s.to_public_dict() for s in scans]
        }

    def get_scan_detail(self, scan_id: str) -> Dict[str, Any]:
        """Get complete scan details including UnifiedReport results, timings, and coverage warnings."""
        scan = self.repo.get_scan(scan_id)
        if not scan:
            raise ScanNotFoundError(f"Scan '{scan_id}' not found")

        options_cfg = self.repo.get_options_config(scan_id)
        result_record = self.repo.get_scan_result(scan_id)

        detail = scan.to_public_dict()
        detail["options"] = options_cfg.config if options_cfg else None

        if result_record:
            try:
                report = self.parser.parse(result_record.to_dict(), scan_id=scan_id)
                detail["report"] = report.to_dict()
                detail["summary"] = report.summary
                detail["findings_count"] = report.summary["total_findings"]
                detail["scan_metrics"] = report.scan_metrics
                detail["coverage_warnings"] = report.coverage_warnings
            except Exception:
                detail["summary"] = {
                    "total_findings": result_record.vulnerabilities_count,
                    "severity_breakdown": result_record.severity_counts
                }
                detail["findings_count"] = result_record.vulnerabilities_count
                detail["coverage_warnings"] = result_record.coverage_warnings or []
                detail["scan_metrics"] = result_record.statistics or {}
                detail["report"] = None
            detail["timings"] = result_record.timings
        else:
            detail["report"] = None
            detail["summary"] = None
            detail["coverage_warnings"] = []
            detail["scan_metrics"] = None
            detail["timings"] = None

        return detail

    def cancel_scan(self, scan_id: str) -> Dict[str, Any]:
        """Cancel an in-progress scan, kill launcher resources, and mark state as CANCELLED_BY_USER."""
        scan = self.repo.get_scan(scan_id)
        if not scan:
            raise ScanNotFoundError(f"Scan '{scan_id}' not found")

        if scan.status in ("COMPLETED", "FAILED"):
            raise ScanCancellationError(
                f"Cannot cancel scan '{scan_id}' in terminal state '{scan.status}'"
            )

        # 1. Instruct launcher to kill and cleanup pod/containers
        try:
            self.launcher.kill(scan_id)
        except Exception:
            pass

        try:
            self.launcher.cleanup(scan_id)
        except Exception:
            pass

        # 2. Transition scan state to FAILED with CANCELLED_BY_USER
        updated_scan = self.state_machine.transition(
            scan_id=scan_id,
            new_status="FAILED",
            error_code="CANCELLED_BY_USER"
        )

        return {
            "status": "success",
            "message": "Scan cancelled successfully",
            "scan_id": scan_id,
            "state": updated_scan.status,
            "error_code": updated_scan.error_code,
            "completed_at": updated_scan.completed_at
        }
