import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from .logger import mask_data

DEFAULT_SECRETS_PATH = Path("/secrets/credentials.json")
DEFAULT_OPTIONS_PATH = Path("/inputs/options.json")
DEFAULT_INPUTS_DIR = Path("/inputs")
DEFAULT_ACUNETIX_URL = "https://localhost:3443"

@dataclass
class DriverConfig:
    scan_id: str
    target_url: str
    webhook_url: Optional[str] = None
    acunetix_url: str = DEFAULT_ACUNETIX_URL
    inputs_dir: Path = DEFAULT_INPUTS_DIR
    
    # Raw secrets (never logged)
    secrets: Dict[str, Any] = field(default_factory=dict)
    
    # Scan options (preset, crawler limits, excluded paths)
    scan_options: Dict[str, Any] = field(default_factory=dict)

    def get_api_key(self) -> Optional[str]:
        return self.secrets.get("api_key")

    def get_webhook_token(self) -> Optional[str]:
        return self.secrets.get("webhook_token")

    def get_admin_credentials(self) -> tuple:
        return (
            self.secrets.get("admin_email", "admin@acunetix.com"),
            self.secrets.get("admin_password")
        )

    def extract_secret_strings(self) -> List[str]:
        """Extract all actual string secret values for the masking filter"""
        secrets_list = []

        def _extract(key, val):
            # Skip non-secret metadata
            if key and any(ex == key.lower() for ex in ["target_url", "webhook_url", "admin_email", "username", "name"]):
                return
            if isinstance(val, str) and len(val) >= 4:
                if val.lower() not in ["admin", "root", "user", "true", "false", "none", "null"]:
                    secrets_list.append(val)
            elif isinstance(val, dict):
                for k, v in val.items():
                    _extract(k, v)
            elif isinstance(val, list):
                for item in val:
                    _extract(key, item)

        for k, v in self.secrets.items():
            _extract(k, v)
        return secrets_list

    def to_masked_dict(self) -> Dict[str, Any]:
        """Return safe, redacted dictionary of configuration for logging"""
        return {
            "scan_id": self.scan_id,
            "target_url": self.target_url,
            "webhook_url": self.webhook_url,
            "acunetix_url": self.acunetix_url,
            "inputs_dir": str(self.inputs_dir),
            "scan_options": self.scan_options,
            "secrets_keys": list(self.secrets.keys()),
            "secrets_masked": mask_data(self.secrets)
        }

def load_config(
    scan_id: str,
    target_url: Optional[str] = None,
    webhook_url: Optional[str] = None,
    secrets_file: Optional[str] = None,
    options_file: Optional[str] = None,
    inputs_dir: Optional[str] = None,
    acunetix_url: Optional[str] = None,
) -> DriverConfig:
    """
    Load Driver configuration from files and parameters.
    """
    # 1. Resolve secrets
    secrets_data = {}
    sec_path = Path(secrets_file) if secrets_file else DEFAULT_SECRETS_PATH
    if sec_path.exists():
        try:
            secrets_data = json.loads(sec_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(f"Failed to parse secrets file {sec_path}: {e}")

    # Target URL can come from CLI param or secrets/options
    final_target = target_url or secrets_data.get("target_url") or "http://127.0.0.1:3000"

    # Webhook URL can come from CLI param or secrets
    final_webhook = webhook_url or secrets_data.get("webhook_url")

    # Acunetix URL
    final_acx = acunetix_url or os.environ.get("ACUNETIX_URL", DEFAULT_ACUNETIX_URL)

    # Inputs directory
    final_inputs = Path(inputs_dir) if inputs_dir else DEFAULT_INPUTS_DIR

    # 2. Resolve options
    options_data = {
        "profile": "default",
        "crawl_limit": 100,
        "excluded_paths": []
    }
    opt_path = Path(options_file) if options_file else DEFAULT_OPTIONS_PATH
    if opt_path.exists():
        try:
            user_opts = json.loads(opt_path.read_text(encoding="utf-8"))
            options_data.update(user_opts)
        except Exception as e:
            raise ValueError(f"Failed to parse options file {opt_path}: {e}")

    return DriverConfig(
        scan_id=scan_id,
        target_url=final_target,
        webhook_url=final_webhook,
        acunetix_url=final_acx,
        inputs_dir=final_inputs,
        secrets=secrets_data,
        scan_options=options_data
    )
