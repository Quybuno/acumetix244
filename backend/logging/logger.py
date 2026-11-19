"""
Secret Masking Logging Filter for Deep Review Backend (Phase 3 - Task T3.4)
Ensures zero password or raw token leakage in backend logs.
"""

import logging
import re
from typing import Set, Tuple

class BackendSecretMaskingFilter(logging.Filter):
    def __init__(self, name: str = ""):
        super().__init__(name)
        self.sensitive_patterns: Set[str] = set()

    def add_secret(self, secret: str):
        """Register a sensitive string to be masked in all log outputs."""
        if secret and len(secret.strip()) >= 3:
            self.sensitive_patterns.add(secret.strip())

    def filter(self, record: logging.LogRecord) -> bool:
        # Pre-format message so arguments in record.args are converted to string
        if record.args:
            record.msg = record.getMessage()
            record.args = ()

        if not isinstance(record.msg, str):
            record.msg = str(record.msg)

        masked_msg = record.msg
        for secret in self.sensitive_patterns:
            if secret in masked_msg:
                masked_msg = masked_msg.replace(secret, "[REDACTED]")

        # Pattern-based masking for standard key-value assignments in logs
        masked_msg = re.sub(
            r'(password|token|secret|key)["\']?\s*[:=]\s*["\']?([^"\'\s,;]+)["\']?',
            r'\1="[REDACTED]"',
            masked_msg,
            flags=re.IGNORECASE
        )

        record.msg = masked_msg
        return True

def setup_backend_logger(name: str = "deepreview_backend", level: int = logging.INFO) -> Tuple[logging.Logger, BackendSecretMaskingFilter]:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-5s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ"
    )
    handler.setFormatter(formatter)
    
    secret_filter = BackendSecretMaskingFilter()
    handler.addFilter(secret_filter)
    logger.addHandler(handler)
    return logger, secret_filter
