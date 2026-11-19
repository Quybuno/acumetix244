"""
HTTP API Handler for Scans Management (Phase 3 - Task T3.3)
Implements:
- POST /api/v1/scans
"""

import json
from urllib.parse import urlparse
from typing import Tuple, Dict, Any, Optional
from backend.services.scan_service import ScanService, ConcurrencyLimitError
from backend.validation.scan_validator import ValidationError

class ScanApiHandler:
    def __init__(self, scan_service: ScanService):
        self.scan_service = scan_service

    def handle_request(
        self,
        method: str,
        path: str,
        body_bytes: bytes,
        headers_in: Optional[Dict[str, str]] = None
    ) -> Tuple[int, Dict[str, str], bytes]:
        parsed_url = urlparse(path)
        route = parsed_url.path.rstrip("/")

        headers_out = {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }

        if method == "OPTIONS":
            return 204, headers_out, b""

        if route == "/api/v1/scans":
            if method != "POST":
                err_body = json.dumps({"error": f"Method {method} not allowed", "status": 405}).encode("utf-8")
                return 405, headers_out, err_body

            # Parse JSON body
            try:
                payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception as e:
                err_body = json.dumps({
                    "error": f"Malformed JSON request body: {e}",
                    "status": 400
                }).encode("utf-8")
                return 400, headers_out, err_body

            engine = payload.get("engine")
            project_id = payload.get("project_id")
            created_by = payload.get("created_by")
            scan_options = payload.get("scan_options", {})
            uploaded_files = payload.get("files", {})

            try:
                res = self.scan_service.create_scan(
                    engine=engine,
                    project_id=project_id,
                    created_by=created_by,
                    scan_options=scan_options,
                    uploaded_files=uploaded_files
                )
                body = json.dumps(res, ensure_ascii=False).encode("utf-8")
                return 201, headers_out, body
            except ValidationError as e:
                err_body = json.dumps({
                    "error": e.message,
                    "status": e.status_code
                }, ensure_ascii=False).encode("utf-8")
                return e.status_code, headers_out, err_body
            except ConcurrencyLimitError as e:
                err_body = json.dumps({
                    "error": e.message,
                    "error_code": "CONCURRENCY_LIMIT_EXCEEDED",
                    "status": e.status_code
                }, ensure_ascii=False).encode("utf-8")
                return e.status_code, headers_out, err_body
            except Exception as e:
                err_body = json.dumps({
                    "error": f"Internal server error: {e}",
                    "status": 500
                }).encode("utf-8")
                return 500, headers_out, err_body

        # Route not found
        err_body = json.dumps({"error": f"Route '{route}' not found", "status": 404}).encode("utf-8")
        return 404, headers_out, err_body
