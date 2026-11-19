#!/usr/bin/env python3
"""
Test script for Task T2.2: Acunetix API readiness polling with timeout.
Verifies:
1. Success case: Returns ready when Acunetix is responding (exits 0).
2. Timeout case: When Acunetix is unreachable, polls until timeout and exits with error code 10 (does not hang).
"""
import sys
import time
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def run_driver(acx_url: str, timeout_sec: int) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-t22-readiness",
        "--acunetix-url", acx_url,
        "--ready-timeout", str(timeout_sec)
    ]
    return subprocess.run(cmd, capture_output=True, text=True)

def main():
    print("=" * 60)
    print("RUNNING VERIFICATION FOR TASK T2.2 (READINESS POLLING)")
    print("=" * 60)

    # Detect which port has Acunetix running (8888 or 3443)
    active_url = None
    for port in [8888, 3443]:
        url = f"https://127.0.0.1:{port}"
        print(f"Checking candidate instance: {url}...")
        res = run_driver(url, timeout_sec=3)
        if res.returncode == 0:
            active_url = url
            print(f"Found active instance at {url}!")
            break

    assert active_url is not None, "Neither port 8888 nor 3443 responded. Is Acunetix running?"

    # --- TEST 1: SUCCESSFUL READINESS CHECK ---
    print(f"\n[Test 1] Testing readiness check against live instance at {active_url}...")
    t0 = time.time()
    res_success = run_driver(active_url, timeout_sec=10)
    elapsed_success = time.time() - t0
    
    print("STDOUT:")
    print(res_success.stdout)
    assert res_success.returncode == 0, f"Expected exit code 0, got {res_success.returncode}"
    assert "Acunetix API is READY" in res_success.stdout, "Missing readiness log message"
    assert "readiness check passed successfully" in res_success.stdout
    print(f"[PASS] Success test passed in {round(elapsed_success, 2)}s (exit code 0)")

    # --- TEST 2: TIMEOUT ON UNREACHABLE PORT (NEVER HANG) ---
    unreachable_url = "https://127.0.0.1:59999"
    timeout_limit = 4
    print(f"\n[Test 2] Testing timeout handling against unreachable endpoint: {unreachable_url} (timeout={timeout_limit}s)...")
    t0 = time.time()
    res_timeout = run_driver(unreachable_url, timeout_sec=timeout_limit)
    elapsed_timeout = time.time() - t0

    print("STDOUT:")
    print(res_timeout.stdout)
    print("STDERR:")
    print(res_timeout.stderr)

    assert res_timeout.returncode == 10, f"Expected exit code 10 on timeout, got {res_timeout.returncode}"
    assert "Readiness check timed out" in res_timeout.stdout or "Readiness check timed out" in res_timeout.stderr
    assert "failed to become ready" in res_timeout.stdout or "failed to become ready" in res_timeout.stderr
    
    # Verify execution time bounded around timeout_limit (between timeout_limit and timeout_limit + 3s, not hanging)
    assert timeout_limit <= elapsed_timeout <= timeout_limit + 4.0, (
        f"Execution time {elapsed_timeout}s was not within expected timeout window"
    )
    print(f"[PASS] Timeout test passed: exited cleanly with code 10 in {round(elapsed_timeout, 2)}s without hanging!")

    print("\n" + "=" * 60)
    print("TASK T2.2 VERIFICATION ALL PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
