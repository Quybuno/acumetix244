import ssl
import time
import logging
import urllib.request
import urllib.error
from typing import Optional, Tuple

class AcunetixClient:
    """
    HTTP Client for Acunetix REST API running in loopback / shared pod network.
    Uses Insecure TLS context (T0.8) to handle Acunetix self-signed certificates.
    """
    def __init__(self, base_url: str = "https://localhost:3443", logger: Optional[logging.Logger] = None):
        self.base_url = base_url.rstrip("/")
        self.logger = logger or logging.getLogger("acunetix_client")
        
        # Configure TLS context for internal self-signed certificate
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE

    def probe_health(self) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Check if Acunetix backend is responding.
        Returns: (is_ready, http_status_code, error_message)
        """
        url = f"{self.base_url}/api/v1/info"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=3.0) as resp:
                code = resp.getcode()
                if code in [200, 204]:
                    return True, code, None
                return False, code, f"Unexpected status {code}"
        except urllib.error.HTTPError as e:
            # Acunetix returns 401/403/400 if service is up but unauthenticated
            if e.code in [400, 401, 403]:
                return True, e.code, None
            return False, e.code, str(e)
        except Exception as e:
            return False, None, str(e)

    def wait_for_ready(self, timeout_seconds: int = 60, poll_interval: float = 2.0) -> bool:
        """
        Repeatedly poll Acunetix API until ready or timeout is reached.
        Never hangs indefinitely.
        """
        start_time = time.time()
        self.logger.info(f"Checking Acunetix API readiness at {self.base_url} (timeout: {timeout_seconds}s)...")

        attempt = 0
        while True:
            attempt += 1
            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                self.logger.error(
                    f"Readiness check timed out after {round(elapsed, 1)}s ({attempt} attempts). "
                    f"Acuentix API at {self.base_url} failed to respond."
                )
                return False

            ready, code, err = self.probe_health()
            if ready:
                self.logger.info(
                    f"Acunetix API is READY at {self.base_url} (HTTP {code}, detected in {round(elapsed, 2)}s, attempt {attempt})."
                )
                return True

            self.logger.debug(
                f"Attempt {attempt}: Acunetix not ready yet ({err or code}). Elapsed: {round(elapsed, 1)}s. Retrying in {poll_interval}s..."
            )
            time.sleep(poll_interval)
