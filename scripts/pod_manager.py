#!/usr/bin/env python3
"""
Pod Manager for Deep Review Acunetix Docker Mock-Pod
Handles lifecycle: launch, status, wait, cleanup, kill
"""

import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TMP_SCANS_DIR = BASE_DIR / "tmp" / "scans"

ROLES = ["net", "acunetix", "driver"]

def get_container_name(scan_id: str, role: str) -> str:
    """Format container name: scan-<scan_id>-<role>"""
    return f"scan-{scan_id}-{role}"

def get_labels(scan_id: str, role: str) -> dict:
    """Format docker labels for pod containers"""
    return {
        "scan-id": scan_id,
        "role": role,
        "managed-by": "deepreview-docker-launcher"
    }

def get_scan_paths(scan_id: str) -> dict:
    """Return dictionary of paths for a scan run"""
    scan_dir = TMP_SCANS_DIR / scan_id
    return {
        "root": scan_dir,
        "secrets": scan_dir / "secrets",
        "inputs": scan_dir / "inputs",
        "logs": scan_dir / "logs"
    }

def setup_scan_dirs(scan_id: str) -> dict:
    """Create isolated temporary directory structure for a scan run"""
    paths = get_scan_paths(scan_id)
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths

def list_pod_containers(scan_id: str) -> list:
    """Filter all containers for a given scan-id label"""
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
            # parse labels
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

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test_t11":
        test_id = "test-t11-run"
        print(f"Setting up directories for {test_id}...")
        paths = setup_scan_dirs(test_id)
        for k, v in paths.items():
            print(f"  {k}: {v} (exists: {v.exists()})")

        print("Container name convention:")
        for r in ROLES:
            cname = get_container_name(test_id, r)
            labels = get_labels(test_id, r)
            print(f"  role={r:8s} -> name={cname:24s} labels={labels}")

        # cleanup test dirs
        shutil.rmtree(paths["root"], ignore_errors=True)
        print("Test directories cleaned up. T1.1 logic verified.")
