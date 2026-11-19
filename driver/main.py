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
from driver.client import AcunetixClient

EXIT_CODE_ACUNETIX_NOT_READY = 10
EXIT_CODE_AUTH_FAILED = 11
EXIT_CODE_CONFIG_FAILED = 12
EXIT_CODE_IMPORT_FAILED = 13

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
    parser.add_argument("--ready-timeout", type=int, default=60, help="Timeout in seconds waiting for Acunetix API readiness")
    parser.add_argument("--clean-target", action="store_true", help="Delete target immediately after configuration (for testing/dry-run)")
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

    # 4. Wait for Acunetix API readiness (Task T2.2)
    client = AcunetixClient(base_url=config.acunetix_url, logger=logger)
    if not client.wait_for_ready(timeout_seconds=args.ready_timeout, poll_interval=2.0):
        logger.error(f"FATAL: Acunetix API failed to become ready within {args.ready_timeout}s.")
        sys.exit(EXIT_CODE_ACUNETIX_NOT_READY)

    logger.info("Acunetix API readiness check passed successfully.")

    # 5. Initialize instance & obtain API authentication (Task T2.3)
    admin_email, admin_password = config.get_admin_credentials()
    try:
        api_key = client.authenticate(
            api_key=config.get_api_key(),
            email=admin_email,
            password=admin_password
        )
        # Register new api_key in logger mask filter
        for handler in logger.handlers:
            for flt in handler.filters:
                if hasattr(flt, "add_secrets"):
                    flt.add_secrets([api_key])
        logger.info("Instance authentication verified. Ready to execute target configuration.")
    except Exception as e:
        logger.error(f"FATAL: Authentication initialization failed: {e}")
        sys.exit(EXIT_CODE_AUTH_FAILED)

    # 6. Create Target & Apply ScanOptions Configuration (Task T2.4)
    target_id = None
    try:
        target_id = client.create_target(
            address=config.target_url,
            description=f"Deep Review Scan - {config.scan_id}"
        )
        current_config = client.configure_target(
            target_id=target_id,
            scan_options=config.scan_options,
            secrets=config.secrets
        )
        logger.info(
            f"Target {target_id} successfully configured according to ScanOptions "
            f"(profile='{config.scan_options.get('profile')}', speed='{current_config.get('scan_speed')}')."
        )
    except Exception as e:
        logger.error(f"FATAL: Target creation/configuration failed: {e}")
        if target_id:
            try:
                client.delete_target(target_id)
            except Exception:
                pass
        sys.exit(EXIT_CODE_CONFIG_FAILED)

    # 7. Import Input Files (OpenAPI definitions, LSR login sequence) (Task T2.5)
    if config.inputs_dir and config.inputs_dir.exists():
        try:
            imported = client.import_inputs_from_directory(target_id, config.inputs_dir)
            logger.info(f"Successfully processed {len(imported)} input file(s) for target {target_id}.")
        except Exception as e:
            logger.error(f"FATAL: Importing input files failed: {e}")
            if target_id:
                try:
                    client.delete_target(target_id)
                except Exception:
                    pass
            sys.exit(EXIT_CODE_IMPORT_FAILED)

    if args.clean_target and target_id:
        logger.info(f"Cleaning up target {target_id} (--clean-target set)...")
        client.delete_target(target_id)
        logger.info("Target cleaned up successfully.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
