"""
Launcher Service Interface and Implementations for Deep Review Backend (Phase 3 - Task T3.5)
Defines:
1. LauncherInterface: Abstract contract for scan execution (launch, status, kill, cleanup).
2. DockerLauncher: Production-like local implementation coordinating Docker Mock-Pod (via pod_manager).
3. MockLauncher: Fast in-memory implementation for unit tests.
4. OpenShiftLauncher: Stub implementation ready for OpenShift Job / Secret deployment.
5. LauncherFactory: Factory resolving the active launcher from configuration / environment.
"""

import os
import sys
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import scripts.pod_manager as pod_mgr

class LauncherInterface(ABC):
    """
    Unified Launcher Interface for Deep Review.
    Ensures Backend scan orchestration remains 100% unchanged whether running on
    Docker (local test pod) or OpenShift (production Kubernetes Job).
    """

    @abstractmethod
    def launch(
        self,
        scan_id: str,
        secrets: Dict[str, Any],
        inputs: Dict[str, Any],
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Launch a new scan execution environment.
        Prepares isolated secret and input mounts, starts sidecars, and runs driver.
        """
        pass

    @abstractmethod
    def status(self, scan_id: str) -> Dict[str, Any]:
        """
        Query status of the running scan environment.
        Returns standardized dictionary: {scan_id, status: RUNNING|COMPLETED|FAILED|NOT_FOUND, driver_exit_code, ...}
        """
        pass

    @abstractmethod
    def kill(self, scan_id: str) -> bool:
        """
        Forcibly terminate running scan containers/pods.
        """
        pass

    @abstractmethod
    def cleanup(self, scan_id: str) -> bool:
        """
        Clean up containers, secrets, and temporary directories associated with scan_id.
        """
        pass


class DockerLauncher(LauncherInterface):
    """
    Docker Mock-Pod implementation coordinating Docker containers via pod_manager (Task T1.10).
    Uses container labels scan-id=<scan_id>, managed-by=deepreview-docker-launcher.
    Mounts secrets and inputs strictly read-only (:ro).
    """

    def __init__(
        self,
        driver_image: str = "deepreview-acunetix-driver:local",
        timeout_ready: int = 60,
        use_dummy_driver: bool = False
    ):
        self.driver_image = driver_image
        self.timeout_ready = timeout_ready
        self.use_dummy_driver = use_dummy_driver

    def launch(
        self,
        scan_id: str,
        secrets: Dict[str, Any],
        inputs: Dict[str, Any],
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Prepare inputs dictionary for pod_manager
        # (pod_manager expects file_name -> content bytes/str)
        inputs_files = {}
        if inputs:
            for field_name, f_info in inputs.items():
                if isinstance(f_info, dict) and "filename" in f_info:
                    fname = f_info["filename"]
                    inputs_files[fname] = f_info.get("content", b"")
                elif isinstance(f_info, str):
                    inputs_files[field_name] = f_info
                elif isinstance(f_info, bytes):
                    inputs_files[field_name] = f_info

        # Also write options.json into inputs directory so driver can read it
        inputs_files["options.json"] = json.dumps(options, indent=2)

        # Build driver command
        driver_cmd = None
        if self.use_dummy_driver:
            driver_cmd = ["sh", "-c", "echo 'Dummy driver executed successfully'; sleep 1; exit 0"]
        else:
            # Command arguments for deepreview-acunetix-driver:local
            # Note: Acunetix sidecar is in the same container network (localhost:3443)
            # Webhook is reachable via host.docker.internal
            webhook_url = secrets.get("webhook_url", "http://host.docker.internal:8000/api/v1/webhook")
            driver_cmd = [
                "--scan-id", scan_id,
                "--acunetix-url", "https://localhost:3443",
                "--secrets-file", "/secrets/credentials.json",
                "--options-file", "/inputs/options.json",
                "--inputs-dir", "/inputs",
                "--webhook-url", webhook_url,
                "--ready-timeout", "20",
                "--scan-timeout", str(options.get("scan_timeout_minutes", 30) * 60),
                "--poll-interval", "2.0",
                "--clean-target",
                "--job-timeout", "1860"
            ]

        # Override pod_manager DRIVER_IMAGE if configured
        original_driver_image = pod_mgr.DUMMY_DRIVER_IMAGE
        try:
            if not self.use_dummy_driver:
                pod_mgr.DUMMY_DRIVER_IMAGE = self.driver_image

            res = pod_mgr.launch_ordered_pod(
                scan_id=scan_id,
                driver_cmd=driver_cmd,
                timeout_ready=self.timeout_ready,
                secrets=secrets,
                inputs=inputs_files
            )
            return {
                "status": "LAUNCHED",
                "scan_id": scan_id,
                "launcher": "docker",
                "containers": [res.get("net"), res.get("acunetix"), res.get("driver")]
            }
        finally:
            pod_mgr.DUMMY_DRIVER_IMAGE = original_driver_image

    def status(self, scan_id: str) -> Dict[str, Any]:
        info = pod_mgr.get_pod_status(scan_id)
        return {
            "scan_id": scan_id,
            "launcher": "docker",
            "status": info.get("status", "NOT_FOUND"),
            "driver_exit_code": info.get("driver_exit_code"),
            "error": info.get("error"),
            "missing_containers": info.get("missing_containers", [])
        }

    def kill(self, scan_id: str) -> bool:
        pod_mgr.kill_pod(scan_id)
        return True

    def cleanup(self, scan_id: str) -> bool:
        pod_mgr.cleanup_pod(scan_id)
        return True


class MockLauncher(LauncherInterface):
    """
    In-memory mock launcher for fast testing and development without Docker daemon.
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
            "status": "RUNNING",
            "exit_code": None
        }
        return {"status": "LAUNCHED", "scan_id": scan_id, "launcher": "mock"}

    def status(self, scan_id: str) -> Dict[str, Any]:
        job = self.launched_jobs.get(scan_id)
        if not job:
            return {"status": "NOT_FOUND", "scan_id": scan_id, "launcher": "mock"}
        return {
            "scan_id": scan_id,
            "status": job["status"],
            "driver_exit_code": job.get("exit_code"),
            "launcher": "mock"
        }

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


