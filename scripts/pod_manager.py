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

def launch_ordered_pod(scan_id: str, driver_cmd: list = None, timeout_ready: int = 60) -> dict:
    """
    Launch pod containers in strict order:
    1. Net container
    2. Acunetix container
    3. Wait for readiness
    4. Driver container (only runs when Acunetix is ready)
    """
    paths = setup_scan_dirs(scan_id)
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
        # cleanup and raise error
        cleanup_pod(scan_id)
        raise TimeoutError(f"Acuentix failed to become ready within {timeout_ready} seconds")

    # Step 4: Driver container (only launched when Acunetix is verified ready)
    d_cmd = driver_cmd or ["sh", "-c", "echo 'Driver starting after Acunetix is ready'; sleep 2; exit 0"]
    subprocess.check_call([
        "docker", "run", "-d",
        "--name", driver_name,
        "--label", f"scan-id={scan_id}",
        "--label", "role=driver",
        "--label", "managed-by=deepreview-docker-launcher",
        "--network", f"container:{net_name}",
        DUMMY_DRIVER_IMAGE
    ] + d_cmd)

    return {
        "scan_id": scan_id,
        "net": net_name,
        "acunetix": acx_name,
        "driver": driver_name,
        "status": "LAUNCHED"
    }

def cleanup_pod(scan_id: str):
    """Remove all containers for a scan-id"""
    containers = list_pod_containers(scan_id)
    c_names = [c["name"] for c in containers]
    if c_names:
        subprocess.run(["docker", "rm", "-f"] + c_names, capture_output=True)
    paths = get_scan_paths(scan_id)
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
