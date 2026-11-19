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

import uuid
import secrets
from typing import Dict, Any, Optional, Tuple, List
from backend.models.scan import (
    ScanJob,
    ScanOptionsConfig,
    ScanRepository,
    hash_webhook_token
)
from backend.validation.scan_validator import ScanValidator, ValidationError
from backend.services.launcher import LauncherInterface, MockLauncher

class ConcurrencyLimitError(Exception):
    def __init__(self, message: str = "Concurrency limit exceeded", status_code: int = 429):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

# Mapping unified presets to engine-appropriate profile names
PRESET_PROFILE_MAP = {
    "fast_scan": "fast",
    "deep_scan": "Full Scan",
    "crawl_only": "crawl_only",
    "owasp_top10": "OWASP Top 10",
    "standard": "standard",
    "quick": "quick"
}

class ScanService:
    def __init__(
        self,
        repo: ScanRepository,
        launcher: Optional[LauncherInterface] = None,
        validator: Optional[ScanValidator] = None,
        max_concurrent_scans: int = 1,
        webhook_base_url: str = "http://127.0.0.1:8000"
    ):
        self.repo = repo
        self.launcher = launcher or MockLauncher()
        self.validator = validator or ScanValidator()
        self.max_concurrent_scans = max_concurrent_scans
        self.webhook_base_url = webhook_base_url.rstrip("/")

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
        non_secret_config, secret_data = self._segregate_options(
            engine=engine,
            target_str=target_str,
            options=cleaned_options,
            raw_token=raw_webhook_token
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
            # If launch fails, update state to FAILED with JOB_LOST error
            self.repo.update_scan_status(scan_id, new_status="FAILED", error_code="JOB_LOST")
            raise RuntimeError(f"Launcher failed to dispatch scan {scan_id}: {e}")
        finally:
            # Explicitly drop references to raw secrets
            del secret_data
            del raw_webhook_token

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
