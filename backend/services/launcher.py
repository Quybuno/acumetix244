"""
Launcher Service Interface for Deep Review Backend (Phase 3 - Task T3.3 & T3.5)
Defines the abstract interface for launching and managing scan jobs:
- launch(scan_id, secrets, inputs, options)
- status(scan_id)
- kill(scan_id)
- cleanup(scan_id)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class LauncherInterface(ABC):
    @abstractmethod
    def launch(
        self,
        scan_id: str,
        secrets: Dict[str, Any],
        inputs: Dict[str, Any],
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Launch a scan job with secrets, inputs, and options."""
        pass

    @abstractmethod
    def status(self, scan_id: str) -> Dict[str, Any]:
        """Get the current operational status of the job."""
        pass

    @abstractmethod
    def kill(self, scan_id: str) -> bool:
        """Kill the running job."""
        pass

    @abstractmethod
    def cleanup(self, scan_id: str) -> bool:
        """Clean up all containers and temporary files for the scan."""
        pass

class MockLauncher(LauncherInterface):
    """
    In-memory mock launcher for backend unit and integration testing (Task T3.14).
    Simulates launching without requiring actual Docker or OpenShift infrastructure.
    """
    def __init__(self):
        self.launched_jobs: Dict[str, Dict[str, Any]] = {}
        self.killed_jobs: list = []
        self.cleaned_jobs: list = []

    def launch(
        self,
        scan_id: str,
        secrets: Dict[str, Any],
        inputs: Dict[str, Any],
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        self.launched_jobs[scan_id] = {
            "scan_id": scan_id,
            "has_secrets": bool(secrets),
            "inputs_count": len(inputs),
            "options": options,
            "status": "RUNNING"
        }
        return {"status": "LAUNCHED", "scan_id": scan_id}

    def status(self, scan_id: str) -> Dict[str, Any]:
        job = self.launched_jobs.get(scan_id)
        if not job:
            return {"status": "NOT_FOUND", "scan_id": scan_id}
        return {"status": job["status"], "scan_id": scan_id}

    def kill(self, scan_id: str) -> bool:
        if scan_id in self.launched_jobs:
            self.launched_jobs[scan_id]["status"] = "KILLED"
            self.killed_jobs.append(scan_id)
            return True
        return False

    def cleanup(self, scan_id: str) -> bool:
        self.cleaned_jobs.append(scan_id)
        if scan_id in self.launched_jobs:
            del self.launched_jobs[scan_id]
        return True
