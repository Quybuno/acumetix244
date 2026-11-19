"""
Data Models and Repository for Scans, Configurations, and Results (Phase 3 - Task T3.1)
Enforces:
1. Complete scan lifecycle data structures (scans, versioned options, results).
2. Token hashing using SHA-256 (raw tokens are ephemeral and NEVER stored in DB).
3. Zero secret fields in DB models or database records.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from backend.db.database import Database

def get_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def hash_webhook_token(raw_token: str) -> str:
    """
    Compute secure SHA-256 hash of webhook token.
    Only the hash is persisted in the database; raw token is never saved.
    """
    if not raw_token:
        raise ValueError("Cannot hash empty token")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

def verify_webhook_token(raw_token: str, expected_hash: str) -> bool:
    """
    Verify raw token matches expected SHA-256 hash in constant-time.
    """
    if not raw_token or not expected_hash:
        return False
    computed = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return hmac.compare_digest(computed, expected_hash)

# Valid engines and statuses as specified in docs/PLAN.md
VALID_ENGINES = {"acunetix", "fortify"}
VALID_STATUSES = {"SCANNING", "PARSING", "COMPLETED", "FAILED"}
VALID_ERROR_CODES = {
    "JOB_LOST",
    "CALLBACK_LOST",
    "PARSE_FAILED",
    "SCAN_TIMEOUT",
    "SCAN_FAILED",
    "LOGIN_FAILED",
    "MANUAL_INTERVENTION",
    "LOW_COVERAGE",
    "LAUNCH_FAILED",
    "CANCELLED_BY_USER",
    "CONCURRENCY_LIMIT_EXCEEDED"
}

@dataclass
class ScanJob:
    scan_id: str
    project_id: str
    engine: str
    created_by: str
    status: str
    target: str
    token_hash: str
    error_code: Optional[str] = None
    created_at: str = field(default_factory=get_utc_now_iso)
    updated_at: str = field(default_factory=get_utc_now_iso)
    completed_at: Optional[str] = None

    def __post_init__(self):
        if self.engine not in VALID_ENGINES:
            raise ValueError(f"Invalid engine '{self.engine}'. Must be one of {VALID_ENGINES}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'. Must be one of {VALID_STATUSES}")
        if not self.target:
            raise ValueError("Scan target cannot be empty")
        if not self.token_hash:
            raise ValueError("Token hash cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ScanOptionsConfig:
    scan_id: str
    version: str
    config: Dict[str, Any]
    id: Optional[int] = None
    created_at: str = field(default_factory=get_utc_now_iso)

    def __post_init__(self):
        # Strict security check: Ensure config does NOT contain raw secret fields
        self._sanitize_config()

    def _sanitize_config(self):
        """Ensure no password or raw credentials exist in config dict."""
        forbidden_keys = {"admin_password", "password", "webhook_token", "target_credentials"}
        found = [k for k in forbidden_keys if k in self.config]
        if found:
            raise ValueError(f"Security error: Attempted to save secret fields {found} in ScanOptionsConfig DB model!")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "version": self.version,
            "config": self.config,
            "created_at": self.created_at
        }

@dataclass
class ScanResult:
    scan_id: str
    status: str
    vulnerabilities_count: int
    severity_counts: Dict[str, int]
    vulnerabilities: List[Dict[str, Any]]
    statistics: Optional[Dict[str, Any]] = None
    timings: Optional[Dict[str, Any]] = None
    coverage_warnings: Optional[List[str]] = None
    id: Optional[int] = None
    created_at: str = field(default_factory=get_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "status": self.status,
            "vulnerabilities_count": self.vulnerabilities_count,
            "severity_counts": self.severity_counts,
            "vulnerabilities": self.vulnerabilities,
            "statistics": self.statistics,
            "timings": self.timings,
            "coverage_warnings": self.coverage_warnings,
            "created_at": self.created_at
        }

class ScanRepository:
    """Repository handling CRUD operations on Scans, Configs, and Results."""

    def __init__(self, db: Database):
        self.db = db

    def create_scan(self, scan: ScanJob) -> ScanJob:
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO scans (
                    scan_id, project_id, engine, created_by, status,
                    error_code, target, token_hash, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    scan.scan_id, scan.project_id, scan.engine, scan.created_by, scan.status,
                    scan.error_code, scan.target, scan.token_hash, scan.created_at, scan.updated_at, scan.completed_at
                )
            )
            conn.commit()
            return scan
        finally:
            if self.db.db_path != ":memory:":
                conn.close()

    def count_active_scans(self, engine: Optional[str] = None) -> int:
        """Count number of scans currently in active states (SCANNING, PARSING)."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            if engine:
                cursor.execute(
                    "SELECT COUNT(*) FROM scans WHERE status IN ('SCANNING', 'PARSING') AND engine = ?;",
                    (engine,)
                )
            else:
                cursor.execute(
                    "SELECT COUNT(*) FROM scans WHERE status IN ('SCANNING', 'PARSING');"
                )
            return cursor.fetchone()[0]
        finally:
            if self.db.db_path != ":memory:":
                conn.close()

    def get_scan(self, scan_id: str) -> Optional[ScanJob]:
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scans WHERE scan_id = ?;", (scan_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ScanJob(
                scan_id=row["scan_id"],
                project_id=row["project_id"],
                engine=row["engine"],
                created_by=row["created_by"],
                status=row["status"],
                error_code=row["error_code"],
                target=row["target"],
                token_hash=row["token_hash"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                completed_at=row["completed_at"]
            )
        finally:
            if self.db.db_path != ":memory:":
                conn.close()

    def update_scan_status(
        self,
        scan_id: str,
        new_status: str,
        error_code: Optional[str] = None,
        completed_at: Optional[str] = None
    ) -> bool:
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{new_status}'")
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            now = get_utc_now_iso()
            cursor.execute(
                """
                UPDATE scans
                SET status = ?, error_code = ?, updated_at = ?, completed_at = COALESCE(?, completed_at)
                WHERE scan_id = ?;
                """,
                (new_status, error_code, now, completed_at, scan_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            if self.db.db_path != ":memory:":
                conn.close()

    def save_options_config(self, opt_cfg: ScanOptionsConfig) -> ScanOptionsConfig:
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO scan_options_configs (scan_id, version, config_json, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (opt_cfg.scan_id, opt_cfg.version, json.dumps(opt_cfg.config), opt_cfg.created_at)
            )
            opt_cfg.id = cursor.lastrowid
            conn.commit()
            return opt_cfg
        finally:
            if self.db.db_path != ":memory:":
                conn.close()

    def get_options_config(self, scan_id: str) -> Optional[ScanOptionsConfig]:
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_options_configs WHERE scan_id = ?;", (scan_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ScanOptionsConfig(
                id=row["id"],
                scan_id=row["scan_id"],
                version=row["version"],
                config=json.loads(row["config_json"]),
                created_at=row["created_at"]
            )
        finally:
            if self.db.db_path != ":memory:":
                conn.close()

    def save_scan_result(self, result: ScanResult) -> ScanResult:
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO scan_results (
                    scan_id, status, vulnerabilities_count, severity_counts_json,
                    vulnerabilities_json, statistics_json, timings_json, coverage_warnings_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    result.scan_id,
                    result.status,
                    result.vulnerabilities_count,
                    json.dumps(result.severity_counts),
                    json.dumps(result.vulnerabilities),
                    json.dumps(result.statistics) if result.statistics else None,
                    json.dumps(result.timings) if result.timings else None,
                    json.dumps(result.coverage_warnings) if result.coverage_warnings else None,
                    result.created_at
                )
            )
            result.id = cursor.lastrowid
            conn.commit()
            return result
        finally:
            if self.db.db_path != ":memory:":
                conn.close()

    def get_scan_result(self, scan_id: str) -> Optional[ScanResult]:
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_results WHERE scan_id = ?;", (scan_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ScanResult(
                id=row["id"],
                scan_id=row["scan_id"],
                status=row["status"],
                vulnerabilities_count=row["vulnerabilities_count"],
                severity_counts=json.loads(row["severity_counts_json"]),
                vulnerabilities=json.loads(row["vulnerabilities_json"]),
                statistics=json.loads(row["statistics_json"]) if row["statistics_json"] else None,
                timings=json.loads(row["timings_json"]) if row["timings_json"] else None,
                coverage_warnings=json.loads(row["coverage_warnings_json"]) if row["coverage_warnings_json"] else None,
                created_at=row["created_at"]
            )
        finally:
            if self.db.db_path != ":memory:":
                conn.close()
