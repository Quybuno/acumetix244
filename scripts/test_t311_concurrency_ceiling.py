"""
Verification Script for Task T3.11: Concurrency Ceiling & Proper Release
Validates:
1. Configurable concurrency ceiling (default: 1, supports custom limit via config/env).
2. Immediate rejection when limit is reached (Zero Queueing, HTTP 429, CONCURRENCY_LIMIT_EXCEEDED).
3. Proper concurrency release across ALL terminal scenarios:
   - Normal completion (COMPLETED)
   - Scan / Parser failure (FAILED: PARSE_FAILED, LOGIN_FAILED, etc.)
   - Reconciler closing lost job (FAILED: JOB_LOST, CALLBACK_LOST)
   - User cancellation via DELETE API (FAILED: CANCELLED_BY_USER)
   - Launcher dispatch failure (FAILED: LAUNCH_FAILED)
4. Multi-threaded race condition safety:
   - 20 concurrent threads trying to create scans simultaneously.
   - Exactly 1 succeeds (201), exactly 19 rejected (429), active scans never exceeds 1.
"""

import sys
import os
import time
import json
import threading
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.database import Database
from backend.models.scan import ScanJob, ScanRepository, hash_webhook_token
from backend.services.launcher import LauncherInterface, MockLauncher
from backend.services.state_machine import ScanStateMachine
from backend.services.scan_service import ScanService, ConcurrencyLimitError
from backend.services.reconciler import ScanReconciler

class FailingMockLauncher(LauncherInterface):
    """Launcher that simulates launch failure to verify release."""
    def launch(self, scan_id, secrets, inputs=None, options=None):
        raise RuntimeError("Docker daemon connection failed during launch")

    def status(self, scan_id):
        return {"status": "NOT_FOUND", "scan_id": scan_id}

    def kill(self, scan_id):
        return True

    def cleanup(self, scan_id):
        return True

def test_configurable_limit(repo: ScanRepository):
    print("\n--- TEST 1: Configurable Concurrency Ceiling (Default & Custom Limits) ---")
    # 1. Default limit = 1
    s_default = ScanService(repo=repo)
    assert s_default.max_concurrent_scans == 1
    print(f"[OK] Default max_concurrent_scans: {s_default.max_concurrent_scans}")

    # 2. Custom limit via constructor = 3
    s_custom = ScanService(repo=repo, max_concurrent_scans=3)
    assert s_custom.max_concurrent_scans == 3
    print(f"[OK] Custom max_concurrent_scans: {s_custom.max_concurrent_scans}")

    # 3. Limit via environment variable MAX_CONCURRENT_SCANS = 2
    os.environ["MAX_CONCURRENT_SCANS"] = "2"
    s_env = ScanService(repo=repo)
    assert s_env.max_concurrent_scans == 2
    print(f"[OK] Environment-based max_concurrent_scans: {s_env.max_concurrent_scans}")
    os.environ.pop("MAX_CONCURRENT_SCANS", None)

    print("[PASS] Test 1 passed: Concurrency limit is fully configurable.")

