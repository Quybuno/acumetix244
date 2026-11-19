#!/usr/bin/env python3
"""
Deep Review Acunetix Driver CLI
Main entry point for driving Acunetix automated scans in ephemeral pods.
"""
import sys
import json
import argparse
from pathlib import Path

# Support running directly or as module
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from driver.config import load_config
from driver.logger import setup_logger

def parse_args():
    parser = argparse.ArgumentParser(description="Deep Review Acunetix Scanner Driver")
    parser.add_argument("--scan-id", required=True, help="Scan identifier")
    parser.add_argument("--secrets-file", default=None, help="Path to credentials JSON file")
    parser.add_argument("--options-file", default=None, help="Path to scan options JSON file")
    parser.add_argument("--target-url", default=None, help="Target application URL")
    parser.add_argument("--webhook-url", default=None, help="Callback webhook URL for reporting")
    parser.add_argument("--acunetix-url", default=None, help="Acunetix API base URL")
    parser.add_argument("--inputs-dir", default=None, help="Directory containing input files (.lsr, openapi)")
    parser.add_argument("--log-file", default=None, help="Optional path to write log output")
    return parser.parse_args()

def main():
    args = parse_args()

    # 1. Load configuration
    try:
        config = load_config(
            scan_id=args.scan_id,
            target_url=args.target_url,
            webhook_url=args.webhook_url,
            secrets_file=args.secrets_file,
            options_file=args.options_file,
            inputs_dir=args.inputs_dir,
            acunetix_url=args.acunetix_url
        )
    except Exception as e:
        sys.stderr.write(f"FATAL: Configuration error: {e}\n")
        sys.exit(1)

    # 2. Setup structured logging with automatic secret scrubbing
    secret_strings = config.extract_secret_strings()
    logger = setup_logger(
        scan_id=config.scan_id,
        log_file=args.log_file,
        secrets_to_mask=secret_strings
    )

    logger.info("Initializing Acunetix Driver framework (Phase 2 - Task T2.1)")
    logger.info("Driver configuration loaded successfully.")

    # 3. Output masked configuration
    masked_config = config.to_masked_dict()
    logger.info(f"Active configuration (masked): {json.dumps(masked_config, indent=2)}")

    logger.info("T2.1: Driver skeleton, config parsing, and secret-masked structured logging verified.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
