"""
Verification Script for Task T3.8: Scan State Machine
Validates:
1. Strict one-way lifecycle transitions:
   SCANNING -> PARSING -> COMPLETED
2. Failure paths with mandatory error_code:
   SCANNING -> FAILED (with error_code)
   SCANNING -> PARSING -> FAILED (with error_code)
3. Strict enforcement: FAILED without valid error_code is strictly rejected.
4. Immutability of terminal states:
   COMPLETED and FAILED can NEVER transition to any state.
5. Strict one-way enforcement:
   Backward transitions (PARSING -> SCANNING) and skip transitions (SCANNING -> COMPLETED) are strictly rejected.
6. Immediate concurrency limit rejection:
   When active scan exists (in SCANNING or PARSING), new scan is rejected immediately (no queueing).
   New scan allowed only after transition to terminal state (COMPLETED or FAILED).
"""

import sys
import os
import json
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.database import Database
from backend.models.scan import (
    ScanJob,
    ScanRepository,
    hash_webhook_token,
    VALID_STATUSES,
    VALID_ERROR_CODES
)
from backend.services.state_machine import (
    ScanStateMachine,
    InvalidStateTransitionError
)
from backend.services.scan_service import (
    ScanService,
    ConcurrencyLimitError
)
from backend.services.launcher import MockLauncher

def test_valid_successful_lifecycle(state_machine: ScanStateMachine, repo: ScanRepository):
    print("\n--- TEST 1: Strict One-Way Flow: SCANNING -> PARSING -> COMPLETED ---")
    scan_id = "scan-sm-001"
    scan = ScanJob(
        scan_id=scan_id,
        project_id="proj-sm",
        engine="acunetix",
        created_by="tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token("token-001")
    )
    repo.create_scan(scan)
    assert scan.status == "SCANNING"
    assert scan.completed_at is None
    print(f"Created scan {scan_id} in initial status 'SCANNING'.")

    # Step 1: SCANNING -> PARSING
    s1 = state_machine.transition(scan_id=scan_id, new_status="PARSING")
    assert s1.status == "PARSING"
    assert s1.completed_at is None
    print(f"[OK] Transitioned {scan_id}: SCANNING -> PARSING.")

    # Step 2: PARSING -> COMPLETED
    s2 = state_machine.transition(scan_id=scan_id, new_status="COMPLETED")
    assert s2.status == "COMPLETED"
    assert s2.error_code is None
    assert s2.completed_at is not None, "completed_at timestamp must be automatically recorded"
    print(f"[OK] Transitioned {scan_id}: PARSING -> COMPLETED (completed_at={s2.completed_at}).")

    print("[PASS] Test 1 passed: Valid successful lifecycle transitions verified.")

def test_valid_failure_paths(state_machine: ScanStateMachine, repo: ScanRepository):
    print("\n--- TEST 2: Failure Transitions With Error Codes ---")

    # Path A: SCANNING -> FAILED (e.g. JOB_LOST or LAUNCH_FAILED)
    scan_a = "scan-sm-fail-a"
    repo.create_scan(ScanJob(
        scan_id=scan_a,
        project_id="proj-sm",
        engine="acunetix",
        created_by="tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token("token-fail-a")
    ))
    res_a = state_machine.transition(scan_id=scan_a, new_status="FAILED", error_code="JOB_LOST")
    assert res_a.status == "FAILED"
    assert res_a.error_code == "JOB_LOST"
    assert res_a.completed_at is not None
    print(f"[OK] Path A: {scan_a} transitioned SCANNING -> FAILED (error_code='JOB_LOST').")

    # Path B: SCANNING -> PARSING -> FAILED (e.g. PARSE_FAILED)
    scan_b = "scan-sm-fail-b"
    repo.create_scan(ScanJob(
        scan_id=scan_b,
        project_id="proj-sm",
        engine="acunetix",
        created_by="tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token("token-fail-b")
    ))
    state_machine.transition(scan_id=scan_b, new_status="PARSING")
    res_b = state_machine.transition(scan_id=scan_b, new_status="FAILED", error_code="PARSE_FAILED")
    assert res_b.status == "FAILED"
    assert res_b.error_code == "PARSE_FAILED"
    assert res_b.completed_at is not None
    print(f"[OK] Path B: {scan_b} transitioned SCANNING -> PARSING -> FAILED (error_code='PARSE_FAILED').")

    print("[PASS] Test 2 passed: Valid failure paths with authorized error codes verified.")