class OpenShiftLauncher(LauncherInterface):
    """
    Production OpenShift / Kubernetes Job implementation stub.
    When Deep Review deploys to OpenShift, this adapter creates Kubernetes Secrets,
    Job manifests with native sidecars, and NetworkPolicies without modifying
    the Backend business workflows.
    """

    def __init__(self, namespace: str = "deepreview-scanners"):
        self.namespace = namespace

    def launch(
        self,
        scan_id: str,
        secrets: Dict[str, Any],
        inputs: Dict[str, Any],
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Stub for OpenShift Job & Secret creation via K8s API
        return {
            "status": "LAUNCHED",
            "scan_id": scan_id,
            "launcher": "openshift",
            "namespace": self.namespace
        }

    def status(self, scan_id: str) -> Dict[str, Any]:
        return {
            "scan_id": scan_id,
            "status": "RUNNING",
            "launcher": "openshift",
            "namespace": self.namespace
        }

    def kill(self, scan_id: str) -> bool:
        return True

    def cleanup(self, scan_id: str) -> bool:
        return True


class LauncherFactory:
    """
    Factory resolving Launcher implementation based on configuration or environment.
    """

    @staticmethod
    def get_launcher(launcher_type: Optional[str] = None, **kwargs) -> LauncherInterface:
        selected_type = (launcher_type or os.environ.get("LAUNCHER_TYPE", "docker")).strip().lower()

        if selected_type == "docker":
            return DockerLauncher(**kwargs)
        elif selected_type == "mock":
            return MockLauncher()
        elif selected_type in ["openshift", "k8s", "kubernetes"]:
            return OpenShiftLauncher(**kwargs)
        else:
            raise ValueError(
                f"Unknown launcher type '{selected_type}'. Supported: ['docker', 'mock', 'openshift']"
            )
