import ssl
import time
import json
import re
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

    def start_scan(self, target_id: str, profile_id: Optional[str] = None) -> str:
        """
        Trigger an immediate scan for target_id using profile_id.
        Returns scan_id.
        """
        resolved_pid = resolve_profile_id(profile_id)
        scan_payload = {
            "target_id": target_id,
            "profile_id": resolved_pid,
            "schedule": {
                "disable": False,
                "start_date": None,
                "time_sensitive": False
            }
        }
        status, resp = self.request("/api/v1/scans", method="POST", data=scan_payload)
        if status not in [200, 201] or not isinstance(resp, dict) or "scan_id" not in resp:
            raise ValueError(f"Failed to trigger scan: HTTP {status}, response: {resp}")

        scan_id = resp["scan_id"]
        self.logger.info(f"Scan triggered successfully: scan_id={scan_id} profile_id={resolved_pid}")
        return scan_id

    def get_scan(self, scan_id: str) -> Dict[str, Any]:
        """
        Get scan status and details.
        """
        status, data = self.request(f"/api/v1/scans/{scan_id}")
        if status != 200 or not isinstance(data, dict):
            raise ValueError(f"Failed to get scan {scan_id}: HTTP {status}, response: {data}")
        return data

    def abort_scan(self, scan_id: str) -> bool:
        """
        Abort an active scan.
        """
        try:
            status, resp = self.request(f"/api/v1/scans/{scan_id}/abort", method="POST")
            if status in [200, 204, 409]:
                self.logger.info(f"Scan {scan_id} abort processed (HTTP {status}).")
                return True
            self.logger.warning(f"Unexpected status aborting scan {scan_id}: HTTP {status}")
            return False
        except Exception as e:
            self.logger.warning(f"Error while aborting scan {scan_id}: {e}")
            return False

    def delete_scan(self, scan_id: str) -> bool:
        """
        Delete a scan record.
        """
        try:
            status, _ = self.request(f"/api/v1/scans/{scan_id}", method="DELETE")
            return status in [200, 204]
        except Exception as e:
            self.logger.warning(f"Error deleting scan {scan_id}: {e}")
            return False

    def poll_scan(
        self,
        scan_id: str,
        timeout_seconds: int = 1800,
        poll_interval: float = 3.0
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Periodically poll scan status until completed, aborted, failed or timed out.
        Returns (final_status, scan_info).
        final_status in ["completed", "failed", "aborted", "timeout", "manual_intervention"].
        """
        start_time = time.monotonic()
        self.logger.info(f"Beginning polling for scan {scan_id} (timeout={timeout_seconds}s, interval={poll_interval}s)...")

        last_logged_status = None
        last_logged_prog = None

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > timeout_seconds:
                self.logger.error(
                    f"Scan {scan_id} exceeded maximum timeout of {timeout_seconds}s "
                    f"(elapsed: {elapsed:.1f}s). Aborting scan..."
                )
                self.abort_scan(scan_id)
                try:
                    scan_info = self.get_scan(scan_id)
                except Exception:
                    scan_info = {}
                return "timeout", scan_info

            scan_info = self.get_scan(scan_id)
            current_session = scan_info.get("current_session") or {}
            status = (current_session.get("status") or "").lower()
            progress = current_session.get("progress")
            manual_intervention = scan_info.get("manual_intervention", False)

            # Log when status or progress changes
            if status != last_logged_status or progress != last_logged_prog:
                self.logger.info(
                    f"Scan progress: status='{status}' progress={progress}% "
                    f"(elapsed: {elapsed:.1f}s)"
                )
                last_logged_status = status
                last_logged_prog = progress

            if manual_intervention:
                self.logger.warning(f"Scan {scan_id} flagged manual_intervention=True! Aborting scan...")
                self.abort_scan(scan_id)
                return "manual_intervention", scan_info

            if status == "completed":
                self.logger.info(f"Scan {scan_id} completed successfully in {elapsed:.1f}s.")
                return "completed", scan_info

            if status in ["failed", "abort", "aborted"]:
                self.logger.error(f"Scan {scan_id} finished with terminal status: '{status}'.")
                return status, scan_info

            time.sleep(poll_interval)

    def get_scan_statistics(self, scan_id: str, scan_session_id: str) -> Dict[str, Any]:
        """
        Fetch statistics object for a given scan session.
        GET /api/v1/scans/{scan_id}/results/{scan_session_id}/statistics
        """
        status, data = self.request(f"/api/v1/scans/{scan_id}/results/{scan_session_id}/statistics")
        if status != 200 or not isinstance(data, dict):
            self.logger.warning(f"Could not retrieve statistics for scan {scan_id} session {scan_session_id}: HTTP {status}")
            return {}
        return data

    def get_scan_vulnerabilities(
        self,
        scan_id: str,
        scan_session_id: str,
        page_size: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Fetch all vulnerabilities for a scan session with automatic pagination (Task T2.8).
        GET /api/v1/scans/{scan_id}/results/{scan_session_id}/vulnerabilities?l={page_size}
        """
        all_vulns = []
        visited_cursors = set()
        next_cursor = None

        while True:
            endpoint = f"/api/v1/scans/{scan_id}/results/{scan_session_id}/vulnerabilities?l={page_size}"
            if next_cursor:
                endpoint += f"&c={next_cursor}"

            status, data = self.request(endpoint)
            if status != 200 or not isinstance(data, dict):
                self.logger.warning(f"Error fetching vulnerabilities: HTTP {status}, resp: {data}")
                break

            vulns = data.get("vulnerabilities", [])
            all_vulns.extend(vulns)

            pagination = data.get("pagination", {})
            total_count = pagination.get("count", len(all_vulns))
            cursors = pagination.get("cursors", [])

            self.logger.info(
                f"Fetched {len(vulns)} vulnerabilities (cumulative: {len(all_vulns)}/{total_count})."
            )

            # Advance cursor
            try:
                curr_idx = cursors.index(next_cursor)
                if curr_idx + 1 < len(cursors) and cursors[curr_idx + 1] is not None:
                    next_cursor = cursors[curr_idx + 1]
                    if next_cursor in visited_cursors:
                        break
                    visited_cursors.add(next_cursor)
                else:
                    break
            except (ValueError, IndexError):
                break

        return all_vulns

    def check_post_scan_health(
        self,
        scan_id: str,
        scan_info: Dict[str, Any],
        statistics: Optional[Dict[str, Any]] = None,
        scan_options: Optional[Dict[str, Any]] = None,
        target_config: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Perform post-scan health and business integrity validation (Task T2.7):
        1. Check MANUAL_INTERVENTION:
           If scan_info.get("manual_intervention") is True or messages indicate human action needed.
        2. Check LOGIN_FAILED:
           If login was configured (automatic credentials or LSR sequence) and
           statistics messages/events indicate authentication failure or preflight connection refusal.
        3. Check LOW_COVERAGE:
           If discovered crawler locations is below threshold (default < 3 or min_locations)
           or crawler could not connect to target.

        Returns (is_healthy, error_code, health_details).
        If is_healthy is False, error_code is one of:
          - "MANUAL_INTERVENTION"
          - "LOGIN_FAILED"
          - "LOW_COVERAGE"
        """
        scan_options = scan_options or {}
        target_config = target_config or {}
        stats = statistics or {}

        main_stats = stats.get("scanning_app", {}).get("wvs", {}).get("main", {})
        web_scan_status = main_stats.get("web_scan_status", {})
        messages = main_stats.get("messages", [])

        locations = web_scan_status.get("locations", 0)
        request_count = web_scan_status.get("request_count", 0)
        manual_int = scan_info.get("manual_intervention", False)

        details = {
            "locations": locations,
            "request_count": request_count,
            "manual_intervention": manual_int,
            "messages_count": len(messages),
            "reasons": []
        }

        # 1. Check MANUAL_INTERVENTION
        if manual_int:
            details["reasons"].append("Acunetix scan flagged manual_intervention=True")
            self.logger.warning(f"Scan {scan_id} failed health check: MANUAL_INTERVENTION detected.")
            return False, "MANUAL_INTERVENTION", details

        for m in messages:
            kind = (m.get("kind") or "").lower()
            data = (m.get("data") or "").lower()
            if "manual_intervention" in kind or "captcha" in data or "interaction" in data:
                details["reasons"].append(f"Message indicates human intervention needed: {data or kind}")
                self.logger.warning(f"Scan {scan_id} failed health check: MANUAL_INTERVENTION detected in messages.")
                return False, "MANUAL_INTERVENTION", details

        # 2. Check LOGIN_FAILED
        login_conf = target_config.get("login", {})
        login_kind = login_conf.get("kind") or "none"
        login_configured = (
            login_kind in ["automatic", "sequence"] or
            bool(scan_options.get("target_credentials"))
        )

        if login_configured:
            for m in messages:
                kind = (m.get("kind") or "").lower()
                data = (m.get("data") or "").lower()
                if kind in ["login_failed", "autologin_failed", "lsr_failed", "login_sequence_failed", "login_form_not_found"]:
                    details["reasons"].append(f"Login failure message (kind='{kind}'): {data}")
                    self.logger.warning(f"Scan {scan_id} failed health check: LOGIN_FAILED detected (kind='{kind}').")
                    return False, "LOGIN_FAILED", details
                if re.search(r"(?i)(login\s+failed|failed\s+to\s+log\s*in|unable\s+to\s+authenticate|invalid\s+credentials|authentication\s+failed)", data):
                    details["reasons"].append(f"Login failure detected in text: {data}")
                    self.logger.warning(f"Scan {scan_id} failed health check: LOGIN_FAILED detected in message text.")
                    return False, "LOGIN_FAILED", details

        # 3. Check LOW_COVERAGE
        min_locations = scan_options.get("min_locations", 3)
        connection_failed = any("could not connect" in (m.get("data") or "").lower() for m in messages)
        if connection_failed:
            details["reasons"].append("Scanner preflight could not connect to target host")
            self.logger.warning(f"Scan {scan_id} failed health check: LOW_COVERAGE (preflight connection failed).")
            return False, "LOW_COVERAGE", details

        if locations < min_locations:
            details["reasons"].append(f"Discovered locations ({locations}) is below minimum threshold ({min_locations})")
            self.logger.warning(f"Scan {scan_id} failed health check: LOW_COVERAGE (locations={locations} < {min_locations}).")
            return False, "LOW_COVERAGE", details

        self.logger.info(f"Scan {scan_id} passed post-scan health check (locations={locations}, requests={request_count}).")
        return True, None, details
