"""
Structured JSON Logging for Deep Review Backend (Phase 3 - Task T3.13)

Formats all backend log records as structured JSON events:
- Standard fields: timestamp, level, logger, message
- Contextual fields: scan_id, project_id, engine, event, status, error_code, duration_ms
- Automatic integration with BackendSecretMaskingFilter to guarantee zero secrets in logs.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from backend.logging.logger import BackendSecretMaskingFilter

class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured JSON dictionaries."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp_iso = datetime.now(timezone.utc).isoformat()

        # Build base structured dictionary
        log_obj: Dict[str, Any] = {
            "timestamp": timestamp_iso,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }

        # Contextual attributes attached via extra={...}
        for attr in ["scan_id", "project_id", "engine", "event", "status", "error_code", "duration_ms", "user_id"]:
            if hasattr(record, attr):
                val = getattr(record, attr)
                if val is not None:
                    log_obj[attr] = val

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)

def setup_structured_logger(
    name: str = "deepreview_structured",
    level: int = logging.INFO
) -> Tuple[logging.Logger, BackendSecretMaskingFilter]:
    """Factory to create a logger with structured JSON formatting and secret masking."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())

    secret_filter = BackendSecretMaskingFilter()
    handler.addFilter(secret_filter)

    logger.addHandler(handler)
    return logger, secret_filter
