"""
HTTP API Handler for Webhook Endpoint (Phase 3 - Task T3.6)
Implements:
- POST /api/v1/webhook
"""

import json
from urllib.parse import urlparse
from typing import Tuple, Dict, Any, Optional
from backend.services.webhook_service import WebhookService, WebhookError

class WebhookApiHandler:
    def __init__(self, webhook_service: WebhookService):
        self.webhook_service = webhook_service

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
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Webhook-Token"
        }

        if method == "OPTIONS":
            return 204, headers_out, b""

        if route == "/api/v1/webhook":
            if method != "POST":
                err_body = json.dumps({"error": f"Method {method} not allowed", "status": 405}).encode("utf-8")
                return 405, headers_out, err_body

            try:
                res = self.webhook_service.process_webhook(
                    headers=headers_in or {},
                    body_bytes=body_bytes
                )
                body = json.dumps(res, ensure_ascii=False).encode("utf-8")
                return 200, headers_out, body
            except WebhookError as e:
                err_body = json.dumps({
                    "error": e.message,
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
