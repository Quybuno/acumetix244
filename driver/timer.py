import time
from typing import Dict, List, Optional, Any

class StepTimer:
    """
    Tracks execution time of each driver pipeline step (Task T2.11).
    Ensures total driver time is measured and strictly lower than Job timeout (T1.6).
    """
    def __init__(self, scan_id: str, logger=None):
        self.scan_id = scan_id
        self.logger = logger
        self.start_total = time.monotonic()
        self.steps: List[Dict[str, Any]] = []
        self._current_step: Optional[str] = None
        self._current_start: Optional[float] = None

    def start_step(self, name: str):
        if self._current_step:
            self.end_step("SUCCESS")
        self._current_step = name
        self._current_start = time.monotonic()

    def end_step(self, status: str = "SUCCESS", details: Optional[str] = None):
        if not self._current_step or self._current_start is None:
            return
        duration = time.monotonic() - self._current_start
        self.steps.append({
            "name": self._current_step,
            "duration": round(duration, 3),
            "status": status,
            "details": details
        })
        self._current_step = None
        self._current_start = None

    def get_total_duration(self) -> float:
        return round(time.monotonic() - self.start_total, 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_duration_seconds": self.get_total_duration(),
            "steps": self.steps
        }

    def print_summary(self, exit_code: int = 0, job_timeout_seconds: Optional[int] = None) -> str:
        if self._current_step:
            self.end_step("FAILED" if exit_code != 0 else "SUCCESS")

        total = self.get_total_duration()
        lines = [
            "=" * 64,
            f"DRIVER EXECUTION TIMING SUMMARY (scan_id={self.scan_id})",
            "-" * 64,
            f"{'Step Name':<38} {'Duration':<12} {'Status':<10}",
            "-" * 64,
        ]
        for s in self.steps:
            lines.append(f"{s['name']:<38} {s['duration']:>7.2f}s    {s['status']:<10}")
        lines.append("-" * 64)
        lines.append(f"{'Total Driver Duration:':<38} {total:>7.2f}s")
        if job_timeout_seconds:
            margin = job_timeout_seconds - total
            lines.append(f"{'Job Timeout Limit (T1.6):':<38} {job_timeout_seconds:>7.2f}s")
            lines.append(f"{'Margin to Job Kill:':<38} {margin:>7.2f}s")
        lines.append(f"{'Exit Code:':<38} {exit_code}")
        lines.append("=" * 64)
        summary_str = "\n".join(lines)
        if self.logger:
            for l in lines:
                self.logger.info(l)
        else:
            print(summary_str)
        return summary_str
