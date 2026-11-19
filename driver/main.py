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
from driver.webhook import WebhookSender

EXIT_CODE_ACUNETIX_NOT_READY = 10
EXIT_CODE_AUTH_FAILED = 11
EXIT_CODE_CONFIG_FAILED = 12
EXIT_CODE_IMPORT_FAILED = 13
EXIT_CODE_SCAN_TIMEOUT = 14
EXIT_CODE_SCAN_FAILED = 15
EXIT_CODE_WEBHOOK_FAILED = 50

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
    parser.add_argument("--scan-timeout", type=int, default=1800, help="Maximum scan duration in seconds before aborting")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="Polling interval in seconds")
    parser.add_argument("--clean-target", action="store_true", default=True, help="Delete target after scan (default: True)")
    parser.add_argument("--keep-target", action="store_true", help="Keep target on Acunetix after scan (default: False, target is deleted)")
    parser.add_argument("--no-scan", action="store_true", help="Skip scan trigger (dry-run / setup only)")
    parser.add_argument("--webhook-retries", type=int, default=3, help="Max retry attempts for webhook delivery")
    parser.add_argument("--webhook-retry-delay", type=float, default=1.0, help="Initial retry delay in seconds")
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

    # 8. Start Scan & Poll Status (Task T2.6)
    scan_id = None
    scan_result_payload = None
    if not args.no_scan:
        try:
            profile = config.scan_options.get("profile")
            scan_id = client.start_scan(target_id=target_id, profile_id=profile)
            logger.info(f"Scan triggered successfully with ID {scan_id}. Polling until completion...")

            final_status, scan_info = client.poll_scan(
                scan_id=scan_id,
                timeout_seconds=args.scan_timeout,
                poll_interval=args.poll_interval
            )

            if final_status == "timeout":
                logger.error(f"FATAL: Scan {scan_id} exceeded maximum timeout ({args.scan_timeout}s).")
                if target_id and args.clean_target:
                    try:
                        client.delete_target(target_id)
                    except Exception:
                        pass
                sys.exit(EXIT_CODE_SCAN_TIMEOUT)

            if final_status in ["failed", "abort", "aborted"]:
                logger.error(f"FATAL: Scan {scan_id} finished with failure status '{final_status}'.")
                if target_id and args.clean_target:
                    try:
                        client.delete_target(target_id)
                    except Exception:
                        pass
                sys.exit(EXIT_CODE_SCAN_FAILED)

            logger.info(f"Scan {scan_id} finished polling with status '{final_status}'.")

            # 9. Post-scan Business Health Check (Task T2.7)
            scan_session_id = (scan_info.get("current_session") or {}).get("scan_session_id")
            statistics = {}
            if scan_session_id:
                statistics = client.get_scan_statistics(scan_id=scan_id, scan_session_id=scan_session_id)

            is_healthy, error_code, health_details = client.check_post_scan_health(
                scan_id=scan_id,
                scan_info=scan_info,
                statistics=statistics,
                scan_options=config.scan_options,
                target_config=current_config
            )

            if not is_healthy:
                logger.warning(
                    f"Post-scan verification REJECTED Acunetix 'completed' status! "
                    f"Scan marked as FAILED with error_code='{error_code}'. "
                    f"Reasons: {health_details.get('reasons')}"
                )
            else:
                logger.info(
                    f"Post-scan verification PASSED: Scan completed with adequate coverage "
                    f"({health_details.get('locations')} locations discovered) and valid authentication."
                )

            # 10. Fetch All Vulnerabilities (with pagination) & Statistics (Task T2.8)
            vulnerabilities = []
            if scan_session_id:
                vulnerabilities = client.get_scan_vulnerabilities(
                    scan_id=scan_id,
                    scan_session_id=scan_session_id,
                    page_size=100
                )
                logger.info(
                    f"Successfully collected {len(vulnerabilities)} vulnerabilities and scan statistics "
                    f"for scan {scan_id}."
                )

            severity_counts = (scan_info.get("current_session") or {}).get("severity_counts") or {}
            scan_result_payload = {
                "scan_id": config.scan_id,
                "acunetix_scan_id": scan_id,
                "session_id": scan_session_id,
                "status": "COMPLETED" if is_healthy else "FAILED",
                "error_code": error_code,
                "is_healthy": is_healthy,
                "health_details": health_details,
                "severity_counts": severity_counts,
                "vulnerabilities_count": len(vulnerabilities),
                "vulnerabilities": vulnerabilities,
                "statistics": statistics
            }
            logger.info(
                f"Scan payload compiled: status='{scan_result_payload['status']}' "
                f"vulns={len(vulnerabilities)} locations={health_details.get('locations')}."
            )

            # 11. Cleanup Target & Associated Scan Artifacts (Task T2.9)
            if not args.keep_target and target_id:
                logger.info(f"Cleaning up target {target_id} before webhook callback (Task T2.9)...")
                cleanup_ok = client.delete_target(target_id)
                if cleanup_ok:
                    logger.info(f"Target {target_id} and all associated scan data deleted successfully from Acunetix.")
                    target_id = None
                else:
                    logger.warning(f"Failed to cleanly delete target {target_id} from Acunetix.")

        except Exception as e:
            logger.error(f"FATAL: Scan execution failed: {e}")
            if target_id and not args.keep_target:
                try:
                    client.delete_target(target_id)
                except Exception:
                    pass
            sys.exit(EXIT_CODE_SCAN_FAILED)

    if not args.keep_target and target_id:
        logger.info(f"Cleaning up target {target_id}...")
        client.delete_target(target_id)
        logger.info("Target cleaned up successfully.")

    # 12. Dispatch Results to Webhook (Task T2.10)
    webhook_url = config.webhook_url or args.webhook_url
    webhook_token = config.get_webhook_token()
    if webhook_url and scan_result_payload:
        sender = WebhookSender(
            webhook_url=webhook_url,
            webhook_token=webhook_token,
            logger=logger,
            max_retries=args.webhook_retries,
            retry_delay=args.webhook_retry_delay
        )
        delivered = sender.send_results(scan_result_payload)
        if not delivered:
            logger.error(
                f"FATAL: Webhook delivery failed after {args.webhook_retries} retry attempts. "
                f"Exiting with code 50 (CALLBACK_LOST)."
            )
            sys.exit(EXIT_CODE_WEBHOOK_FAILED)
    elif not webhook_url:
        logger.info("No webhook_url configured. Scan execution finished without callback.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