def test_mandatory_error_code_enforcement(state_machine: ScanStateMachine, repo: ScanRepository):
    print("\n--- TEST 3: Strict Error Code Enforcement for FAILED Status ---")
    scan_id = "scan-sm-errcode-check"
    repo.create_scan(ScanJob(
        scan_id=scan_id,
        project_id="proj-sm",
        engine="acunetix",
        created_by="tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token("token-check")
    ))

    # 1. Transition to FAILED with None error_code -> MUST FAIL
    try:
        state_machine.transition(scan_id=scan_id, new_status="FAILED", error_code=None)
        assert False, "Should reject transition to FAILED with error_code=None"
    except InvalidStateTransitionError as e:
        print(f"[OK] Rejected FAILED without error_code: {e}")

    # 2. Transition to FAILED with empty string error_code -> MUST FAIL
    try:
        state_machine.transition(scan_id=scan_id, new_status="FAILED", error_code="   ")
        assert False, "Should reject transition to FAILED with empty error_code"
    except InvalidStateTransitionError as e:
        print(f"[OK] Rejected FAILED with empty error_code: {e}")

    # 3. Transition to FAILED with unauthorized error_code -> MUST FAIL
    try:
        state_machine.transition(scan_id=scan_id, new_status="FAILED", error_code="UNKNOWN_CUSTOM_ERROR")
        assert False, "Should reject transition to FAILED with unauthorized error_code"
    except InvalidStateTransitionError as e:
        print(f"[OK] Rejected FAILED with unauthorized error_code: {e}")

    # 4. Transition to COMPLETED with an error_code -> MUST FAIL
    state_machine.transition(scan_id=scan_id, new_status="PARSING")
    try:
        state_machine.transition(scan_id=scan_id, new_status="COMPLETED", error_code="SOME_ERROR")
        assert False, "Should reject transition to COMPLETED when error_code is present"
    except InvalidStateTransitionError as e:
        print(f"[OK] Rejected COMPLETED with error_code: {e}")

    # Cleanup active scan in Test 3
    state_machine.transition(scan_id=scan_id, new_status="FAILED", error_code="PARSE_FAILED")

    print("[PASS] Test 3 passed: Strict error code constraints enforced 100%.")

def test_terminal_state_immutability(state_machine: ScanStateMachine, repo: ScanRepository):
    print("\n--- TEST 4: Immutability of Terminal States (COMPLETED & FAILED) ---")

    # A. Scan in COMPLETED state
    scan_comp = "scan-sm-terminal-completed"
    repo.create_scan(ScanJob(
        scan_id=scan_comp,
        project_id="proj-sm",
        engine="acunetix",
        created_by="tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token("token-comp")
    ))
    state_machine.transition(scan_comp, "PARSING")
    state_machine.transition(scan_comp, "COMPLETED")

    for illegal_target in ["SCANNING", "PARSING", "FAILED"]:
        try:
            state_machine.transition(scan_comp, illegal_target, error_code="JOB_LOST" if illegal_target == "FAILED" else None)
            assert False, f"COMPLETED must not transition to {illegal_target}"
        except InvalidStateTransitionError as e:
            print(f"[OK] Blocked transition COMPLETED -> {illegal_target}: {e.message}")

    # B. Scan in FAILED state
    scan_fail = "scan-sm-terminal-failed"
    repo.create_scan(ScanJob(
        scan_id=scan_fail,
        project_id="proj-sm",
        engine="acunetix",
        created_by="tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token("token-fail")
    ))
    state_machine.transition(scan_fail, "FAILED", error_code="SCAN_TIMEOUT")

    for illegal_target in ["SCANNING", "PARSING", "COMPLETED"]:
        try:
            state_machine.transition(scan_fail, illegal_target)
            assert False, f"FAILED must not transition to {illegal_target}"
        except InvalidStateTransitionError as e:
            print(f"[OK] Blocked transition FAILED -> {illegal_target}: {e.message}")

    print("[PASS] Test 4 passed: Terminal states are strictly immutable.")

def test_illegal_order_transitions(state_machine: ScanStateMachine, repo: ScanRepository):
    print("\n--- TEST 5: Strict One-Way: No Backward or Skip Transitions ---")
    scan_id = "scan-sm-illegal-order"
    repo.create_scan(ScanJob(
        scan_id=scan_id,
        project_id="proj-sm",
        engine="acunetix",
        created_by="tester",
        status="SCANNING",
        target="http://127.0.0.1:3000",
        token_hash=hash_webhook_token("token-order")
    ))

    # 1. Skip transition: SCANNING -> COMPLETED directly (skipping PARSING) -> MUST FAIL
    try:
        state_machine.transition(scan_id, "COMPLETED")
        assert False, "SCANNING must not skip directly to COMPLETED"
    except InvalidStateTransitionError as e:
        print(f"[OK] Blocked skip transition SCANNING -> COMPLETED: {e.message}")

    # 2. Advance to PARSING
    state_machine.transition(scan_id, "PARSING")

    # 3. Backward transition: PARSING -> SCANNING -> MUST FAIL
    try:
        state_machine.transition(scan_id, "SCANNING")
        assert False, "PARSING must not transition backward to SCANNING"
    except InvalidStateTransitionError as e:
        print(f"[OK] Blocked backward transition PARSING -> SCANNING: {e.message}")

    # Cleanup active scan in Test 5
    state_machine.transition(scan_id=scan_id, new_status="FAILED", error_code="PARSE_FAILED")

    print("[PASS] Test 5 passed: Out-of-order and backward transitions strictly prohibited.")

