#!/usr/bin/env python3
"""
CLI script to launch a mock pod for Acunetix scanning (Phase 1)
Usage: python launch.py <scan_id> [--duration <sec>] [--exit-code <code>] [--secrets-file <path>]
"""
import sys
import json
import argparse
from pathlib import Path

# Add parent directory to path so pod_manager can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pod_manager import launch_ordered_pod, get_pod_status, wait_pod_completion

def main():
    parser = argparse.ArgumentParser(description="Launch Deep Review Acunetix Mock-Pod")
    parser.add_argument("scan_id", help="Unique scan identifier")
    parser.add_argument("--duration", type=int, default=5, help="Driver execution duration in seconds before exit")
    parser.add_argument("--exit-code", type=int, default=0, help="Driver exit code")
    parser.add_argument("--secrets-file", type=str, default=None, help="Path to JSON file containing secrets")
    parser.add_argument("--timeout-ready", type=int, default=60, help="Readiness check timeout in seconds")
    parser.add_argument("--wait", action="store_true", help="Wait for driver to complete and output final status")
    
    args = parser.parse_args()
    
    secrets = None
    if args.secrets_file:
        sec_path = Path(args.secrets_file)
        if sec_path.exists():
            secrets = json.loads(sec_path.read_text(encoding="utf-8"))
        else:
            print(f"Warning: secrets file {args.secrets_file} not found, proceeding without it.")
    else:
        secrets = {
            "api_key": f"mock_key_{args.scan_id}",
            "target_url": "http://127.0.0.1:3000"
        }

    driver_cmd = [
        "sh", "-c",
        f"echo 'Driver {args.scan_id} started. Simulating workload for {args.duration}s...'; "
        f"if [ -f /secrets/credentials.json ]; then echo 'Secrets file verified accessible'; fi; "
        f"sleep {args.duration}; "
        f"echo 'Driver {args.scan_id} exiting with code {args.exit_code}'; "
        f"exit {args.exit_code}"
    ]

    print(f"[*] Launching pod for scan_id='{args.scan_id}'...")
    launch_res = launch_ordered_pod(
        scan_id=args.scan_id,
        driver_cmd=driver_cmd,
        timeout_ready=args.timeout_ready,
        secrets=secrets
    )
    print(f"[+] Pod launched successfully: {json.dumps(launch_res, indent=2)}")

    status = get_pod_status(args.scan_id)
    print(f"[+] Initial Pod Status: {json.dumps(status, indent=2)}")

    if args.wait:
        print(f"[*] Waiting for pod '{args.scan_id}' to finish (max duration: {args.duration + 30}s)...")
        wait_res = wait_pod_completion(args.scan_id, timeout_sec=args.duration + 30)
        print(f"[+] Final Pod Result: {json.dumps(wait_res, indent=2)}")
        final_status = get_pod_status(args.scan_id)
        print(f"[+] Final Pod Status: {json.dumps(final_status, indent=2)}")

if __name__ == "__main__":
    main()
