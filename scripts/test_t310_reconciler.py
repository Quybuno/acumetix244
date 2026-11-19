"""
Verification Script for Task T3.10: Scan Reconciler Service
Validates:
1. JOB_LOST detection:
   - Job disappears (NOT_FOUND) from infrastructure -> scan closed as FAILED/JOB_LOST.
   - Job crashes (status FAILED / driver exit code != 0) -> scan closed as FAILED/JOB_LOST.
2. CALLBACK_LOST detection:
   - Job completed but webhook never arrived beyond grace period -> scan closed as FAILED/CALLBACK_LOST.
   - Job completed within grace period -> NOT closed (grace period respected).
3. SCAN_TIMEOUT detection:
   - Scan running beyond maximum job duration ceiling -> killed and closed as FAILED/SCAN_TIMEOUT.
4. Orphaned infrastructure cleanup:
   - Residual containers/secrets for finished scans are wiped clean.
5. Background thread lifecycle:
   - start() and stop() function cleanly without thread leaks or blocking.
"""

import sys
import os
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.database import Database
from backend.models.scan import (
    ScanJob,
    ScanRepository,
    hash_webhook_token,
    get_utc_now_iso
)
from backend.services.launcher import LauncherInterface
from backend.services.state_machine import ScanStateMachine
from backend.services.reconciler import ScanReconciler

class ConfigurableMockLauncher(LauncherInterface):
    """Configurable mock launcher to simulate various infrastructure failure states."""
    def __init__(self):
        self.jobs: dict = {}
        self.killed = []
        self.cleaned = []

    def set_job_state(self, scan_id: str, status: str, exit_code: int = None, error: str = None):
        self.jobs[scan_id] = {
            "scan_id": scan_id,
            "status": status,
            "driver_exit_code": exit_code,
            "error": error
        }

    def launch(self, scan_id, secrets, inputs=None, options=None):
        self.jobs[scan_id] = {"scan_id": scan_id, "status": "RUNNING", "driver_exit_code": None}
        return {"status": "LAUNCHED", "scan_id": scan_id}

    def status(self, scan_id: str):
        if scan_id not in self.jobs:
            return {"status": "NOT_FOUND", "scan_id": scan_id}
        return self.jobs[scan_id]

    def kill(self, scan_id: str):
        self.killed.append(scan_id)
        if scan_id in self.jobs:
            self.jobs[scan_id]["status"] = "KILLED"
        return True

    def cleanup(self, scan_id: str):
        self.cleaned.append(scan_id)
        self.jobs.pop(scan_id, None)
        return True

