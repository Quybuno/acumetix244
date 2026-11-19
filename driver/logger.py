import logging
import sys
import json
import re
from datetime import datetime, timezone
from pathlib import Path

# Sensitive key substrings that must always be masked
SENSITIVE_KEY_PATTERNS = [
    r"api[_-]?key",
    r"token",
    r"secret",
    r"pass(word)?",
    r"auth(orization)?",
    r"cookie",
    r"licen[sc]e",
    r"credential",
    r"private[_-]?key",
]

SENSITIVE_KEY_REGEX = re.compile("|".join(SENSITIVE_KEY_PATTERNS), re.IGNORECASE)

class SecretMaskingFilter(logging.Filter):
    """
    Filter that intercepts all log messages and scrubs any known secret strings.
    """
    def __init__(self, secrets_to_mask=None):
        super().__init__()
        self.secrets = set()
        if secrets_to_mask:
            self.add_secrets(secrets_to_mask)

    def add_secrets(self, secrets):
        for s in secrets:
            if s and isinstance(s, str) and len(s) > 3:
                self.secrets.add(s)

    def filter(self, record):
        if not isinstance(record.msg, str):
            record.msg = str(record.msg)
        for sec in self.secrets:
            if sec in record.msg:
                record.msg = record.msg.replace(sec, "[REDACTED]")
        return True

class StructuredFormatter(logging.Formatter):
    """
    Format logs as:
    [ISO-TIMESTAMP] [LEVEL] [scan_id=<scan_id>] <message>
    """
    def __init__(self, scan_id: str):
        super().__init__()
        self.scan_id = scan_id

    def format(self, record):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        lvl = record.levelname.ljust(5)
        return f"[{now}] [{lvl}] [scan_id={self.scan_id}] {record.getMessage()}"

def setup_logger(scan_id: str, log_file: str = None, secrets_to_mask: list = None) -> logging.Logger:
    """
    Initialize and return a structured logger tagged with scan_id and secret masking.
    """
    logger = logging.getLogger(f"driver.{scan_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    masking_filter = SecretMaskingFilter(secrets_to_mask)
    formatter = StructuredFormatter(scan_id)

    # Console Handler (stdout)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(masking_filter)
    logger.addHandler(stdout_handler)

    # Optional File Handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(masking_filter)
        logger.addHandler(file_handler)

    return logger

def mask_data(data, max_depth=10):
    """
    Recursively traverse dictionaries / lists and mask sensitive values.
    Preserves structural dicts/lists while replacing leaf secret values with [REDACTED].
    """
    if max_depth <= 0:
        return data

    if isinstance(data, dict):
        # Special handling for HTTP header dicts: {"name": "Authorization", "value": "..."}
        if "name" in data and "value" in data:
            header_name = str(data.get("name", ""))
            if SENSITIVE_KEY_REGEX.search(header_name):
                return {"name": header_name, "value": "[REDACTED]"}

        masked = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                masked[k] = mask_data(v, max_depth - 1)
            elif isinstance(k, str) and SENSITIVE_KEY_REGEX.search(k):
                masked[k] = "[REDACTED]"
            else:
                masked[k] = v
        return masked
    elif isinstance(data, list):
        return [mask_data(item, max_depth - 1) for item in data]
    return data
