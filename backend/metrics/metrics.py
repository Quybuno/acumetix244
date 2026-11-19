"""
Metrics and Observability Collector for Deep Review Backend (Phase 3 - Task T3.13)

Tracks:
1. Scan counts by lifecycle status (SCANNING, PARSING, COMPLETED, FAILED).
2. Scan counts by error code (JOB_LOST, CALLBACK_LOST, PARSE_FAILED, etc.).
3. Scan counts by engine (acunetix, fortify).
4. Current active scans vs. concurrency limit.
5. Scan duration metrics (total, average, min, max seconds).
6. Reconciler closures count.
7. Automated alert generation when JOB_LOST or CALLBACK_LOST exceeds thresholds.
"""

import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from backend.models.scan import VALID_STATUSES, VALID_ERROR_CODES

@dataclass
class Alert:
    """Represents an operational alert regarding infrastructure or network health."""
    level: str  # 'WARNING' or 'CRITICAL'
    alert_type: str
    metric: str
    current_value: int
    threshold: int
    message: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class MetricsCollector:
    """
    Thread-safe in-memory metrics aggregator and alert generator.
    """

    def __init__(self, concurrency_limit: int = 1):
        self._lock = threading.Lock()
        self.concurrency_limit = concurrency_limit
        self.reset()

    def reset(self):
        """Reset all metrics counters to initial values."""
        with self._lock:
            self.scans_total: int = 0
            self.scans_by_status: Dict[str, int] = {s: 0 for s in VALID_STATUSES}
            self.scans_by_error_code: Dict[str, int] = {e: 0 for e in VALID_ERROR_CODES}
            self.scans_by_engine: Dict[str, int] = {"acunetix": 0, "fortify": 0}
            self.reconciler_closures: Dict[str, int] = {
                "JOB_LOST": 0,
                "CALLBACK_LOST": 0,
                "SCAN_TIMEOUT": 0
            }
            self.durations_seconds: List[float] = []

    def record_scan_created(self, engine: str, project_id: Optional[str] = None):
        """Record the creation of a new scan job."""
        with self._lock:
            self.scans_total += 1
            self.scans_by_status["SCANNING"] += 1
            if engine in self.scans_by_engine:
                self.scans_by_engine[engine] += 1
            else:
                self.scans_by_engine[engine] = 1

    def record_state_transition(
        self,
        from_status: str,
        to_status: str,
        error_code: Optional[str] = None,
        duration_seconds: Optional[float] = None
    ):
        """Record a scan transitioning between lifecycle states."""
        with self._lock:
            if from_status in self.scans_by_status and self.scans_by_status[from_status] > 0:
                self.scans_by_status[from_status] -= 1
            if to_status in self.scans_by_status:
                self.scans_by_status[to_status] += 1

            if to_status == "FAILED" and error_code:
                if error_code in self.scans_by_error_code:
                    self.scans_by_error_code[error_code] += 1
                else:
                    self.scans_by_error_code[error_code] = 1

            if duration_seconds is not None and duration_seconds >= 0:
                self.durations_seconds.append(float(duration_seconds))

    def record_reconciler_closure(self, error_code: str):
        """Record a scan being forcefully closed by the Reconciler."""
        with self._lock:
            if error_code in self.reconciler_closures:
                self.reconciler_closures[error_code] += 1

    def check_alerts(
        self,
        job_lost_threshold: int = 2,
        callback_lost_threshold: int = 2
    ) -> List[Alert]:
        """
        Check whether JOB_LOST or CALLBACK_LOST counts exceed operational alert thresholds.
        Indicates potential cluster, container runtime, or networking problems.
        """
        alerts: List[Alert] = []
        with self._lock:
            job_lost_val = self.scans_by_error_code.get("JOB_LOST", 0)
            if job_lost_val >= job_lost_threshold:
                alerts.append(Alert(
                    level="CRITICAL",
                    alert_type="HIGH_JOB_LOST_RATE",
                    metric="JOB_LOST",
                    current_value=job_lost_val,
                    threshold=job_lost_threshold,
                    message=(
                        f"ALERT: Infrastructure failure rate high! {job_lost_val} scan(s) failed with JOB_LOST. "
                        f"Pod or sidecar containers may be crashing or killed by OOM."
                    )
                ))

            cb_lost_val = self.scans_by_error_code.get("CALLBACK_LOST", 0)
            if cb_lost_val >= callback_lost_threshold:
                alerts.append(Alert(
                    level="WARNING",
                    alert_type="HIGH_CALLBACK_LOST_RATE",
                    metric="CALLBACK_LOST",
                    current_value=cb_lost_val,
                    threshold=callback_lost_threshold,
                    message=(
                        f"ALERT: Network or webhook callback failure! {cb_lost_val} scan(s) timed out with CALLBACK_LOST. "
                        f"Check network policy or backend webhook receiver accessibility."
                    )
                ))

        return alerts

    def get_summary(
        self,
        job_lost_threshold: int = 2,
        callback_lost_threshold: int = 2
    ) -> Dict[str, Any]:
        """Generate a complete structured metrics report."""
        with self._lock:
            active_scans = self.scans_by_status.get("SCANNING", 0) + self.scans_by_status.get("PARSING", 0)
            total_durations = len(self.durations_seconds)
            avg_duration = round(sum(self.durations_seconds) / total_durations, 2) if total_durations > 0 else 0.0
            min_duration = min(self.durations_seconds) if total_durations > 0 else 0.0
            max_duration = max(self.durations_seconds) if total_durations > 0 else 0.0

            status_copy = dict(self.scans_by_status)
            error_copy = {k: v for k, v in self.scans_by_error_code.items() if v > 0}
            engine_copy = dict(self.scans_by_engine)
            reconciler_copy = dict(self.reconciler_closures)

        alerts = [a.to_dict() for a in self.check_alerts(job_lost_threshold, callback_lost_threshold)]

        return {
            "scans_total": self.scans_total,
            "active_scans": active_scans,
            "concurrency_limit": self.concurrency_limit,
            "concurrency_utilization_percent": round((active_scans / self.concurrency_limit) * 100, 1) if self.concurrency_limit > 0 else 0.0,
            "scans_by_status": status_copy,
            "scans_by_error_code": error_copy,
            "scans_by_engine": engine_copy,
            "reconciler_closures": reconciler_copy,
            "performance": {
                "completed_scans_measured": total_durations,
                "avg_duration_seconds": avg_duration,
                "min_duration_seconds": min_duration,
                "max_duration_seconds": max_duration
            },
            "alerts": alerts,
            "has_active_alerts": len(alerts) > 0,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

# Global singleton metrics instance
_GLOBAL_METRICS = MetricsCollector()

def get_global_metrics() -> MetricsCollector:
    return _GLOBAL_METRICS
