"""
ScanOptions Schemas with Versioning for Supported Engines (Phase 3 - Task T3.2)
Defines dynamic form schemas for Deep Review Frontend:
- Completely decoupled from engine-internal field names (Zero Acunetix-specific names exposed).
- Versioned schemas (version '1.0').
- Supports field groups, field types, validation rules, dependencies (depends_on), and secret flags.
"""

from typing import Dict, Any, List

SCHEMA_VERSION = "1.0"

# ==============================================================================
# 1. Acunetix ScanOptions Schema
# ==============================================================================
ACUNETIX_SCAN_OPTIONS_SCHEMA: Dict[str, Any] = {
    "version": SCHEMA_VERSION,
    "engine": "acunetix",
    "title": "Cấu hình quét lỗ hổng ứng dụng Web & API (Acunetix)",
    "description": "Lược đồ biểu mẫu cấu hình lượt quét DAST tự động",
    "groups": [
        {
            "id": "target",
            "title": "1. Mục tiêu quét",
            "description": "Địa chỉ máy chủ hoặc ứng dụng cần kiểm tra an toàn thông tin",
            "fields": [
                {
                    "name": "target_url",
                    "label": "Địa chỉ URL mục tiêu",
                    "type": "url",
                    "required": True,
                    "placeholder": "https://example.com hoặc http://127.0.0.1:3000",
                    "help_text": "URL đầy đủ bao gồm giao thức (http/https). Đích thử phải nằm trong danh sách được phép.",
                    "is_secret": False
                },
                {
                    "name": "description",
                    "label": "Mô tả mục tiêu",
                    "type": "string",
                    "required": False,
                    "default": "",
                    "placeholder": "Mô tả ngắn gọn về hệ thống/phiên bản cần quét",
                    "is_secret": False
                }
            ]
        },
        {
            "id": "preset",
            "title": "2. Kiểu quét (Preset)",
            "description": "Hồ sơ quét định hình phạm vi và độ sâu",
            "fields": [
                {
                    "name": "preset",
                    "label": "Hồ sơ quét định sẵn",
                    "type": "select",
                    "required": True,
                    "default": "fast_scan",
                    "options": [
                        {
                            "value": "fast_scan",
                            "label": "Quét nhanh (Fast Scan)",
                            "description": "Quét tập trung phát hiện nhanh các lỗ hổng nghiêm trọng và mức cao."
                        },
                        {
                            "value": "deep_scan",
                            "label": "Quét sâu toàn diện (Full Scan)",
                            "description": "Thu thập đầy đủ và kiểm thử toàn bộ các vector tấn công."
                        },
                        {
                            "value": "crawl_only",
                            "label": "Chỉ thu thập liên kết (Crawl Only)",
                            "description": "Lập bản đồ cấu trúc trang web và API mà không gửi payload khai thác."
                        },
                        {
                            "value": "owasp_top10",
                            "label": "Kiểm tra theo chuẩn OWASP Top 10",
                            "description": "Tập trung kiểm tra 10 nhóm rủi ro an ninh ứng dụng web hàng đầu."
                        }
                    ],
                    "is_secret": False
                }
            ]
        },
        {
            "id": "authentication",
            "title": "3. Cơ chế đăng nhập mục tiêu",
            "description": "Cấu hình xác thực nếu mục tiêu yêu cầu quyền đăng nhập",
            "fields": [
                {
                    "name": "login_type",
                    "label": "Chế độ đăng nhập",
                    "type": "select",
                    "required": True,
                    "default": "none",
                    "options": [
                        {
                            "value": "none",
                            "label": "Không yêu cầu đăng nhập",
                            "description": "Quét trang công khai không cần tài khoản."
                        },
                        {
                            "value": "automatic",
                            "label": "Đăng nhập tự động bằng biểu mẫu (Username / Password)",
                            "description": "Scanner tự động nhận diện form đăng nhập và điền thông tin."
                        },
                        {
                            "value": "sequence",
                            "label": "Chuỗi thao tác đăng nhập (.lsr)",
                            "description": "Sử dụng tệp ghi lại chuỗi thao tác đăng nhập đa bước."
                        }
                    ],
                    "is_secret": False
                },
                {
                    "name": "target_username",
                    "label": "Tên đăng nhập / Email",
                    "type": "string",
                    "required": True,
                    "depends_on": {"field": "login_type", "value": "automatic"},
                    "placeholder": "testuser@domain.com",
                    "help_text": "Chỉ sử dụng tài khoản thử nghiệm chuyên dụng.",
                    "is_secret": False
                },
                {
                    "name": "target_password",
                    "label": "Mật khẩu",
                    "type": "password",
                    "required": True,
                    "depends_on": {"field": "login_type", "value": "automatic"},
                    "help_text": "Mật khẩu được mã hóa chuyển giao và không bao giờ lưu trữ trên cơ sở dữ liệu.",
                    "is_secret": True
                },
                {
                    "name": "login_sequence_file",
                    "label": "Tệp kịch bản đăng nhập (.lsr)",
                    "type": "file",
                    "required": True,
                    "allowed_extensions": [".lsr"],
                    "max_size_bytes": 1048576,  # 1MB
                    "depends_on": {"field": "login_type", "value": "sequence"},
                    "help_text": "Tải lên tệp ghi nhận thao tác đăng nhập (.lsr, tối đa 1MB).",
                    "is_secret": False
                }
            ]
        },
        {
            "id": "imports",
            "title": "4. Định nghĩa API và tài liệu nhập",
            "description": "Tải lên tệp định nghĩa để quét các endpoint ẩn và dịch vụ REST/GraphQL",
            "fields": [
                {
                    "name": "api_definition_file",
                    "label": "Tệp đặc tả API (OpenAPI, Swagger, Postman, HAR)",
                    "type": "file",
                    "required": False,
                    "allowed_extensions": [".json", ".yaml", ".yml", ".xml", ".har"],
                    "max_size_bytes": 10485760,  # 10MB
                    "help_text": "Hỗ trợ OpenAPI 3.0 / Swagger 2.0 / Postman Collection (tối đa 10MB).",
                    "is_secret": False
                }
            ]
        },
        {
            "id": "headers",
            "title": "5. Header tùy chỉnh",
            "description": "Đính kèm thêm các HTTP Header đặc thù vào mọi request quét",
            "fields": [
                {
                    "name": "custom_headers",
                    "label": "Danh sách Header bổ sung",
                    "type": "key_value_list",
                    "required": False,
                    "default": [],
                    "key_label": "Tên Header (Header Name)",
                    "value_label": "Giá trị (Header Value)",
                    "placeholder_key": "X-Custom-Auth",
                    "placeholder_value": "token-value-xyz",
                    "help_text": "Có thể dùng để truyền token xác thực API hoặc header định danh môi trường test.",
                    "is_secret": True  # Values can contain bearer tokens
                }
            ]
        },
        {
            "id": "scope",
            "title": "6. Phạm vi và đường dẫn loại trừ",
            "description": "Ngăn chặn scanner truy cập vào các đường dẫn nhạy cảm hoặc nguy hiểm",
            "fields": [
                {
                    "name": "excluded_paths",
                    "label": "Các đường dẫn loại trừ (Excluded Paths)",
                    "type": "list_of_strings",
                    "required": False,
                    "default": [],
                    "placeholder": "/logout, /admin/delete, /api/v1/reset",
                    "help_text": "Danh sách các URL path cần loại trừ hoàn toàn trong quá trình crawl và scan.",
                    "is_secret": False
                }
            ]
        },
        {
            "id": "advanced",
            "title": "7. Tùy chọn nâng cao (Thu gọn)",
            "description": "Tinh chỉnh hiệu năng và giới hạn thời gian quét",
            "collapsed": True,
            "fields": [
                {
                    "name": "scan_speed",
                    "label": "Tốc độ quét",
                    "type": "select",
                    "required": False,
                    "default": "fast",
                    "options": [
                        {"value": "fast", "label": "Nhanh (Fast - Khuyến nghị cho dev/staging)"},
                        {"value": "moderate", "label": "Vừa phải (Moderate)"},
                        {"value": "slow", "label": "Chậm (Slow - Hạn chế tải hệ thống)"},
                        {"value": "sequential", "label": "Tuần tự (Sequential)"}
                    ],
                    "is_secret": False
                },
                {
                    "name": "crawl_limit",
                    "label": "Giới hạn số lượng liên kết thu thập",
                    "type": "integer",
                    "required": False,
                    "default": 100,
                    "min": 10,
                    "max": 5000,
                    "help_text": "Giới hạn trần số URL thu thập để tránh crawl vô hạn trên SPA.",
                    "is_secret": False
                },
                {
                    "name": "scan_timeout_minutes",
                    "label": "Thời hạn quét tối đa (phút)",
                    "type": "integer",
                    "required": False,
                    "default": 30,
                    "min": 5,
                    "max": 120,
                    "help_text": "Tự động hủy lượt quét nếu vượt quá số phút này.",
                    "is_secret": False
                }
            ]
        }
    ]
}

