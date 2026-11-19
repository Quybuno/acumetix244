#!/usr/bin/env python3
"""
CLI script to cleanup a mock pod for Acunetix scanning (Phase 1)
Usage: python cleanup.py <scan_id> [--preserve-logs]
"""
import sys
import json
import argparse
from pathlib import Path

# Add parent directory to path so pod_manager can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pod_manager import cleanup_pod, list_pod_containers, get_scan_paths

def main():
    parser = argparse.ArgumentParser(description="Cleanup Deep Review Acunetix Mock-Pod")
    parser.add_argument("scan_id", help="Unique scan identifier to cleanup")
    parser.add_argument("--preserve-logs", action="store_true", help="Preserve driver logs on host before container removal")

    args = parser.parse_args()
    print(f"[*] Cleaning up pod for scan_id='{args.scan_id}' (preserve_logs={args.preserve_logs})...")

    containers_before = list_pod_containers(args.scan_id)
    print(f"[*] Found {len(containers_before)} containers to remove: {[c['name'] for c in containers_before]}")

    cleanup_pod(args.scan_id, preserve_logs=args.preserve_logs)

    containers_after = list_pod_containers(args.scan_id)
    paths = get_scan_paths(args.scan_id)

    print(f"[+] Remaining containers for scan-id='{args.scan_id}': {len(containers_after)}")
    if args.preserve_logs:
        log_file = paths["logs"] / "driver.log"
        print(f"[+] Logs preserved: {log_file.exists()} (path: {log_file})")
    else:
        print(f"[+] Root temporary directory exists: {paths['root'].exists()}")

    print(f"[+] Cleanup completed for '{args.scan_id}'.")

if __name__ == "__main__":
    main()
