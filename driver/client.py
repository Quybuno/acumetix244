import ssl
import time
import json
import hashlib
import logging
import urllib.request
import urllib.error
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path

PROFILES = {
    "full": "11111111-1111-1111-1111-111111111111",
    "full_scan": "11111111-1111-1111-1111-111111111111",
    "high_risk": "11111111-1111-1111-1111-111111111112",
    "critical": "11111111-1111-1111-1111-111111111112",
    "crawl_only": "11111111-1111-1111-1111-111111111117",
    "sqli": "11111111-1111-1111-1111-111111111113",
    "xss": "11111111-1111-1111-1111-111111111116",
    "owasp_top_10": "11111111-1111-1111-1111-111111111129",
}

def resolve_profile_id(profile_name: Optional[str]) -> str:
    if not profile_name:
        return PROFILES["full"]
    if len(profile_name) == 36 and "-" in profile_name:
        return profile_name
    normalized = profile_name.lower().replace(" ", "_")
    return PROFILES.get(normalized, PROFILES["full"])

class AcunetixClient:
    """
    HTTP Client for Acunetix REST & GraphQL APIs running in loopback / shared pod network.
    Handles Insecure TLS (T0.8), Authentication (T0.2 - T0.4), and Target Configuration (T2.4).
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
        if api_key:
            self.logger.info("Validating provided API key against Acunetix API...")
            self.api_key = api_key
            if self.check_auth():
                self.logger.info("Provided API key is valid and authenticated.")
                return self.api_key
            self.logger.warning("Provided API key failed authentication check. Falling back to admin login if available...")

        admin_pass = password or "Acunetix@123"
        self.api_key = self.login_and_generate_api_key(email=email, password=admin_pass)
        
        if not self.check_auth():
            raise ValueError("Generated API key failed validation check on /api/v1/targets")

        self.logger.info("Acunetix API authentication verified successfully.")
        return self.api_key

    def create_target(self, address: str, description: str, criticality: int = 10) -> str:
        """
        Create a new target in Acunetix. (Step 2 in API Sequence).
        Returns target_id.
        """
        payload = {
            "address": address,
            "description": description,
            "type": "default",
            "criticality": criticality
        }
        status, resp = self.request("/api/v1/targets", method="POST", data=payload)
        if status != 201 or not isinstance(resp, dict) or "target_id" not in resp:
            raise ValueError(f"Failed to create target: HTTP {status}, response: {resp}")
        target_id = resp["target_id"]
        self.logger.info(f"Target created successfully: target_id={target_id} address='{address}'")
        return target_id

    def configure_target(
        self,
        target_id: str,
        scan_options: Dict[str, Any],
        secrets: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Configure target settings: speed, scope, excluded paths, custom headers, login credentials.
        (Step 3 in API Sequence).
        Returns the patched configuration verified from the server.
        """
        # Format custom headers
        headers_list = []
        raw_headers = secrets.get("custom_headers") or scan_options.get("custom_headers", [])
        if isinstance(raw_headers, list):
            for h in raw_headers:
                if isinstance(h, dict) and "name" in h and "value" in h:
                    headers_list.append(f"{h['name']}: {h['value']}")
                elif isinstance(h, str) and ":" in h:
                    headers_list.append(h)

        # Format login credentials
        login_cfg = {"kind": "none"}
        target_creds = secrets.get("target_credentials")
        if target_creds and isinstance(target_creds, dict) and target_creds.get("username"):
            login_cfg = {
                "kind": "automatic",
                "credentials": {
                    "enabled": True,
                    "username": target_creds["username"],
                    "password": target_creds.get("password", "")
                }
            }

        # Excluded paths
        excluded_paths = scan_options.get("excluded_paths", [])

        # Crawler limits & speed
        scan_speed = scan_options.get("scan_speed", "fast")
        limit_crawler_scope = scan_options.get("limit_crawler_scope", True)
        user_agent = scan_options.get("user_agent", "Mozilla/5.0 DeepReview-AcunetixDriver/1.0")

        config_payload = {
            "scan_speed": scan_speed,
            "limit_crawler_scope": limit_crawler_scope,
            "user_agent": user_agent,
            "excluded_paths": excluded_paths,
            "login": login_cfg,
            "custom_headers": headers_list
        }

        # Profile ID
        profile_name = scan_options.get("profile")
        if profile_name:
            config_payload["default_scanning_profile_id"] = resolve_profile_id(profile_name)

        self.logger.info(f"Patching configuration for target_id={target_id}...")
        status, resp = self.request(f"/api/v1/targets/{target_id}/configuration", method="PATCH", data=config_payload)
        if status != 204:
            raise ValueError(f"Failed to patch configuration for target {target_id}: HTTP {status}, response: {resp}")

        # Fetch and verify configuration from Acunetix
        status, current_config = self.request(f"/api/v1/targets/{target_id}/configuration", method="GET")
        if status != 200 or not isinstance(current_config, dict):
            raise ValueError(f"Failed to verify configuration for target {target_id}: HTTP {status}")

        self.logger.info(
            f"Target {target_id} configuration verified: speed='{current_config.get('scan_speed')}' "
            f"excluded_paths={len(current_config.get('excluded_paths', []))} "
            f"headers={len(current_config.get('custom_headers', []))} "
            f"login_kind='{current_config.get('login', {}).get('kind')}'"
        )
        return current_config

    def upload_file_stream(self, init_endpoint: str, file_path: Path, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute Acunetix two-step file upload:
        Step 1: POST init_endpoint with {"name": filename, "size": size} -> returns upload_url
        Step 2: POST upload_url with raw bytes, Content-Range, Content-Disposition -> returns 201/204
        """
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File to upload not found: {file_path}")

        file_bytes = p.read_bytes()
        file_len = len(file_bytes)
        fname = filename or p.name

        # Step 1: Request upload URL
        status, init_resp = self.request(init_endpoint, method="POST", data={"name": fname, "size": file_len})
        if status not in [200, 201] or not isinstance(init_resp, dict) or "upload_url" not in init_resp:
            raise ValueError(f"Upload initialization failed for {fname}: HTTP {status}, response: {init_resp}")

        upload_rel_url = init_resp["upload_url"]
        upload_full_url = f"{self.base_url}{upload_rel_url}"

        # Step 2: Upload raw stream with Content-Range & Content-Disposition
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Range": f"bytes 0-{file_len - 1}/{file_len}",
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Auth": self.api_key
        }
        req = urllib.request.Request(upload_full_url, data=file_bytes, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=30.0) as resp:
                up_status = resp.getcode()
                if up_status not in [200, 201, 202, 204]:
                    raise ValueError(f"Upload failed for {fname}: HTTP {up_status}")
        except urllib.error.HTTPError as e:
            raise ValueError(f"Upload stream error for {fname}: HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")

        self.logger.info(f"File '{fname}' ({file_len} bytes) uploaded successfully to {upload_rel_url}.")
        return init_resp

    def import_api_definition(self, target_id: str, file_path: Path) -> Dict[str, Any]:
        """
        Upload API definition (OpenAPI/Swagger/Postman/HAR/XML) to target configuration imports.
        """
        init_endpoint = f"/api/v1/targets/{target_id}/configuration/imports"
        res = self.upload_file_stream(init_endpoint, file_path)
        return res

    def import_login_sequence(self, target_id: str, file_path: Path) -> Dict[str, Any]:
        """
        Upload Login Sequence (.lsr) to target configuration login_sequence.
        Also activates sequence login mode on target configuration.
        """
        init_endpoint = f"/api/v1/targets/{target_id}/configuration/login_sequence"
        res = self.upload_file_stream(init_endpoint, file_path)
        self.request(f"/api/v1/targets/{target_id}/configuration", method="PATCH", data={"login": {"kind": "sequence"}})
        self.logger.info(f"Target {target_id} login mode set to 'sequence' from {file_path.name}.")
        return res

    def import_inputs_from_directory(self, target_id: str, inputs_dir: Path) -> List[Dict[str, Any]]:
        """
        Scan directory and import all supported input files (.lsr, .json, .yaml, .yml, .xml, .har, .saz).
        """
        inp_path = Path(inputs_dir)
        if not inp_path.exists() or not inp_path.is_dir():
            self.logger.info(f"Inputs directory '{inputs_dir}' does not exist or is empty. Skipping file import.")
            return []

        imported_files = []
        for file in sorted(inp_path.iterdir()):
            if not file.is_file():
                continue

            fname_lower = file.name.lower()
            if fname_lower.endswith(".lsr"):
                self.logger.info(f"Found Login Sequence file: {file.name}. Uploading...")
                res = self.import_login_sequence(target_id, file)
                imported_files.append({"type": "login_sequence", "name": file.name, "result": res})
            elif any(fname_lower.endswith(ext) for ext in [".json", ".yaml", ".yml", ".xml", ".har", ".saz"]):
                # Skip options.json if present
                if fname_lower == "options.json":
                    continue
                self.logger.info(f"Found API/import definition file: {file.name}. Uploading...")
                res = self.import_api_definition(target_id, file)
                imported_files.append({"type": "api_import", "name": file.name, "result": res})

        # Verify imported files on Acunetix
        status, imports_list = self.request(f"/api/v1/targets/{target_id}/configuration/imports")
        if status == 200 and isinstance(imports_list, dict):
            files = imports_list.get("files", [])
            self.logger.info(f"Target {target_id} now has {len(files)} imported file(s) registered in Acunetix.")

        return imported_files

    def delete_target(self, target_id: str) -> bool:
        """
        Delete target from Acunetix instance.
        """
        self.logger.info(f"Deleting target {target_id}...")
        status, _ = self.request(f"/api/v1/targets/{target_id}", method="DELETE")
        return status in [200, 204]
