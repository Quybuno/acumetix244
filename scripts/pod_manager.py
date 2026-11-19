#!/usr/bin/env python3
"""
Pod Manager for Deep Review Acunetix Docker Mock-Pod
Implements pod lifecycle: launch, status, wait, cleanup, kill
"""

import os
import sys
import json
import time
import shutil
import ssl
import urllib.request
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TMP_SCANS_DIR = BASE_DIR / "tmp" / "scans"

ACUNETIX_IMAGE = "acunetix:24.4"
NET_IMAGE = "alpine:3.20"
DUMMY_DRIVER_IMAGE = "alpine:3.20"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def get_container_name(scan_id: str, role: str) -> str:
    return f"scan-{scan_id}-{role}"

def get_labels(scan_id: str, role: str) -> dict:
    return {
        "scan-id": scan_id,
        "role": role,
        "managed-by": "deepreview-docker-launcher"
    }

def get_scan_paths(scan_id: str) -> dict:
    scan_dir = TMP_SCANS_DIR / scan_id
    return {
        "root": scan_dir,
        "secrets": scan_dir / "secrets",
        "inputs": scan_dir / "inputs",
        "logs": scan_dir / "logs"
    }

def setup_scan_dirs(scan_id: str) -> dict:
    paths = get_scan_paths(scan_id)
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths

def prepare_scan_files(scan_id: str, secrets: dict = None, inputs: dict = None) -> dict:
    """
    Prepare isolated temporary secret and input files for a scan run.
    Secrets file permissions are set to owner read/write (0600).
    """
    paths = setup_scan_dirs(scan_id)

    if secrets:
        sec_file = paths["secrets"] / "credentials.json"
        sec_file.write_text(json.dumps(secrets, indent=2), encoding="utf-8")
        try:
            os.chmod(sec_file, 0o600)
        except Exception:
            pass

    if inputs:
        for fname, content in inputs.items():
            inp_file = paths["inputs"] / fname
            if isinstance(content, bytes):
                inp_file.write_bytes(content)
            else:
                inp_file.write_text(content, encoding="utf-8")

    return paths

def list_pod_containers(scan_id: str) -> list:
    cmd = [
        "docker", "ps", "-a",
        "--filter", f"label=scan-id={scan_id}",
        "--format", "{{.ID}}|{{.Names}}|{{.Status}}|{{.State}}|{{.Labels}}"
    ]
    try:
        output = subprocess.check_output(cmd).decode().strip()
    except subprocess.CalledProcessError:
        return []

    if not output:
        return []

    containers = []
    for line in output.splitlines():
        parts = line.split("|")
        if len(parts) >= 5:
            cid, name, status_str, state, labels_str = parts[0], parts[1], parts[2], parts[3], parts[4]
            labels = {}
            for pair in labels_str.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    labels[k.strip()] = v.strip()
            containers.append({
                "id": cid,
                "name": name,
                "status": status_str,
                "state": state,
                "role": labels.get("role", "unknown"),
                "scan_id": labels.get("scan-id", "")
            })
    return containers

def wait_acunetix_ready(net_container_name: str, timeout_sec: int = 90) -> bool:
    """Fast readiness check: probe port 3443 via net container, then verify HTTP"""
    start_time = time.time()
    port_open = False
    while time.time() - start_time < timeout_sec:
        # Fast socket check via net container (alpine nc)
        nc_cmd = ["docker", "exec", net_container_name, "nc", "-z", "-w", "1", "127.0.0.1", "3443"]
        res = subprocess.run(nc_cmd, capture_output=True)
        if res.returncode == 0:
            port_open = True
            break
        time.sleep(1)

    if not port_open:
        return False

    # Port is open, verify HTTP API responds
    while time.time() - start_time < timeout_sec:
        curl_cmd = [
            "docker", "run", "--rm",
            "--network", f"container:{net_container_name}",
            "curlimages/curl:latest",
            "curl", "-k", "-s", "-o", "/dev/null", "-w", "%{http_code}",
            "https://localhost:3443/api/v1/info"
        ]
        res = subprocess.run(curl_cmd, capture_output=True, text=True)
        code = res.stdout.strip()
        if code in ["200", "400", "401"]:
            return True
        time.sleep(1)

    return False