# ==============================================================================
# 2. Fortify ScanOptions Schema (For Reference and Compatibility)
# ==============================================================================
FORTIFY_SCAN_OPTIONS_SCHEMA: Dict[str, Any] = {
    "version": SCHEMA_VERSION,
    "engine": "fortify",
    "title": "Cấu hình quét mã nguồn tĩnh SAST (Fortify)",
    "description": "Lược đồ biểu mẫu cấu hình phân tích mã nguồn tĩnh",
    "groups": [
        {
            "id": "target",
            "title": "1. Mục tiêu mã nguồn",
            "description": "Nhánh kho chứa mã nguồn cần phân tích",
            "fields": [
                {
                    "name": "git_branch",
                    "label": "Nhánh Git (Git Branch)",
                    "type": "string",
                    "required": True,
                    "default": "main",
                    "placeholder": "main hoặc develop hoặc release/v1.0",
                    "is_secret": False
                }
            ]
        },
        {
            "id": "preset",
            "title": "2. Kiểu quét",
            "description": "Mức độ phân tích mã nguồn",
            "fields": [
                {
                    "name": "preset",
                    "label": "Hồ sơ quét",
                    "type": "select",
                    "required": True,
                    "default": "standard",
                    "options": [
                        {"value": "standard", "label": "Quét tiêu chuẩn (Standard Scan)"},
                        {"value": "quick", "label": "Quét nhanh (Quick Scan)"}
                    ],
                    "is_secret": False
                }
            ]
        }
    ]
}

