import time
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

class WebhookSender:
    """
    Handles robust webhook delivery with token authentication, retries, and backoff (Task T2.10).
    """
    def __init__(
        self,
        webhook_url: str,
        webhook_token: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 10.0
    ):
        self.webhook_url = webhook_url
        self.webhook_token = webhook_token
        self.logger = logger or logging.getLogger("webhook")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout

    def send_results(self, payload: Dict[str, Any]) -> bool:
        """
        Send scan results payload to webhook_url with retry mechanism.
        Returns True if delivered (HTTP 2xx), False otherwise.
        """
        if not self.webhook_url:
            self.logger.warning("No webhook_url provided. Skipping callback.")
            return True

        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DeepReview-Acunetix-Driver/1.0"
        }
        if self.webhook_token:
            headers["X-Webhook-Token"] = self.webhook_token
            headers["Authorization"] = f"Bearer {self.webhook_token}"

        for attempt in range(1, self.max_retries + 1):
            self.logger.info(
                f"Dispatching scan results to webhook {self.webhook_url} "
                f"(attempt {attempt}/{self.max_retries}, payload size: {len(body)} bytes)..."
            )
            req = urllib.request.Request(
                self.webhook_url,
                data=body,
                headers=headers,
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.getcode()
                    if 200 <= status < 300:
                        self.logger.info(
                            f"Webhook delivered successfully to {self.webhook_url} "
                            f"(HTTP {status}, attempt {attempt})."
                        )
                        return True
                    else:
                        self.logger.warning(
                            f"Webhook returned non-2xx status: HTTP {status} (attempt {attempt})."
                        )
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                self.logger.warning(
                    f"Webhook HTTP error: {e.code} {e.reason} (attempt {attempt}): {err_body[:200]}"
                )
            except Exception as e:
                self.logger.warning(
                    f"Webhook network error on attempt {attempt}: {e}"
                )

            if attempt < self.max_retries:
                delay = self.retry_delay * attempt
                self.logger.info(f"Retrying webhook in {delay:.1f}s...")
                time.sleep(delay)

        self.logger.error(
            f"FATAL: Webhook dispatch to {self.webhook_url} failed after {self.max_retries} attempts."
        )
        return False