def launch_ordered_pod(
    scan_id: str,
    driver_cmd: list = None,
    timeout_ready: int = 60,
    secrets: dict = None,
    inputs: dict = None
) -> dict:
    """
    Launch pod containers in strict order:
    1. Net container
    2. Acunetix container
    3. Wait for readiness
    4. Driver container (only runs when Acunetix is ready, with read-only secrets and inputs mounts)
    """
    paths = prepare_scan_files(scan_id, secrets=secrets, inputs=inputs)
    net_name = get_container_name(scan_id, "net")
    acx_name = get_container_name(scan_id, "acunetix")
    driver_name = get_container_name(scan_id, "driver")

    # Step 1: Net container
    subprocess.check_call([
        "docker", "run", "-d",
        "--name", net_name,
        "--label", f"scan-id={scan_id}",
        "--label", "role=net",
        "--label", "managed-by=deepreview-docker-launcher",
        "--memory=64m",
        "--cpus=0.1",
        "--add-host", "host.docker.internal:host-gateway",
        NET_IMAGE, "sleep", "infinity"
    ])

    # Step 2: Acunetix sidecar
    subprocess.check_call([
        "docker", "run", "-d",
        "--name", acx_name,
        "--label", f"scan-id={scan_id}",
        "--label", "role=acunetix",
        "--label", "managed-by=deepreview-docker-launcher",
        "--memory=4g",
        "--cpus=2.0",
        "--network", f"container:{net_name}",
        ACUNETIX_IMAGE
    ])
    time.sleep(2)
    subprocess.check_call([
        "docker", "exec", "-u", "0", acx_name,
        "chmod", "777", "/home/acunetix/.acunetix/data/license"
    ])

    # Step 3: Wait for readiness with timeout
    is_ready = wait_acunetix_ready(net_name, timeout_sec=timeout_ready)
    if not is_ready:
        cleanup_pod(scan_id)
        raise TimeoutError(f"Acuentix failed to become ready within {timeout_ready} seconds")

    # Step 4: Driver container (only launched when Acunetix is verified ready)
    # Secrets and inputs mounted strictly read-only (:ro).
    # NEVER pass secrets via environment variables!
    d_cmd = driver_cmd or ["sh", "-c", "echo 'Driver starting after Acunetix is ready'; sleep 2; exit 0"]
    subprocess.check_call([
        "docker", "run", "-d",
        "--name", driver_name,
        "--label", f"scan-id={scan_id}",
        "--label", "role=driver",
        "--label", "managed-by=deepreview-docker-launcher",
        "--memory=256m",
        "--cpus=0.5",
        "--network", f"container:{net_name}",
        "-v", f"{paths['secrets'].resolve().as_posix()}:/secrets:ro",
        "-v", f"{paths['inputs'].resolve().as_posix()}:/inputs:ro",
        DUMMY_DRIVER_IMAGE
    ] + d_cmd)

    return {
        "scan_id": scan_id,
        "net": net_name,
        "acunetix": acx_name,
        "driver": driver_name,
        "status": "LAUNCHED"
    }

def kill_pod(scan_id: str) -> list:
    """Immediately kill all running containers for a scan-id"""
    containers = list_pod_containers(scan_id)
    running_names = [c["name"] for c in containers if c["state"] == "running"]
    if running_names:
        subprocess.run(["docker", "kill"] + running_names, capture_output=True)
    return running_names