# Engine registry mapping
ENGINES_REGISTRY: Dict[str, Dict[str, Any]] = {
    "acunetix": {
        "engine": "acunetix",
        "display_name": "Acunetix Web & API DAST",
        "category": "DAST",
        "enabled": True,
        "schema": ACUNETIX_SCAN_OPTIONS_SCHEMA
    },
    "fortify": {
        "engine": "fortify",
        "display_name": "Fortify Static Code SAST",
        "category": "SAST",
        "enabled": True,
        "schema": FORTIFY_SCAN_OPTIONS_SCHEMA
    }
}

# Internal keywords specific to Acunetix engine that must NEVER be leaked in schemas
ACUNETIX_INTERNAL_KEYWORDS = [
    "default_scanning_profile_id",
    "limit_crawler_scope",
    "ad_blocker",
    "sensor_secret",
    "client_certificate_password",
    "ssh_credentials",
    "case_sensitive",
    "technologies"
]

def get_scan_options_schema(engine: str) -> Dict[str, Any]:
    """
    Retrieve versioned ScanOptions schema for a given engine.
    Raises ValueError if engine is unknown or unsupported.
    """
    engine_lower = engine.strip().lower()
    if engine_lower not in ENGINES_REGISTRY:
        raise ValueError(
            f"Unsupported engine '{engine}'. Supported engines: {list(ENGINES_REGISTRY.keys())}"
        )
    return ENGINES_REGISTRY[engine_lower]["schema"]

def list_supported_engines() -> List[Dict[str, Any]]:
    """List all supported engines and metadata."""
    return [
        {
            "engine": item["engine"],
            "display_name": item["display_name"],
            "category": item["category"],
            "enabled": item["enabled"]
        }
        for item in ENGINES_REGISTRY.values()
    ]
