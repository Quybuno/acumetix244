"""
Database Schema Definition for Deep Review Backend (Phase 3 - Task T3.1)
Implements relational schema for scans, versioned scan options, and scan results.
STRICT CONSTRAINT: ZERO secret columns in any table!
"""

CREATE_TABLES_SQL = """
-- 1. Scan Jobs Table
-- Holds lifecycle state, engine type, target, and hashed webhook token.
-- NEVER store raw webhook tokens, passwords, or API keys!
CREATE TABLE IF NOT EXISTS scans (
    scan_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    engine TEXT NOT NULL CHECK(engine IN ('acunetix', 'fortify')),
    created_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('SCANNING', 'PARSING', 'COMPLETED', 'FAILED')),
    error_code TEXT,
    target TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_scans_project ON scans(project_id);
CREATE INDEX IF NOT EXISTS idx_scans_status ON scans(status);
CREATE INDEX IF NOT EXISTS idx_scans_engine ON scans(engine);
CREATE INDEX IF NOT EXISTS idx_scans_token_hash ON scans(token_hash);

-- 2. Versioned ScanOptions Configurations Table
-- Stores normalized non-secret configuration options for the scan.
-- Secret options (passwords, secret headers) are excluded before storing in DB (Task T3.4).
CREATE TABLE IF NOT EXISTS scan_options_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL DEFAULT '1.0',
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES scans(scan_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_options_scan ON scan_options_configs(scan_id);

-- 3. Scan Results Table
-- Stores aggregated findings, severity counts, crawl statistics, and step execution timings.
CREATE TABLE IF NOT EXISTS scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    vulnerabilities_count INTEGER NOT NULL DEFAULT 0,
    severity_counts_json TEXT NOT NULL,
    vulnerabilities_json TEXT NOT NULL,
    statistics_json TEXT,
    timings_json TEXT,
    coverage_warnings_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES scans(scan_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_results_scan ON scan_results(scan_id);
"""

# Restricted list of secret field names that must NEVER appear as database column names
FORBIDDEN_COLUMN_SUBSTRINGS = [
    "password",
    "secret",
    "token_raw",
    "raw_token",
    "api_key",
    "credential",
    "private_key",
    "auth_token"
]
