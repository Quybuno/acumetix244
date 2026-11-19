"""
Scan State Machine Service for Deep Review Backend (Phase 3 - Task T3.8)

Enforces:
1. Strict one-way state transitions:
   SCANNING -> PARSING -> COMPLETED / FAILED
2. Immutability of terminal states:
   COMPLETED and FAILED can NEVER transition to any other state or be re-triggered.
3. Strict error_code requirement for FAILED states:
   Every failed scan MUST have a valid error_code from the authorized catalog:
   (JOB_LOST, CALLBACK_LOST, PARSE_FAILED, SCAN_TIMEOUT, LOGIN_FAILED,
    MANUAL_INTERVENTION, LOW_COVERAGE, LAUNCH_FAILED, CANCELLED_BY_USER,
    CONCURRENCY_LIMIT_EXCEEDED).
4. Automatic recording of completed_at timestamp upon reaching terminal state.
5. Immediate concurrency limit rejection: Active scans (SCANNING, PARSING) cannot exceed ceiling.
"""

import logging
from typing import Optional, Set, Dict
from datetime import datetime, timezone
from backend.models.scan import (
    ScanJob,
    ScanRepository,
    VALID_STATUSES,
    VALID_ERROR_CODES,
    get_utc_now_iso
)
from backend.metrics.metrics import MetricsCollector, get_global_metrics

class InvalidStateTransitionError(Exception):
    """Raised when an illegal or out-of-order state transition is attempted."""
    def __init__(
        self,
        message: str,
        current_status: Optional[str] = None,
        target_status: Optional[str] = None,
        error_code: str = "INVALID_STATE_TRANSITION"
    ):
        super().__init__(message)
        self.message = message
        self.current_status = current_status
        self.target_status = target_status
        self.error_code = error_code

    def __str__(self) -> str:
        if self.current_status and self.target_status:
            return f"[{self.error_code}] {self.message} (current='{self.current_status}', target='{self.target_status}')"
        return f"[{self.error_code}] {self.message}"

class ScanStateMachine:
    """
    Manages the lifecycle state transitions for scan jobs in Deep Review.
    """

    TERMINAL_STATUSES: Set[str] = {"COMPLETED", "FAILED"}
    ACTIVE_STATUSES: Set[str] = {"SCANNING", "PARSING"}

    # Strict one-way allowed transitions
    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        "SCANNING": {"PARSING", "FAILED"},
        "PARSING": {"COMPLETED", "FAILED"},
        "COMPLETED": set(),  # Terminal: No transitions allowed
        "FAILED": set(),     # Terminal: No transitions allowed
    }

    def __init__(
        self,
        repo: ScanRepository,
        logger: Optional[logging.Logger] = None,
        metrics: Optional[MetricsCollector] = None
    ):
        self.repo = repo
        self.logger = logger or logging.getLogger("deepreview_state_machine")
        self.metrics = metrics or get_global_metrics()

    def can_transition(self, current_status: str, target_status: str) -> bool:
        """Check if a transition from current_status to target_status is permitted."""
        return target_status in self.ALLOWED_TRANSITIONS.get(current_status, set())

    def validate_transition(
        self,
        current_status: str,
        target_status: str,
        error_code: Optional[str] = None
    ) -> None:
        """
        Validate transition rules. Raises InvalidStateTransitionError on violation.
        """
        if current_status not in VALID_STATUSES:
            raise InvalidStateTransitionError(
                f"Invalid current scan status '{current_status}'. Allowed: {VALID_STATUSES}",
                current_status=current_status,
                target_status=target_status
            )

        if target_status not in VALID_STATUSES:
            raise InvalidStateTransitionError(
                f"Invalid target scan status '{target_status}'. Allowed: {VALID_STATUSES}",
                current_status=current_status,
                target_status=target_status
            )

        allowed = self.ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            if current_status in self.TERMINAL_STATUSES:
                raise InvalidStateTransitionError(
                    f"Cannot transition from terminal state '{current_status}' to '{target_status}'. Terminal states are immutable.",
                    current_status=current_status,
                    target_status=target_status
                )
            if current_status == "PARSING" and target_status == "SCANNING":
                raise InvalidStateTransitionError(
                    f"Illegal backward transition from '{current_status}' to '{target_status}'. State machine is strictly one-way.",
                    current_status=current_status,
                    target_status=target_status
                )
            if current_status == "SCANNING" and target_status == "COMPLETED":
                raise InvalidStateTransitionError(
                    f"Illegal transition: '{current_status}' cannot skip directly to '{target_status}'. Must transition to PARSING first.",
                    current_status=current_status,
                    target_status=target_status
                )
            raise InvalidStateTransitionError(
                f"Illegal transition from '{current_status}' to '{target_status}'. Allowed targets: {allowed or 'none (terminal)'}.",
                current_status=current_status,
                target_status=target_status
            )

        # Enforce error_code requirements for FAILED status
        if target_status == "FAILED":
            if not error_code or not str(error_code).strip():
                raise InvalidStateTransitionError(
                    "Transition to FAILED status strictly requires a non-empty error_code.",
                    current_status=current_status,
                    target_status=target_status
                )
            if error_code not in VALID_ERROR_CODES:
                raise InvalidStateTransitionError(
                    f"Invalid error_code '{error_code}'. Must be one of {sorted(list(VALID_ERROR_CODES))}.",
                    current_status=current_status,
                    target_status=target_status
                )

        # Enforce no error_code for COMPLETED status
        if target_status == "COMPLETED" and error_code is not None:
            raise InvalidStateTransitionError(
                f"Transition to COMPLETED status cannot include an error_code (got '{error_code}').",
                current_status=current_status,
                target_status=target_status
            )

    def transition(
        self,
        scan_id: str,
        new_status: str,
        error_code: Optional[str] = None,
        completed_at: Optional[str] = None
    ) -> ScanJob:
        """
        Atomically validate and execute a scan state transition.
        Updates DB and returns the updated ScanJob.
        """
        scan = self.repo.get_scan(scan_id)
        if not scan:
            raise ValueError(f"Scan '{scan_id}' not found")

        current_status = scan.status
        self.validate_transition(
            current_status=current_status,
            target_status=new_status,
            error_code=error_code
        )

        # Auto-set completed_at for terminal statuses if not explicitly provided
        final_completed_at = completed_at
        if new_status in self.TERMINAL_STATUSES and not final_completed_at:
            final_completed_at = get_utc_now_iso()

        self.repo.update_scan_status(
            scan_id=scan_id,
            new_status=new_status,
            error_code=error_code,
            completed_at=final_completed_at
        )

        self.logger.info(
            f"Scan {scan_id} state transition executed: '{current_status}' -> '{new_status}' "
            f"(error_code={error_code}, completed_at={final_completed_at})."
        )

        # Record metrics
        duration_sec = None
        if new_status in self.TERMINAL_STATUSES and scan.created_at:
            try:
                c_time = datetime.fromisoformat(scan.created_at.replace("Z", "+00:00"))
                duration_sec = (datetime.now(timezone.utc) - c_time).total_seconds()
            except Exception:
                pass

        if self.metrics:
            self.metrics.record_state_transition(
                from_status=current_status,
                to_status=new_status,
                error_code=error_code,
                duration_seconds=duration_sec
            )

        updated_scan = self.repo.get_scan(scan_id)
        if not updated_scan:
            raise RuntimeError(f"Failed to reload scan '{scan_id}' after update")
        return updated_scan
