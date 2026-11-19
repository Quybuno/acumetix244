"""
Scan Reconciler Service for Deep Review Backend (Phase 3 - Task T3.10)

Runs periodically (every 60 seconds) to reconcile state between Backend DB and Launcher/Docker:
1. Detects lost jobs (Job disappears or crashes without sending webhook) -> Closes scan with JOB_LOST.
2. Detects missing webhooks (Job completed but webhook never arrived beyond grace period) -> Closes scan with CALLBACK_LOST.
3. Enforces overall scan duration ceiling -> Kills and closes scan with SCAN_TIMEOUT.
4. Cleans up orphaned or leftover containers and secrets for finished scans.
5. Emits structured log warnings and metrics for operational monitoring.
"""

import time
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from backend.models.scan import ScanJob, ScanRepository, get_utc_now_iso
from backend.services.launcher import LauncherInterface
from backend.services.state_machine import ScanStateMachine, InvalidStateTransitionError
from backend.metrics.metrics import MetricsCollector, get_global_metrics

def parse_iso_timestamp(iso_str: Optional[str]) -> Optional[datetime]:
    if not iso_str:
        return None
    try:
        # Handle 'Z' suffix for UTC
        clean_str = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except Exception:
        return None

class ScanReconciler:
    """
    Periodic reconciler ensuring state alignment between DB and Job execution infrastructure.
    """

    def __init__(
        self,
        repo: ScanRepository,
        launcher: LauncherInterface,
        state_machine: Optional[ScanStateMachine] = None,
        logger: Optional[logging.Logger] = None,
        callback_grace_period_seconds: int = 60,
        max_scan_duration_seconds: int = 1860,  # 31 minutes
        metrics: Optional[MetricsCollector] = None
    ):
        self.repo = repo
        self.launcher = launcher
        self.state_machine = state_machine or ScanStateMachine(repo=self.repo)
        self.logger = logger or logging.getLogger("deepreview_reconciler")
        self.callback_grace_period_seconds = callback_grace_period_seconds
        self.max_scan_duration_seconds = max_scan_duration_seconds
        self.metrics = metrics or get_global_metrics()

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def reconcile_once(self) -> Dict[str, Any]:
        """
        Execute a single reconciliation pass over active and finished scans.
        Returns a summary report of actions taken.
        """
        now = datetime.now(timezone.utc)
        job_lost_count = 0
        callback_lost_count = 0
        timeout_count = 0
        cleaned_count = 0

        # 1. Query all scans currently in SCANNING state
        active_scans = self.repo.list_scans(status="SCANNING", limit=100)

        for scan in active_scans:
            scan_id = scan.scan_id
            created_at = parse_iso_timestamp(scan.created_at)
            elapsed_seconds = (now - created_at).total_seconds() if created_at else 0

            # Query launcher for real infrastructure status
            try:
                job_info = self.launcher.status(scan_id)
            except Exception as e:
                self.logger.warning(f"Failed to query launcher status for scan {scan_id}: {e}")
                continue

            launcher_status = job_info.get("status", "NOT_FOUND")
            driver_exit_code = job_info.get("driver_exit_code")

            # -------------------------------------------------------------
            # CASE 1: JOB_LOST
            # Job disappeared or failed abruptly without calling webhook
            # -------------------------------------------------------------
            is_job_lost = False
            lost_reason = ""

            if launcher_status == "NOT_FOUND":
                # Job not found in infrastructure while scan is still marked SCANNING
                is_job_lost = True
                lost_reason = "Job container/pod not found in infrastructure"
            elif launcher_status in ("FAILED", "DEGRADED"):
                # Job container failed or critical sidecar missing
                is_job_lost = True
                lost_reason = f"Job status is '{launcher_status}' (error={job_info.get('error')})"
            elif driver_exit_code is not None and driver_exit_code != 0 and driver_exit_code != 50:
                # Driver exited with a failure code (e.g. crash, OOM)
                is_job_lost = True
                lost_reason = f"Driver container exited with error code {driver_exit_code}"

            if is_job_lost:
                self.logger.warning(
                    f"RECONCILER: Scan {scan_id} detected as JOB_LOST. Reason: {lost_reason}. "
                    f"Transitioning to FAILED and cleaning infrastructure."
                )
                try:
                    self.launcher.cleanup(scan_id)
                except Exception as e_clean:
                    self.logger.warning(f"Error during cleanup of lost job {scan_id}: {e_clean}")

                try:
                    self.state_machine.transition(
                        scan_id=scan_id,
                        new_status="FAILED",
                        error_code="JOB_LOST"
                    )
                    job_lost_count += 1
                    if self.metrics:
                        self.metrics.record_reconciler_closure("JOB_LOST")
                except Exception as e_trans:
                    self.logger.error(f"Failed to transition scan {scan_id} to JOB_LOST: {e_trans}")
                continue

            # -------------------------------------------------------------
            # CASE 2: CALLBACK_LOST
            # Job completed normally (or with exit code 50 callback failure),
            # but webhook callback never reached Backend within grace period.
            # -------------------------------------------------------------
            is_job_done = (launcher_status == "COMPLETED" or driver_exit_code in (0, 50))
            if is_job_done:
                # If elapsed time exceeds grace period, close as CALLBACK_LOST
                if elapsed_seconds >= self.callback_grace_period_seconds:
                    self.logger.warning(
                        f"RECONCILER: Scan {scan_id} detected as CALLBACK_LOST. Job finished "
                        f"(exit_code={driver_exit_code}) but webhook did not arrive within "
                        f"{self.callback_grace_period_seconds}s (elapsed: {elapsed_seconds:.1f}s)."
                    )
                    try:
                        self.launcher.cleanup(scan_id)
                    except Exception as e_clean:
                        self.logger.warning(f"Error during cleanup of scan {scan_id}: {e_clean}")

                    try:
                        self.state_machine.transition(
                            scan_id=scan_id,
                            new_status="FAILED",
                            error_code="CALLBACK_LOST"
                        )
                        callback_lost_count += 1
                        if self.metrics:
                            self.metrics.record_reconciler_closure("CALLBACK_LOST")
                    except Exception as e_trans:
                        self.logger.error(f"Failed to transition scan {scan_id} to CALLBACK_LOST: {e_trans}")
                    continue
                else:
                    # Within grace period: let driver retry delivery
                    self.logger.info(
                        f"RECONCILER: Scan {scan_id} job finished; waiting for webhook "
                        f"(elapsed {elapsed_seconds:.1f}s / grace period {self.callback_grace_period_seconds}s)."
                    )

            # -------------------------------------------------------------
            # CASE 3: SCAN_TIMEOUT
            # Job has been running longer than maximum permitted duration
            # -------------------------------------------------------------
            if elapsed_seconds >= self.max_scan_duration_seconds:
                self.logger.warning(
                    f"RECONCILER: Scan {scan_id} exceeded maximum job duration ceiling "
                    f"({elapsed_seconds:.1f}s >= {self.max_scan_duration_seconds}s). "
                    f"Killing pod and closing with SCAN_TIMEOUT."
                )
                try:
                    self.launcher.kill(scan_id)
                except Exception as e_kill:
                    self.logger.warning(f"Error killing timed out scan {scan_id}: {e_kill}")

                try:
                    self.launcher.cleanup(scan_id)
                except Exception as e_clean:
                    self.logger.warning(f"Error cleaning timed out scan {scan_id}: {e_clean}")

                try:
                    self.state_machine.transition(
                        scan_id=scan_id,
                        new_status="FAILED",
                        error_code="SCAN_TIMEOUT"
                    )
                    timeout_count += 1
                    if self.metrics:
                        self.metrics.record_reconciler_closure("SCAN_TIMEOUT")
                except Exception as e_trans:
                    self.logger.error(f"Failed to transition scan {scan_id} to SCAN_TIMEOUT: {e_trans}")
                continue

        # -----------------------------------------------------------------
        # STEP 2: Dọn dẹp tài nguyên rác (Orphaned / Stale resources)
        # Check finished scans (COMPLETED or FAILED) and ensure containers/secrets are wiped
        # -----------------------------------------------------------------
        recent_finished = self.repo.list_scans(status="COMPLETED", limit=20)
        recent_finished.extend(self.repo.list_scans(status="FAILED", limit=20))

        for f_scan in recent_finished:
            try:
                st = self.launcher.status(f_scan.scan_id)
                # If infrastructure still has records or containers for this finished scan
                if st.get("status") not in ("NOT_FOUND", None):
                    self.launcher.cleanup(f_scan.scan_id)
                    cleaned_count += 1
            except Exception:
                pass

        report = {
            "scans_checked": len(active_scans),
            "job_lost": job_lost_count,
            "callback_lost": callback_lost_count,
            "scan_timeout": timeout_count,
            "cleaned": cleaned_count
        }

        self.logger.debug(f"RECONCILER: Completed pass. Result: {report}")
        return report

    def start(self, interval_seconds: int = 60) -> None:
        """Start the background reconciler thread."""
        if self._running:
            return

        self._stop_event.clear()
        self._running = True

        def _worker():
            self.logger.info(f"Reconciler background thread started (interval={interval_seconds}s).")
            while not self._stop_event.is_set():
                try:
                    self.reconcile_once()
                except Exception as e:
                    self.logger.error(f"Unhandled exception in reconciler cycle: {e}")

                # Sleep in short increments to allow rapid shutdown
                for _ in range(interval_seconds * 10):
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.1)

            self.logger.info("Reconciler background thread stopped.")

        self._thread = threading.Thread(target=_worker, daemon=True, name="ScanReconcilerThread")
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background reconciler thread."""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._running = False
