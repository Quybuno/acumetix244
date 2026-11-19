"""
HTTP Handler for ScanOptions Schemas API (Phase 3 - Task T3.2)
Provides REST endpoints:
- GET /api/v1/schemas/engines
- GET /api/v1/schemas/scan-options?engine=<engine>
"""

import json
from urllib.parse import urlparse, parse_qs
from typing import Tuple, Dict, Any, Optional
from backend.schemas.scan_options import (
    get_scan_options_schema,
    list_supported_engines
)

class SchemaApiHandler:
    """Dispatches schema-related HTTP API requests."""

    @staticmethod
    def handle_request(method: str, path: str) -> Tuple[int, Dict[str, str], bytes]:
        """
        Handle schema API endpoints.
        Returns: (http_status, headers_dict, response_bytes)
        """
        parsed_url = urlparse(path)
        route = parsed_url.path.rstrip("/")
        query_params = parse_qs(parsed_url.query)

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }

        if method == "OPTIONS":
            return 204, headers, b""

        if method != "GET":
            err_body = json.dumps({"error": f"Method {method} not allowed", "status": 405}).encode("utf-8")
            return 405, headers, err_body

        # Endpoint 1: GET /api/v1/schemas/engines
        if route in ["/api/v1/schemas/engines", "/api/v1/engines"]:
            engines = list_supported_engines()
            body = json.dumps({"status": "success", "engines": engines}, ensure_ascii=False).encode("utf-8")
            return 200, headers, body

        # Endpoint 2: GET /api/v1/schemas/scan-options
        if route == "/api/v1/schemas/scan-options":
            engine_param = query_params.get("engine", [None])[0]
            if not engine_param:
                err_body = json.dumps({
                    "error": "Missing required query parameter: 'engine'",
                    "status": 400,
                    "example": "/api/v1/schemas/scan-options?engine=acunetix"
                }, ensure_ascii=False).encode("utf-8")
                return 400, headers, err_body

            try:
                schema = get_scan_options_schema(engine_param)
                body = json.dumps({"status": "success", "schema": schema}, ensure_ascii=False).encode("utf-8")
                return 200, headers, body
            except ValueError as e:
                err_body = json.dumps({
                    "error": str(e),
                    "status": 400
                }, ensure_ascii=False).encode("utf-8")
                return 400, headers, err_body

        # Route not found
        err_body = json.dumps({
            "error": f"Route '{route}' not found",
            "status": 404
        }).encode("utf-8")
        return 404, headers, err_body
