"""
Options Segregator for Deep Review Backend (Phase 3 - Task T3.4)
Separates ScanOptions into:
1. Non-Secret Configuration: Stored in DB (scan_options_configs table) and safe to log.
2. Secret Data: Passed exclusively to launcher for pod secrets, then purged from memory.
"""

from typing import Dict, Any, Tuple, Optional, List
# Mapping unified presets to engine-appropriate profile names
PRESET_PROFILE_MAP = {
    "fast_scan": "fast",
    "deep_scan": "Full Scan",
    "crawl_only": "crawl_only",
    "owasp_top10": "OWASP Top 10",
    "standard": "standard",
    "quick": "quick"
}

# Strict list of keys that must NEVER appear in the non-secret config
SECRET_KEYS_FORBIDDEN_IN_DB = {
    "target_password",
    "password",
    "webhook_token",
    "raw_token",
    "admin_password",
    "api_key",
    "secret",
    "target_credentials"
}

class OptionsSegregator:
    @staticmethod
    def segregate(
        engine: str,
        target_str: str,
        options: Dict[str, Any],
        raw_webhook_token: str,
        webhook_url: str,
        admin_credentials: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Split options into (non_secret_config, secret_data).
        Guarantees that non_secret_config contains zero passwords or tokens.
        """
        preset = options.get("preset", "fast_scan")
        profile = PRESET_PROFILE_MAP.get(preset, "fast")
        login_type = options.get("login_type", "none")

        # Extract custom headers: separate names from sensitive values
        raw_custom_headers = options.get("custom_headers", [])
        header_names_only = []
        full_headers_list = []
        if isinstance(raw_custom_headers, list):
            for h in raw_custom_headers:
                if isinstance(h, dict) and "key" in h and "value" in h:
                    header_names_only.append(h["key"])
                    full_headers_list.append(f"{h['key']}: {h['value']}")
                elif isinstance(h, dict) and "name" in h and "value" in h:
                    header_names_only.append(h["name"])
                    full_headers_list.append(f"{h['name']}: {h['value']}")
                elif isinstance(h, str) and ":" in h:
                    header_names_only.append(h.split(":", 1)[0].strip())
                    full_headers_list.append(h)

        # -------------------------------------------------------------
        # 1. Non-Secret Config (Safe for Database and Logging)
        # -------------------------------------------------------------
        non_secret_config: Dict[str, Any] = {
            "preset": preset,
            "profile": profile,
            "login_kind": login_type,
            "scan_speed": options.get("scan_speed", "fast"),
            "limit_crawler_scope": True,
            "crawl_limit": options.get("crawl_limit", 100),
            "excluded_paths": options.get("excluded_paths", []),
            "scan_timeout_minutes": options.get("scan_timeout_minutes", 30),
            "description": options.get("description", ""),
            "custom_header_names": header_names_only
        }

        # Username is an identifier, not a secret, safe to keep for display
        if options.get("target_username"):
            non_secret_config["target_username"] = options["target_username"]

        # Final audit of non-secret config: Raise error if any forbidden key leaked
        for forbidden in SECRET_KEYS_FORBIDDEN_IN_DB:
            if forbidden in non_secret_config:
                raise ValueError(
                    f"CRITICAL SECURITY FLAW: Secret key '{forbidden}' found in non_secret_config!"
                )

        # -------------------------------------------------------------
        # 2. Secret Data (For Launcher / Pod credentials.json Only)
        # -------------------------------------------------------------
        secret_data: Dict[str, Any] = {
            "target_url": target_str,
            "webhook_token": raw_webhook_token,
            "webhook_url": webhook_url
        }

        # Include admin credentials for the instance if provided
        if admin_credentials:
            if "admin_email" in admin_credentials:
                secret_data["admin_email"] = admin_credentials["admin_email"]
            if "admin_password" in admin_credentials:
                secret_data["admin_password"] = admin_credentials["admin_password"]

        # Target login credentials
        target_username = options.get("target_username")
        target_password = options.get("target_password")
        if target_username or target_password:
            secret_data["target_credentials"] = {
                "username": target_username or "",
                "password": target_password or ""
            }

        # Full custom headers (containing secret authorization values)
        if full_headers_list:
            secret_data["custom_headers"] = full_headers_list

        return non_secret_config, secret_data

    @staticmethod
    def purge_secrets(secret_data: Dict[str, Any]):
        """
        Actively overwrite and purge sensitive secrets from memory.
        """
        if not isinstance(secret_data, dict):
            return

        for k in list(secret_data.keys()):
            val = secret_data[k]
            if isinstance(val, dict):
                for sub_k in list(val.keys()):
                    val[sub_k] = "[PURGED]"
                val.clear()
            elif isinstance(val, list):
                val.clear()
            else:
                secret_data[k] = "[PURGED]"
        secret_data.clear()
