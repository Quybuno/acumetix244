import ssl
import time
import json
import hashlib
import logging
import urllib.request
import urllib.error
from typing import Optional, Tuple, Dict, Any

class AcunetixClient:
    """
    HTTP Client for Acunetix REST & GraphQL APIs running in loopback / shared pod network.
    Handles Insecure TLS (T0.8) and Authentication (T0.2 - T0.4).
    """
    def __init__(
        self,
        base_url: str = "https://localhost:3443",
        api_key: Optional[str] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.logger = logger or logging.getLogger("acunetix_client")
        
        # Configure TLS context for internal self-signed certificate (T0.8)
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
            if e.code in [400, 401, 403]:
                return True, e.code, None
            return False, e.code, str(e)
        except Exception as e:
            return False, None, str(e)

    def wait_for_ready(self, timeout_seconds: int = 60, poll_interval: float = 2.0) -> bool:
        """
        Repeatedly poll Acunetix API until ready or timeout is reached.
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

    def request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None,
        cookie: Optional[str] = None
    ) -> Tuple[int, Any]:
        """
        Send HTTP request to Acunetix API with JSON payload and X-Auth header.
        Returns: (http_status_code, response_body_parsed_json_or_text)
        """
        url = f"{self.base_url}{endpoint}" if endpoint.startswith("/") else f"{self.base_url}/{endpoint}"
        body_bytes = None
        if data is not None:
            body_bytes = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(url, data=body_bytes, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        token_to_use = auth_token or self.api_key
        if token_to_use:
            req.add_header("X-Auth", token_to_use)
        if cookie:
            req.add_header("Cookie", cookie)

        try:
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=15.0) as resp:
                status = resp.getcode()
                raw_body = resp.read().decode("utf-8")
                if not raw_body:
                    return status, None
                try:
                    return status, json.loads(raw_body)
                except Exception:
                    return status, raw_body
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            try:
                parsed_err = json.loads(err_body)
            except Exception:
                parsed_err = err_body
            return e.code, parsed_err

    def check_auth(self) -> bool:
        """
        Verify current authentication token by querying authenticated endpoint GET /api/v1/targets.
        """
        if not self.api_key:
            return False
        status, _ = self.request("/api/v1/targets?l=1", method="GET")
        return status == 200

    def login_and_generate_api_key(
        self,
        email: str = "admin@acunetix.com",
        password: str = "Acunetix@123"
    ) -> str:
        """
        Perform login (POST /api/v1/me/login) with SHA-256 hashed password,
        then execute GraphQL mutation generateApiKey to obtain an API key (T0.2 - T0.4).
        """
        self.logger.info(f"Authenticating via login endpoint as '{email}'...")
        sha256_pwd = hashlib.sha256(password.encode("utf-8")).hexdigest()
        login_payload = {
            "email": email,
            "password": sha256_pwd,
            "remember_me": False
        }

        # Step 1: POST /api/v1/me/login
        url = f"{self.base_url}/api/v1/me/login"
        body_bytes = json.dumps(login_payload).encode("utf-8")
        req = urllib.request.Request(url, data=body_bytes, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=15.0) as resp:
                status = resp.getcode()
                session_token = resp.headers.get("X-Auth")
                if not session_token:
                    cookie_header = resp.headers.get("Set-Cookie", "")
                    for part in cookie_header.split(";"):
                        if "ui_session=" in part:
                            session_token = part.split("ui_session=")[1].strip()
                            break

                if status not in [200, 204] or not session_token:
                    raise ValueError(f"Login failed: status {status}, no session token returned")
        except urllib.error.HTTPError as e:
            raise ValueError(f"Login request failed with HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")

        self.logger.info("Login successful. Requesting permanent API key via GraphQL mutation...")

        # Step 2: POST /graphql/ with session token and ui_session cookie to generate API key
        gql_payload = {"query": "mutation { generateApiKey }"}
        status, gql_resp = self.request(
            "/graphql/",
            method="POST",
            data=gql_payload,
            auth_token=session_token,
            cookie=f"ui_session={session_token}"
        )
        if status != 200 or not isinstance(gql_resp, dict) or "data" not in gql_resp:
            raise ValueError(f"GraphQL generateApiKey failed: status {status}, response: {gql_resp}")

        api_key = gql_resp.get("data", {}).get("generateApiKey")
        if not api_key:
            raise ValueError(f"Failed to extract generateApiKey from response: {gql_resp}")

        self.logger.info("API key generated and retrieved successfully.")
        return api_key

    def authenticate(
        self,
        api_key: Optional[str] = None,
        email: str = "admin@acunetix.com",
        password: Optional[str] = None
    ) -> str:
        """
        Authenticate with Acunetix instance using either provided API key or admin login.
        """
        # Option A: API key is directly provided
        if api_key:
            self.logger.info("Validating provided API key against Acunetix API...")
            self.api_key = api_key
            if self.check_auth():
                self.logger.info("Provided API key is valid and authenticated.")
                return self.api_key
            self.logger.warning("Provided API key failed authentication check. Falling back to admin login if available...")

        # Option B: Fallback to admin login + GraphQL key generation
        admin_pass = password or "Acunetix@123"
        self.api_key = self.login_and_generate_api_key(email=email, password=admin_pass)
        
        # Verify generated key
        if not self.check_auth():
            raise ValueError("Generated API key failed validation check on /api/v1/targets")

        self.logger.info("Acunetix API authentication verified successfully.")
        return self.api_key