def test_concurrency_ceiling_and_zero_queue(db: Database, repo: ScanRepository):
    print("\n--- TEST 6: Concurrency Ceiling Enforcement (Limit = 1, Zero Queueing) ---")
    launcher = MockLauncher()
    state_machine = ScanStateMachine(repo)
    scan_service = ScanService(
        repo=repo,
        launcher=launcher,
        max_concurrent_scans=1
    )

    # 1. Create first scan -> Should succeed (active = 1)
    res1 = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-q",
        created_by="user1",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    scan1_id = res1["scan_id"]
    print(f"Created active scan 1: {scan1_id} (status: SCANNING)")
    assert repo.count_active_scans() == 1

    # 2. Attempt second scan while scan 1 is in SCANNING -> Must be rejected immediately
    try:
        scan_service.create_scan(
            engine="acunetix",
            project_id="proj-q",
            created_by="user2",
            scan_options={"target_url": "http://127.0.0.1:3000"}
        )
        assert False, "Second scan must be rejected when active scans == 1"
    except ConcurrencyLimitError as e:
        print(f"[OK] Immediate rejection while scan 1 is SCANNING: {e.message}")

    # 3. Transition scan 1: SCANNING -> PARSING (still active = 1)
    state_machine.transition(scan1_id, "PARSING")
    assert repo.count_active_scans() == 1

    # Attempt third scan while scan 1 is in PARSING -> Must be rejected immediately
    try:
        scan_service.create_scan(
            engine="acunetix",
            project_id="proj-q",
            created_by="user3",
            scan_options={"target_url": "http://127.0.0.1:3000"}
        )
        assert False, "Third scan must be rejected when active scans == 1"
    except ConcurrencyLimitError as e:
        print(f"[OK] Immediate rejection while scan 1 is PARSING: {e.message}")

    # 4. Transition scan 1 to COMPLETED -> active scans drops to 0
    state_machine.transition(scan1_id, "COMPLETED")
    assert repo.count_active_scans() == 0
    print(f"Scan 1 transitioned to COMPLETED. Active scans: {repo.count_active_scans()}")

    # 5. New scan request now succeeds immediately
    res2 = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-q",
        created_by="user4",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    scan2_id = res2["scan_id"]
    print(f"[OK] Permitted new scan 2 after scan 1 completed: {scan2_id}")
    assert repo.count_active_scans() == 1

    # 6. Fail scan 2 with error_code -> active scans drops to 0 again
    state_machine.transition(scan2_id, "FAILED", error_code="SCAN_TIMEOUT")
    assert repo.count_active_scans() == 0
    print(f"Scan 2 transitioned to FAILED (SCAN_TIMEOUT). Active scans: {repo.count_active_scans()}")

    # 7. Permitted new scan 3 immediately
    res3 = scan_service.create_scan(
        engine="acunetix",
        project_id="proj-q",
        created_by="user5",
        scan_options={"target_url": "http://127.0.0.1:3000"}
    )
    scan3_id = res3["scan_id"]
    print(f"[OK] Permitted new scan 3 after scan 2 failed: {scan3_id}")

    print("[PASS] Test 6 passed: Concurrency limit strictly enforced with zero queueing.")

def main():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR TASK T3.8 (SCAN STATE MACHINE)")
    print("=" * 70)

    tmp_db = PROJECT_ROOT / "tmp" / "test_t38_state_machine.db"
    tmp_db.parent.mkdir(parents=True, exist_ok=True)
    if tmp_db.exists():
        tmp_db.unlink()

    db = Database(str(tmp_db))
    db.init_schema()
    repo = ScanRepository(db)
    logger = logging.getLogger("test_t38_logger")
    state_machine = ScanStateMachine(repo=repo, logger=logger)

    test_valid_successful_lifecycle(state_machine, repo)
    test_valid_failure_paths(state_machine, repo)
    test_mandatory_error_code_enforcement(state_machine, repo)
    test_terminal_state_immutability(state_machine, repo)
    test_illegal_order_transitions(state_machine, repo)
    test_concurrency_ceiling_and_zero_queue(db, repo)

    # Cleanup
    if tmp_db.exists():
        tmp_db.unlink()

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS FOR TASK T3.8 PASSED SUCCESSFULLY (100%)!")
    print("=" * 70)

if __name__ == "__main__":
    main()