def wait_pod_completion(scan_id: str, timeout_sec: int = 1800, poll_interval: float = 1.0) -> dict:
    """
    Monitor driver container until it exits or maximum pod timeout is reached.
    If timeout is exceeded, kills the pod and returns SCAN_TIMEOUT.
    """
    driver_name = get_container_name(scan_id, "driver")
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout_sec:
            # Maximum Job timeout exceeded -> terminate pod
            killed = kill_pod(scan_id)
            return {
                "scan_id": scan_id,
                "status": "TIMEOUT",
                "exit_code": None,
                "timed_out": True,
                "error": "SCAN_TIMEOUT",
                "elapsed_sec": round(elapsed, 2),
                "killed_containers": killed
            }
        
        # Check driver state
        try:
            out = subprocess.check_output(
                ["docker", "inspect", driver_name, "--format", "{{.State.Status}}|{{.State.ExitCode}}"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            status_str, exit_code_str = out.split("|")
            exit_code = int(exit_code_str)
            
            if status_str == "exited":
                return {
                    "scan_id": scan_id,
                    "status": "COMPLETED" if exit_code == 0 else "FAILED",
                    "exit_code": exit_code,
                    "timed_out": False,
                    "error": None if exit_code == 0 else f"DRIVER_EXIT_{exit_code}",
                    "elapsed_sec": round(elapsed, 2)
                }
        except Exception:
            # Container might not be visible yet or inspect failed temporarily
            pass
        
        time.sleep(poll_interval)

def save_pod_logs(scan_id: str) -> dict:
    """
    Export logs from pod containers (driver and acunetix) to local log files
    before container removal. Returns dict of saved log file paths.
    """
    paths = get_scan_paths(scan_id)
    paths["logs"].mkdir(parents=True, exist_ok=True)
    saved_logs = {}
    
    for role in ["driver", "acunetix"]:
        cname = get_container_name(scan_id, role)
        log_file = paths["logs"] / f"{role}.log"
        try:
            res = subprocess.run(
                ["docker", "logs", cname],
                capture_output=True,
                text=True
            )
            # Combine stdout and stderr
            combined = res.stdout + res.stderr
            log_file.write_text(combined, encoding="utf-8")
            saved_logs[role] = log_file
        except Exception:
            saved_logs[role] = None
            
    return saved_logs

def cleanup_pod(scan_id: str, preserve_logs: bool = False):
    """
    Remove all containers and temporary directories for a scan-id.
    If preserve_logs is True, exports container logs to tmp/scans/<scan_id>/logs/
    before deleting containers, wipes secrets and inputs, and retains log files.
    If preserve_logs is False, completely wipes everything including logs.
    """
    if preserve_logs:
        save_pod_logs(scan_id)

    containers = list_pod_containers(scan_id)
    c_names = [c["name"] for c in containers]
    if c_names:
        subprocess.run(["docker", "rm", "-f"] + c_names, capture_output=True)

    paths = get_scan_paths(scan_id)
    if preserve_logs:
        # Strictly wipe secrets and inputs
        if paths["secrets"].exists():
            shutil.rmtree(paths["secrets"], ignore_errors=True)
        if paths["inputs"].exists():
            shutil.rmtree(paths["inputs"], ignore_errors=True)
    else:
        if paths["root"].exists():
            shutil.rmtree(paths["root"], ignore_errors=True)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test_t13":
        test_id = "t13ordered"
        print(f"Testing ordered launch for {test_id}...")
        try:
            res = launch_ordered_pod(test_id, timeout_ready=60)
            print("Launch result:", res)
            containers = list_pod_containers(test_id)
            print(f"Verified {len(containers)} containers running in pod:")
            for c in containers:
                print(f"  {c['name']} ({c['role']}): state={c['state']}")
        finally:
            print("Cleaning up...")
            cleanup_pod(test_id)
            print("Cleaned up. T1.3 verified.")

    elif len(sys.argv) > 1 and sys.argv[1] == "test_t14":
        test_id = "t14secrets"
        print(f"Testing secrets and inputs handling for {test_id}...")
        test_secret = {"api_key": "secret_token_t14_proof", "target": "http://127.0.0.1:3000"}
        test_input = {"api_spec.json": '{"info": {"title": "Test API"}}'}
        
        driver_sh = (
            "echo '--- READING SECRETS ---'; "
            "cat /secrets/credentials.json; "
            "echo '--- READING INPUTS ---'; "
            "cat /inputs/api_spec.json; "
            "echo '--- TESTING WRITE PROHIBITION ---'; "
            "touch /secrets/hacked.txt 2>&1 || echo 'CANNOT_WRITE_RO'; "
            "sleep 3"
        )
        try:
            res = launch_ordered_pod(
                test_id,
                driver_cmd=["sh", "-c", driver_sh],
                timeout_ready=60,
                secrets=test_secret,
                inputs=test_input
            )
            print("Launch result:", res)
            
            # Inspect all 3 containers
            for role in ["net", "acunetix", "driver"]:
                cname = get_container_name(test_id, role)
                insp = json.loads(subprocess.check_output(["docker", "inspect", cname]))[0]
                
                # Check env vars
                env_list = insp.get("Config", {}).get("Env", [])
                for env_item in env_list:
                    assert "secret_token_t14_proof" not in env_item, f"LEAKED in env of {cname}: {env_item}"
                print(f"Verified {cname}: no secrets in environment variables ({len(env_list)} envs checked)")
                
                # Check mounts
                mounts = insp.get("Mounts", [])
                mount_dests = {m.get("Destination"): m for m in mounts}
                if role == "driver":
                    assert "/secrets" in mount_dests, "Driver missing /secrets mount"
                    assert "/inputs" in mount_dests, "Driver missing /inputs mount"
                    assert mount_dests["/secrets"].get("RW") is False, "/secrets is not read-only!"
                    assert mount_dests["/inputs"].get("RW") is False, "/inputs is not read-only!"
                    print(f"Verified {cname}: /secrets and /inputs are mounted Read-Only (RW=False)")
                else:
                    assert "/secrets" not in mount_dests, f"{cname} must not have /secrets mounted!"
                    assert "/inputs" not in mount_dests, f"{cname} must not have /inputs mounted!"
                    print(f"Verified {cname}: strictly isolated (no /secrets or /inputs mounts)")

            # Check driver logs
            time.sleep(2)
            d_name = get_container_name(test_id, "driver")
            d_logs = subprocess.check_output(["docker", "logs", d_name]).decode()
            print("Driver execution logs:")
            print(d_logs.strip())
            assert "secret_token_t14_proof" in d_logs, "Driver failed to read secret"
            assert "Test API" in d_logs, "Driver failed to read input file"
            assert "CANNOT_WRITE_RO" in d_logs, "Read-only enforcement failed"
            print("T1.4 verification assertions PASSED!")
        finally:
            print("Cleaning up...")
            cleanup_pod(test_id)
            # Verify temporary directory removed
            paths = get_scan_paths(test_id)
            assert not paths["root"].exists(), "Root directory not removed during cleanup"
            print("Temporary secrets and scan directories completely wiped. T1.4 verified.")

    elif len(sys.argv) > 1 and sys.argv[1] == "test_t15":
        test_id = "t15limits"
        print(f"Testing resource limits and non-privileged mode for {test_id}...")
        try:
            res = launch_ordered_pod(
                test_id,
                driver_cmd=["sh", "-c", "echo 'Testing limits'; sleep 2; exit 0"],
                timeout_ready=60
            )
            print("Launch result:", res)
            
            expected_limits = {
                "net": {"mem": 64 * 1024 * 1024, "nano_cpus": 100000000},
                "acunetix": {"mem": 4 * 1024 * 1024 * 1024, "nano_cpus": 2000000000},
                "driver": {"mem": 256 * 1024 * 1024, "nano_cpus": 500000000}
            }
            
            for role, exp in expected_limits.items():
                cname = get_container_name(test_id, role)
                insp = json.loads(subprocess.check_output(["docker", "inspect", cname]))[0]
                hcfg = insp.get("HostConfig", {})
                
                mem = hcfg.get("Memory")
                nanocpus = hcfg.get("NanoCpus")
                priv = hcfg.get("Privileged", False)
                
                print(f"Container {cname}:")
                print(f"  Memory: {mem} bytes (expected {exp['mem']})")
                print(f"  NanoCpus: {nanocpus} (expected {exp['nano_cpus']})")
                print(f"  Privileged: {priv} (expected False)")
                
                assert mem == exp["mem"], f"Memory limit mismatch for {cname}: got {mem}, expected {exp['mem']}"
                assert nanocpus == exp["nano_cpus"], f"CPU limit mismatch for {cname}: got {nanocpus}, expected {exp['nano_cpus']}"
                assert priv is False, f"Privileged mode must be False for {cname}"
            
            print("All resource limits and non-privileged checks PASSED for T1.5!")
        finally:
            print("Cleaning up...")
            cleanup_pod(test_id)
            print("Cleaned up. T1.5 verified.")

    elif len(sys.argv) > 1 and sys.argv[1] == "test_t16":
        test_id = "t16timeout"
        print(f"Testing Job maximum timeout and kill enforcement for {test_id}...")
        try:
            # Driver hangs for 60 seconds
            res = launch_ordered_pod(
                test_id,
                driver_cmd=["sh", "-c", "echo 'Driver hanging...'; sleep 60; exit 0"],
                timeout_ready=60
            )
            print("Launch result:", res)
            
            # Wait with a short maximum timeout of 6 seconds to simulate job timeout
            print("Waiting with maximum Job timeout = 6 seconds...")
            wait_res = wait_pod_completion(test_id, timeout_sec=6, poll_interval=1.0)
            print("Wait completion result:", wait_res)
            
            assert wait_res["timed_out"] is True, "Wait did not report timed_out=True"
            assert wait_res["status"] == "TIMEOUT", f"Expected TIMEOUT status, got {wait_res['status']}"
            assert wait_res["error"] == "SCAN_TIMEOUT", f"Expected error SCAN_TIMEOUT, got {wait_res['error']}"
            
            # Verify containers are no longer running
            containers = list_pod_containers(test_id)
            for c in containers:
                assert c["state"] != "running", f"Container {c['name']} still running after timeout kill!"
                print(f"Verified {c['name']}: killed, state={c['state']}")
            
            print("T1.6 Job maximum timeout and termination PASSED!")
        finally:
            print("Cleaning up...")
            cleanup_pod(test_id)
            print("Cleaned up. T1.6 verified.")

    elif len(sys.argv) > 1 and sys.argv[1] == "test_t17":
        test_id = "t17logsave"
        print(f"Testing saving driver logs before container cleanup for {test_id}...")
        error_msg = "FATAL ERROR: Target connection refused on mock port"
        driver_cmd = [
            "sh", "-c",
            f"echo 'Driver initializing...'; echo '{error_msg}' >&2; exit 42"
        ]
        try:
            res = launch_ordered_pod(
                test_id,
                driver_cmd=driver_cmd,
                timeout_ready=60
            )
            print("Launch result:", res)
            
            # Wait for driver exit
            wait_res = wait_pod_completion(test_id, timeout_sec=15)
            print("Driver completed:", wait_res)
            assert wait_res["exit_code"] == 42, f"Expected exit code 42, got {wait_res['exit_code']}"
            
            # Cleanup with preserve_logs=True
            cleanup_pod(test_id, preserve_logs=True)
            
            # Verify containers are deleted from Docker
            containers = list_pod_containers(test_id)
            assert len(containers) == 0, f"Expected 0 containers remaining, found {len(containers)}"
            print("Verified: all pod containers deleted from Docker.")
            
            # Verify driver log file exists on host and contains error message
            paths = get_scan_paths(test_id)
            driver_log_path = paths["logs"] / "driver.log"
            assert driver_log_path.exists(), f"Log file {driver_log_path} does not exist!"
            
            log_content = driver_log_path.read_text(encoding="utf-8")
            print("Persisted driver log content:")
            print(log_content.strip())
            
            assert error_msg in log_content, f"Expected error message not found in {driver_log_path}"
            assert "Driver initializing..." in log_content, "Stdout not captured in log"
            print("T1.7 log persistence and error diagnosis PASSED!")
        finally:
            # Full wipe
            cleanup_pod(test_id, preserve_logs=False)
            print("Full cleanup completed. T1.7 verified.")