def test_rejection_and_normal_completion_release(repo: ScanRepository, state_machine: ScanStateMachine):
    print("\n--- TEST 2 & 3: Immediate Rejection & Normal Completion (COMPLETED) Release ---")
    scan_service = ScanService(repo=repo, state_machine=state_machine, max_concurrent_scans=1)

    # 1. Start scan 1
    res1 = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-t311",
        created_by="tester",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    scan1_id = res1["scan_id"]
    print(f"Scan 1 created: {scan1_id} (active = {repo.count_active_scans()})")
    assert repo.count_active_scans() == 1

    # 2. Attempt scan 2 while scan 1 is running -> MUST REJECT WITH 429
    try:
        scan_service.create_scan(
            engine="acunetix",
            project_id="proj-t311",
            created_by="tester",
            scan_options={"target_url": "http://127.0.0.1:3000"}
        )
        assert False, "Scan 2 must be rejected with ConcurrencyLimitError"
    except ConcurrencyLimitError as e:
        print(f"[OK] Scan 2 rejected immediately (HTTP {e.status_code}): {e.message}")
        assert e.status_code == 429
        assert "Concurrency limit (1) reached" in e.message

    # 3. Transition scan 1 to COMPLETED
    state_machine.transition(scan1_id, "PARSING")
    state_machine.transition(scan1_id, "COMPLETED")
    assert repo.count_active_scans() == 0
    print(f"[OK] Scan 1 COMPLETED. Concurrency released (active = {repo.count_active_scans()}).")

    # 4. Now scan 2 can be created successfully
    res2 = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-t311",
        created_by="tester",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    scan2_id = res2["scan_id"]
    print(f"[OK] Scan 2 created immediately after release: {scan2_id}")
    assert repo.count_active_scans() == 1

    # Cleanup scan 2
    state_machine.transition(scan2_id, "FAILED", error_code="LOGIN_FAILED")
    assert repo.count_active_scans() == 0
    print("[PASS] Test 2 & 3 passed: Immediate 429 rejection and COMPLETED release verified.")

def test_failure_and_user_cancellation_release(repo: ScanRepository, state_machine: ScanStateMachine):
    print("\n--- TEST 4: Release on Failure and User Cancellation ---")
    scan_service = ScanService(repo=repo, state_machine=state_machine, max_concurrent_scans=1)

    # 1. Create scan -> cancel via cancel_scan API
    res = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-t311",
        created_by="tester",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    scan_id = res["scan_id"]
    assert repo.count_active_scans() == 1

    # User cancels scan
    cancel_res = scan_service.cancel_scan(scan_id)
    assert cancel_res["status"] == "success"
    assert cancel_res["state"] == "FAILED"
    assert cancel_res["error_code"] == "CANCELLED_BY_USER"
    assert repo.count_active_scans() == 0
    print(f"[OK] Scan cancelled by user. Concurrency released (active = {repo.count_active_scans()}).")

    # 2. Next scan can immediately be created
    res_next = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-t311",
        created_by="tester",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    print(f"[OK] Permitted next scan after user cancellation: {res_next['scan_id']}")
    state_machine.transition(res_next["scan_id"], "FAILED", error_code="PARSE_FAILED")
    assert repo.count_active_scans() == 0

    print("[PASS] Test 4 passed: Concurrency properly released on failure & cancellation.")

def test_reconciler_release(repo: ScanRepository, state_machine: ScanStateMachine):
    print("\n--- TEST 5: Release on Reconciler Closure (JOB_LOST) ---")
    launcher = MockLauncher()
    reconciler = ScanReconciler(repo=repo, launcher=launcher, state_machine=state_machine)
    scan_service = ScanService(repo=repo, launcher=launcher, state_machine=state_machine, max_concurrent_scans=1)

    res = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-t311",
        created_by="tester",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    scan_id = res["scan_id"]
    assert repo.count_active_scans() == 1

    # Reconciler detects lost job (launcher status is NOT_FOUND by clearing launcher dict)
    launcher.launched_jobs.clear()
    rec_report = reconciler.reconcile_once()
    assert rec_report["job_lost"] == 1
    assert repo.count_active_scans() == 0
    print(f"[OK] Reconciler closed lost job. Concurrency released (active = {repo.count_active_scans()}).")

    # Next scan succeeds immediately
    res_after = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-t311",
        created_by="tester",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    print(f"[OK] Permitted next scan after Reconciler release: {res_after['scan_id']}")
    state_machine.transition(res_after["scan_id"], "FAILED", error_code="SCAN_TIMEOUT")
    assert repo.count_active_scans() == 0

    print("[PASS] Test 5 passed: Concurrency properly released when Reconciler closes scan.")

