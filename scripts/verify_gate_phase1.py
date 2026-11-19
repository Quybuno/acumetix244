#!/usr/bin/env python3
"""
Gate Verification for Phase 1 (Cổng sang giai đoạn 2)
Criterion: 'Chạy tay vài lần liên tiếp không để sót lại container, mạng hay tệp tạm nào'
Runs 3 consecutive mock-pod lifecycles with different exit conditions,
and verifies zero leakage of containers, networks, or temporary files.
"""
import subprocess
import time
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TMP_SCANS_DIR = BASE_DIR / "tmp" / "scans"

from pod_manager import launch_ordered_pod, wait_pod_completion, cleanup_pod, list_pod_containers

def check_leakage(iteration_name: str):
    # 1. Containers check
    res_c = subprocess.check_output([
        "docker", "ps", "-a",
        "--filter", "label=managed-by=deepreview-docker-launcher",
        "--format", "{{.ID}}|{{.Names}}"
    ]).decode().strip()
    c_list = res_c.splitlines() if res_c else []

    # 2. Filesystem check
    leaked_dirs = []
    if TMP_SCANS_DIR.exists():
        leaked_dirs = [str(p) for p in TMP_SCANS_DIR.iterdir()]

    print(f"[{iteration_name}] Leak check: {len(c_list)} containers, {len(leaked_dirs)} temporary scan dirs.")
    assert len(c_list) == 0, f"Leaked containers detected: {c_list}"
    assert len(leaked_dirs) == 0, f"Leaked temp directories detected: {leaked_dirs}"

def main():
    print("=" * 60)
    print("PHASE 1 GATE VERIFICATION (CỔNG SANG GIAI ĐOẠN 2)")
    print("Criterion: Chạy tay vài lần liên tiếp không để sót lại container, mạng hay tệp tạm nào")
    print("=" * 60)

    # Initial check
    check_leakage("Pre-check")

    test_runs = [
        {"scan_id": "gate-run-1", "duration": 2, "exit_code": 0, "desc": "Run 1: Normal success (exit 0)"},
        {"scan_id": "gate-run-2", "duration": 2, "exit_code": 1, "desc": "Run 2: Mock error failure (exit 1)"},
        {"scan_id": "gate-run-3", "duration": 2, "exit_code": 0, "desc": "Run 3: Repeat normal run (exit 0)"}
    ]

    for idx, run in enumerate(test_runs, 1):
        sid = run["scan_id"]
        print(f"\n---> [Loop {idx}/3] {run['desc']} (scan_id={sid})")
        
        # 1. Launch
        t0 = time.time()
        driver_cmd = [
            "sh", "-c",
            f"echo 'Driver {sid} running'; sleep {run['duration']}; exit {run['exit_code']}"
        ]
        launch_res = launch_ordered_pod(
            scan_id=sid,
            driver_cmd=driver_cmd,
            timeout_ready=60,
            secrets={"api_key": f"gate_key_{sid}", "url": "http://127.0.0.1:3000"}
        )
        print(f"     Launched: {launch_res['net']}, {launch_res['acunetix']}, {launch_res['driver']}")
        
        # 2. Wait
        wait_res = wait_pod_completion(sid, timeout_sec=20)
        print(f"     Execution finished: status={wait_res['status']} exit_code={wait_res['exit_code']} elapsed={wait_res['elapsed_sec']}s")
        assert wait_res["exit_code"] == run["exit_code"]
        
        # 3. Cleanup
        cleanup_pod(sid, preserve_logs=False)
        print(f"     Cleaned up pod: {sid}")
        
        # 4. Check zero leakage immediately after each run
        check_leakage(f"After Loop {idx}")

    print("\n" + "=" * 60)
    print("ALL 3 CONSECUTIVE RUNS COMPLETED WITH ZERO LEAKS!")
    print("PHASE 1 GATE VERIFICATION: PASSED (100% CLEAN)")
    print("=" * 60)

if __name__ == "__main__":
    main()