def create_scan_with_age(repo: ScanRepository, scan_id: str, status: str, age_seconds: int) -> ScanJob:
    """Helper to seed scan with simulated age in the past."""
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    scan = ScanJob(
        scan_id=scan_id,
        project_id="proj-rec",
        engine="acunetix",
        created_by="tester",
        status=status,
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token(f"token-{scan_id}"),
        created_at=past_time,
        updated_at=past_time
    )
    return repo.create_scan(scan)

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.10 (SCAN RECONCILER SERVICE)")
    print("=" * 70)

    tmp_db = PROJECT_ROOT / "tmp" / "test_t310_reconciler.db"
    tmp_db.parent.mkdir(parents=True, exist_ok=True)
    if tmp_db.exists():
        tmp_db.unlink()

    db = Database(str(tmp_db))
    db.init_schema()
    repo = ScanRepository(db)
    launcher = ConfigurableMockLauncher()
    state_machine = ScanStateMachine(repo)
    logger = logging.getLogger("test_t310_logger")

    reconciler = ScanReconciler(
        repo=repo,
        launcher=launcher,
        state_machine=state_machine,
        logger=logger,
        callback_grace_period_seconds=60,
        max_scan_duration_seconds=1800  # 30 mins
    )

    # ==========================================================
    # TEST 1: JOB_LOST Detection (Job Missing from Infrastructure)
    # ==========================================================
    print("\n--- TEST 1: JOB_LOST Detection (Job Disappeared from Infrastructure) ---")
    scan1_id = "scan-lost-missing"
    create_scan_with_age(repo, scan1_id, "SCANNING", age_seconds=10)
    # Do NOT set job in launcher -> launcher returns NOT_FOUND

    res1 = reconciler.reconcile_once()
    print(f"Reconciler pass 1 summary: {res1}")

    assert res1["job_lost"] == 1
    scan1_db = repo.get_scan(scan1_id)
    print(f"Scan 1 DB status: '{scan1_db.status}', error_code: '{scan1_db.error_code}'")
    assert scan1_db.status == "FAILED"
    assert scan1_db.error_code == "JOB_LOST"
    assert scan1_id in launcher.cleaned
    print("[PASS] Test 1 passed: Missing job successfully closed as FAILED/JOB_LOST and cleaned.")

    # ==========================================================
    # TEST 2: JOB_LOST Detection (Job Crashed / Exited with Error)
    # ==========================================================
    print("\n--- TEST 2: JOB_LOST Detection (Driver Container Crash / OOM) ---")
    scan2_id = "scan-lost-crashed"
    create_scan_with_age(repo, scan2_id, "SCANNING", age_seconds=15)
    # Simulate container crashed with OOM exit code 137
    launcher.set_job_state(scan2_id, status="FAILED", exit_code=137, error="Container killed by OOM")

    res2 = reconciler.reconcile_once()
    print(f"Reconciler pass 2 summary: {res2}")

    assert res2["job_lost"] == 1
    scan2_db = repo.get_scan(scan2_id)
    print(f"Scan 2 DB status: '{scan2_db.status}', error_code: '{scan2_db.error_code}'")
    assert scan2_db.status == "FAILED"
    assert scan2_db.error_code == "JOB_LOST"
    assert scan2_id in launcher.cleaned
    print("[PASS] Test 2 passed: Crashed job successfully closed as FAILED/JOB_LOST.")

    # ==========================================================
    # TEST 3: CALLBACK_LOST Detection (Job Completed Beyond Grace Period)
    # ==========================================================
    print("\n--- TEST 3: CALLBACK_LOST Detection (Job Finished but No Webhook) ---")
    scan3_id = "scan-cb-lost"
    # Seed scan with age 90s (> grace period 60s)
    create_scan_with_age(repo, scan3_id, "SCANNING", age_seconds=90)
    # Driver completed (exit code 0 or 50) but webhook was lost
    launcher.set_job_state(scan3_id, status="COMPLETED", exit_code=0)

    res3 = reconciler.reconcile_once()
    print(f"Reconciler pass 3 summary: {res3}")

    assert res3["callback_lost"] == 1
    scan3_db = repo.get_scan(scan3_id)
    print(f"Scan 3 DB status: '{scan3_db.status}', error_code: '{scan3_db.error_code}'")
    assert scan3_db.status == "FAILED"
    assert scan3_db.error_code == "CALLBACK_LOST"
    assert scan3_id in launcher.cleaned
    print("[PASS] Test 3 passed: Scan with lost webhook closed as FAILED/CALLBACK_LOST.")

    # ==========================================================
    # TEST 4: Respect Grace Period (Do NOT Close Job Within Grace Period)
    # ==========================================================
    print("\n--- TEST 4: Respect Webhook Grace Period ---")
    scan4_id = "scan-cb-waiting"
    # Seed scan with age 15s (< grace period 60s)
    create_scan_with_age(repo, scan4_id, "SCANNING", age_seconds=15)
    launcher.set_job_state(scan4_id, status="COMPLETED", exit_code=0)

    res4 = reconciler.reconcile_once()
    print(f"Reconciler pass 4 summary: {res4}")

    assert res4["callback_lost"] == 0
    scan4_db = repo.get_scan(scan4_id)
    print(f"Scan 4 DB status: '{scan4_db.status}' (reconciler patiently waited for webhook)")
    assert scan4_db.status == "SCANNING", "Scan must remain in SCANNING during grace period"
    print("[PASS] Test 4 passed: Scan preserved in SCANNING while within webhook grace period.")

    # Cleanup scan 4 for subsequent tests
    state_machine.transition(scan4_id, "FAILED", error_code="PARSE_FAILED")

    # ==========================================================
    # TEST 5: SCAN_TIMEOUT Detection (Job Exceeds Max Allowed Duration)
    # ==========================================================
    print("\n--- TEST 5: SCAN_TIMEOUT Detection (Exceeded 30 mins Ceiling) ---")
    scan5_id = "scan-timed-out"
    # Seed scan running for 2000s (> 1800s max ceiling)
    create_scan_with_age(repo, scan5_id, "SCANNING", age_seconds=2000)
    launcher.set_job_state(scan5_id, status="RUNNING", exit_code=None)

    res5 = reconciler.reconcile_once()
    print(f"Reconciler pass 5 summary: {res5}")

    assert res5["scan_timeout"] == 1
    scan5_db = repo.get_scan(scan5_id)
    print(f"Scan 5 DB status: '{scan5_db.status}', error_code: '{scan5_db.error_code}'")
    assert scan5_db.status == "FAILED"
    assert scan5_db.error_code == "SCAN_TIMEOUT"
    assert scan5_id in launcher.killed
    assert scan5_id in launcher.cleaned
    print("[PASS] Test 5 passed: Scan exceeding ceiling killed and closed with SCAN_TIMEOUT.")

    # ==========================================================
    # TEST 6: Residual Orphan Container Cleanup for Finished Scans
    # ==========================================================
    print("\n--- TEST 6: Residual Infrastructure Cleanup for Finished Scans ---")
    scan6_id = "scan-orphaned-containers"
    # Seed completed scan in DB, but container leftover in launcher
    create_scan_with_age(repo, scan6_id, "COMPLETED", age_seconds=120)
    launcher.set_job_state(scan6_id, status="COMPLETED", exit_code=0)

    assert scan6_id in launcher.jobs
    res6 = reconciler.reconcile_once()
    print(f"Reconciler pass 6 summary: {res6}")

    assert res6["cleaned"] >= 1
    assert scan6_id not in launcher.jobs
    assert scan6_id in launcher.cleaned
    print("[PASS] Test 6 passed: Leftover containers for finished scan successfully cleaned.")

    # ==========================================================
    # TEST 7: Background Thread Lifecycle (start & stop)
    # ==========================================================
    print("\n--- TEST 7: Background Reconciler Thread Lifecycle ---")
    reconciler.start(interval_seconds=1)
    assert reconciler._running is True
    assert reconciler._thread.is_alive()
    print("Reconciler background thread is active.")

    time.sleep(2.2)  # Allow background thread to execute at least 2 cycles

    reconciler.stop()
    assert reconciler._running is False
    assert not reconciler._thread.is_alive()
    print("Reconciler background thread stopped gracefully.")
    print("[PASS] Test 7 passed: Background thread cleanly runs and terminates.")

    # Cleanup temp db
    if tmp_db.exists():
        tmp_db.unlink()

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.10 PASSED SUCCESSFULLY (100%)!")
    print("=" * 70)

if __name__ == "__main__":
    main()