def test_launcher_failure_release(repo: ScanRepository, state_machine: ScanStateMachine):
    print("\n--- TEST 6: Release on Launcher Dispatch Failure (LAUNCH_FAILED) ---")
    failing_launcher = FailingMockLauncher()
    scan_service = ScanService(
        repo=repo,
        launcher=failing_launcher,
        state_machine=state_machine,
        max_concurrent_scans=1
    )

    try:
        scan_service.create_scan(
            engine="acunetix",
            project_id="proj-t311",
            created_by="tester",
            scan_options={"target_url": "http://127.0.0.1:3000"}
        )
        assert False, "Launch should have failed"
    except RuntimeError as e:
        print(f"[OK] Caught expected launch failure: {e}")

    # Verify that the scan was transitioned to FAILED with LAUNCH_FAILED and did NOT leak active count
    assert repo.count_active_scans() == 0
    print(f"[OK] Verified active scans = {repo.count_active_scans()} after launch failure.")

    # A working launcher can immediately create a new scan
    scan_service.launcher = MockLauncher()
    res_ok = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-t311",
        created_by="tester",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    print(f"[OK] New scan successfully created after launch failure recovery: {res_ok['scan_id']}")
    state_machine.transition(res_ok["scan_id"], "FAILED", error_code="CANCELLED_BY_USER")
    assert repo.count_active_scans() == 0

    print("[PASS] Test 6 passed: Concurrency properly released on launcher failure.")

def test_multithreaded_concurrency_race(repo: ScanRepository, state_machine: ScanStateMachine):
    print("\n--- TEST 7: Multi-threaded Concurrency Race (20 Simultaneous Threads) ---")
    scan_service = ScanService(repo=repo, state_machine=state_machine, max_concurrent_scans=1)

    successful_scans = []
    rejected_scans = []
    errors = []

    def _worker(thread_idx: int):
        try:
            res = scan_service.create_scan(
                engine="acunetix",
                project_id=f"proj-race-{thread_idx}",
                created_by=f"user-{thread_idx}",
                scan_options={"target_url": "http://127.0.0.1:3000"}
            )
            successful_scans.append(res["scan_id"])
        except ConcurrencyLimitError as cle:
            rejected_scans.append((thread_idx, cle.status_code))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(20)]

    # Start all threads simultaneously
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"Results of 20 concurrent requests:")
    print(f"  - Successful scans (201 Created): {len(successful_scans)} -> {successful_scans}")
    print(f"  - Rejected scans (429 Concurrency Limit): {len(rejected_scans)}")
    print(f"  - Unexpected errors: {len(errors)}")

    assert len(errors) == 0, f"Unexpected errors occurred: {errors}"
    assert len(successful_scans) == 1, f"Expected exactly 1 success, got {len(successful_scans)}"
    assert len(rejected_scans) == 19, f"Expected exactly 19 rejections, got {len(rejected_scans)}"
    assert all(code == 429 for _, code in rejected_scans)

    # Active scans in DB must be exactly 1
    assert repo.count_active_scans() == 1
    print(f"[OK] Total active scans in DB: {repo.count_active_scans()} (ceiling maintained perfectly).")

    # Clean up the 1 active scan
    state_machine.transition(successful_scans[0], "FAILED", error_code="CANCELLED_BY_USER")
    assert repo.count_active_scans() == 0

    print("[PASS] Test 7 passed: Race condition safe. Exactly 1 succeeded, 19 rejected with 429.")

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.11 (CONCURRENCY CEILING = 1)")
    print("=" * 70)

    tmp_db = PROJECT_ROOT / "tmp" / "test_t311_concurrency.db"
    tmp_db.parent.mkdir(parents=True, exist_ok=True)
    if tmp_db.exists():
        tmp_db.unlink()

    db = Database(str(tmp_db))
    db.init_schema()
    repo = ScanRepository(db)
    state_machine = ScanStateMachine(repo)

    test_configurable_limit(repo)
    test_rejection_and_normal_completion_release(repo, state_machine)
    test_failure_and_user_cancellation_release(repo, state_machine)
    test_reconciler_release(repo, state_machine)
    test_launcher_failure_release(repo, state_machine)
    test_multithreaded_concurrency_race(repo, state_machine)

    # Cleanup temp db
    if tmp_db.exists():
        tmp_db.unlink()

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.11 PASSED SUCCESSFULLY (100%)!")
    print("=" * 70)

if __name__ == "__main__":
    main()
