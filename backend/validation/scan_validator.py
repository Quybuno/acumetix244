"""
Scan Validator for Deep Review Backend (Phase 3 - Task T3.3)
Validates:
- Engine type
- Target URL for Acunetix (required, syntax, no credentials/tokens in URL, URL allowlist)
- Target branch for Fortify
- Unknown/unrecognized fields rejection
- Uploaded files validation (allowed extensions, maximum size limits)
"""

import re
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, List, Optional, Tuple
from backend.schemas.scan_options import (
    ACUNETIX_SCAN_OPTIONS_SCHEMA,
    FORTIFY_SCAN_OPTIONS_SCHEMA,
    ENGINES_REGISTRY
)

# Default Allowlist for Test and Development Targets
DEFAULT_ALLOWED_URL_PATTERNS = [
    r"^https?://localhost(:\d+)?(/.*)?$",
    r"^https?://127\.0\.0\.1(:\d+)?(/.*)?$",
    r"^https?://host\.docker\.internal(:\d+)?(/.*)?$",
    r"^https?://.*\.internal\.domain(:\d+)?(/.*)?$",
    r"^https?://juice-shop(:\d+)?(/.*)?$"
]

# Sensitive query parameter names that must NOT appear in target URLs
SENSITIVE_QUERY_PARAMS = {
    "token", "access_token", "api_key", "apikey", "secret", "password", "auth", "session"
}

class ValidationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class ScanValidator:
    def __init__(self, allowed_url_patterns: Optional[List[str]] = None):
        self.allowed_url_patterns = allowed_url_patterns or DEFAULT_ALLOWED_URL_PATTERNS

    def validate_create_request(
        self,
        engine: str,
        project_id: str,
        created_by: str,
        scan_options: Dict[str, Any],
        uploaded_files: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """
        Validate complete scan creation request.
        Returns: (target_string, cleaned_options, validated_files)
        Raises: ValidationError on any validation failure.
        """
        # 1. Validate basic metadata
        if not engine or engine not in ENGINES_REGISTRY:
            raise ValidationError(f"Invalid or unsupported engine '{engine}'. Must be one of {list(ENGINES_REGISTRY.keys())}")
        if not project_id or not project_id.strip():
            raise ValidationError("Missing required field: 'project_id'")
        if not created_by or not created_by.strip():
            raise ValidationError("Missing required field: 'created_by'")

        schema = ENGINES_REGISTRY[engine]["schema"]
        allowed_field_names = set()
        file_field_configs = {}
        for group in schema.get("groups", []):
            for f in group.get("fields", []):
                allowed_field_names.add(f["name"])
                if f.get("type") == "file":
                    file_field_configs[f["name"]] = f

        # 2. Reject unknown fields in scan_options
        unknown_fields = [k for k in scan_options.keys() if k not in allowed_field_names]
        if unknown_fields:
            raise ValidationError(
                f"Unknown field(s) rejected for engine '{engine}': {unknown_fields}. "
                f"Allowed fields: {sorted(list(allowed_field_names))}"
            )

        # 3. Engine-specific Target validation
        target_str = ""
        if engine == "acunetix":
            target_url = scan_options.get("target_url")
            if not target_url or not str(target_url).strip():
                raise ValidationError("Missing required field for Acunetix: 'target_url'")
            target_str = self.validate_target_url(str(target_url).strip())
        elif engine == "fortify":
            git_branch = scan_options.get("git_branch", "main")
            if not git_branch or not str(git_branch).strip():
                raise ValidationError("Missing required field for Fortify: 'git_branch'")
            target_str = str(git_branch).strip()

        # 4. Validate uploaded files
        validated_files = {}
        if uploaded_files:
            for field_name, file_data in uploaded_files.items():
                if field_name not in file_field_configs:
                    raise ValidationError(f"Unexpected uploaded file field '{field_name}' for engine '{engine}'")
                validated_file = self.validate_file(field_name, file_data, file_field_configs[field_name])
                validated_files[field_name] = validated_file

        return target_str, scan_options, validated_files

    def validate_target_url(self, url: str) -> str:
        """
        Validate URL syntax, credentials, query parameters, and allowlist.
        """
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise ValidationError(f"Invalid URL syntax '{url}': {e}")

        # Check scheme
        if parsed.scheme.lower() not in ["http", "https"]:
            raise ValidationError(f"Invalid URL scheme '{parsed.scheme}'. Only http and https are permitted.")

        # Check host/netloc
        if not parsed.netloc:
            raise ValidationError(f"Invalid URL: Missing host in '{url}'.")

        # Disallow embedded credentials in URL (e.g., http://user:pass@host)
        if parsed.username or parsed.password:
            raise ValidationError(
                "Security violation: Embedded credentials (user:pass@host) are forbidden in target URL."
            )

        # Check query parameters for sensitive tokens
        if parsed.query:
            query_params = parse_qs(parsed.query)
            leaked_params = [p for p in query_params.keys() if p.lower() in SENSITIVE_QUERY_PARAMS]
            if leaked_params:
                raise ValidationError(
                    f"Security violation: Target URL contains sensitive token parameter(s) {leaked_params} in query string."
                )

        # Check against target URL allowlist
        matched = False
        for pattern in self.allowed_url_patterns:
            if re.match(pattern, url, re.IGNORECASE):
                matched = True
                break

        if not matched:
            raise ValidationError(
                f"Target URL '{url}' is not in the authorized targets allowlist."
            )

        return url

    def validate_file(self, field_name: str, file_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate an uploaded file's extension and size.
        """
        filename = file_data.get("filename", "")
        content = file_data.get("content", b"")
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        elif isinstance(content, bytes):
            content_bytes = content
        else:
            raise ValidationError(f"Invalid content format for file '{filename}' in field '{field_name}'")

        # Check extension
        allowed_exts = config.get("allowed_extensions", [])
        if allowed_exts:
            fname_lower = filename.lower()
            if not any(fname_lower.endswith(ext.lower()) for ext in allowed_exts):
                raise ValidationError(
                    f"Invalid file extension for '{filename}'. Allowed extensions for '{field_name}': {allowed_exts}"
                )

        # Check size limit
        max_size = config.get("max_size_bytes", 10485760)  # default 10MB
        if len(content_bytes) > max_size:
            raise ValidationError(
                f"File '{filename}' exceeds maximum allowed size of {max_size} bytes (size: {len(content_bytes)} bytes)"
            )

        return {
            "filename": filename,
            "content": content_bytes,
            "size": len(content_bytes)
        }
