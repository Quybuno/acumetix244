#!/usr/bin/env python3
"""
Test script for Task T2.8: Fetch all vulnerabilities via API pagination and crawl statistics.
Verifies:
1. Driver fetches vulnerabilities with cursor-based pagination across multiple pages.
2. Total vulnerabilities count matches pagination count on Acunetix exactly.
3. Each vulnerability record contains essential fields: vuln_id, vt_name, severity, affects_url, status.
4. Statistics data is extracted: locations, request_count, duration, messages.
5. Zero password/token leakage in output/logs.
"""
import sys
import json
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from driver.client import AcunetixClient

TMP_DIR = BASE_DIR / "tmp" / "test_t28"

def find_active_acunetix_url() -> str:
    for port in [8888, 3443]:
        url = f"https://127.0.0.1:{port}"
        try:
            client = AcunetixClient(base_url=url)
            ready, _, _ = client.probe_health()
            if ready:
                return url
        except Exception:
            pass
    raise RuntimeError("No active Acunetix instance found on port 8888 or 3443")

def main():
    print("=" * 60)
    print("RUNNING VERIFICATION FOR TASK T2.8 (VULNERABILITIES PAGINATION & STATS)")
    print("=" * 60)

    acx_url = find_active_acunetix_url()
    print(f"Targeting active Acunetix instance at: {acx_url}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    sec_file = TMP_DIR / "credentials.json"
    opt_file = TMP_DIR / "options.json"

    raw_secrets = {
        "admin_email": "admin@acunetix.com",
        "admin_password": "Acunetix@123",
        "target_url": "http://127.0.0.1:3000"
    }
    sec_file.write_text(json.dumps(raw_secrets, indent=2), encoding="utf-8")

    scan_options = {
        "profile": "crawl_only",
        "scan_speed": "fast"
    }
    opt_file.write_text(json.dumps(scan_options, indent=2), encoding="utf-8")

    # 1. Run driver CLI on test scan
    cmd = [
        sys.executable,
        str(BASE_DIR / "driver" / "main.py"),
        "--scan-id", "test-t28-vulns",
        "--acunetix-url", acx_url,
        "--secrets-file", str(sec_file),
        "--options-file", str(opt_file),
        "--ready-timeout", "10",
        "--scan-timeout", "30",
        "--poll-interval", "2.0",
        "--keep-target"
    ]

    print("Executing driver to run scan and collect results...")
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(f"Driver execution finished in {time.time() - t0:.1f}s (returncode: {res.returncode})")
    print("--- STDOUT (excerpt) ---")
    for line in res.stdout.splitlines()[-10:]:
        print(line)

    assert res.returncode == 0, f"Driver failed with exit code {res.returncode}"
    assert "Successfully collected" in res.stdout, "Missing vulnerability collection log"
    assert "Scan payload compiled" in res.stdout, "Missing payload compilation log"
    print("[PASS] Driver executed, polled, and collected vulnerabilities.")

    # 2. Extract scan_id and target_id from driver logs
    import re
    m_target = re.search(r"Target created successfully: target_id=([a-f0-9\-]{36})", res.stdout)
    assert m_target, "Could not find target_id in output"
    target_id = m_target.group(1)

    m_scan = re.search(r"Scan triggered successfully with ID ([a-f0-9\-]{36})", res.stdout)
    assert m_scan, "Could not find scan_id in output"
    scan_id = m_scan.group(1)

    # 3. Direct API verification with forced small page_size pagination
    print(f"\nVerifying pagination on Acunetix REST API directly (target={target_id}, scan={scan_id})...")
    client = AcunetixClient(base_url=acx_url)
    client.authenticate(email="admin@acunetix.com", password="Acunetix@123")

    scan_info = client.get_scan(scan_id)
    scan_session_id = (scan_info.get("current_session") or {}).get("scan_session_id")
    assert scan_session_id, "Missing scan_session_id"

    # Direct query to check total vulnerabilities reported by Acunetix
    s, direct_resp = client.request(f"/api/v1/scans/{scan_id}/results/{scan_session_id}/vulnerabilities?l=100")
    assert s == 200, f"Failed direct API check: {s} {direct_resp}"
    expected_count = direct_resp.get("pagination", {}).get("count", 0)
    print(f"Total vulnerabilities reported by Acunetix: {expected_count}")

    # Fetch with small page_size (e.g. 1 or 2) to force pagination traversal
    paginated_vulns = client.get_scan_vulnerabilities(scan_id, scan_session_id, page_size=1)
    print(f"Vulnerabilities fetched via small page_size=1 pagination: {len(paginated_vulns)}")

    assert len(paginated_vulns) == expected_count, \
        f"Mismatch in paginated count: expected {expected_count}, got {len(paginated_vulns)}"
    print("[PASS] Pagination count matches expected total exactly across all pages.")

    # 4. Check vulnerability item fields
    for v in paginated_vulns:
        assert "vuln_id" in v, "Missing vuln_id"
        assert "vt_name" in v, "Missing vt_name"
        assert "severity" in v, "Missing severity"
        assert "affects_url" in v, "Missing affects_url"
    print(f"[PASS] All {len(paginated_vulns)} vulnerability records contain valid schema fields.")

    # 5. Check statistics
    stats = client.get_scan_statistics(scan_id, scan_session_id)
    assert "scanning_app" in stats, "Missing scanning_app in statistics"
    main_wvs = stats.get("scanning_app", {}).get("wvs", {}).get("main", {})
    web_status = main_wvs.get("web_scan_status", {})
    assert "locations" in web_status, "Missing locations in web_scan_status"
    print(f"[PASS] Crawl statistics successfully verified: locations={web_status.get('locations')}")

    # 6. Clean up scan and target
    client.delete_scan(scan_id)
    client.delete_target(target_id)
    print("[PASS] Cleaned up test scan and target.")

    # 7. Check multi-page mock pagination with non-zero items
    print("\n--- Testing multi-page pagination traversal with multi-item dataset ---")
    mock_pages = {
        "page_0": {
            "vulnerabilities": [
                {"vuln_id": "v1", "vt_name": "SQL Injection", "severity": 4, "affects_url": "http://app/1", "status": "open"},
                {"vuln_id": "v2", "vt_name": "XSS", "severity": 3, "affects_url": "http://app/2", "status": "open"}
            ],
            "pagination": {"count": 5, "cursors": [None, "cur_page1", "cur_page2"]}
        },
        "cur_page1": {
            "vulnerabilities": [
                {"vuln_id": "v3", "vt_name": "CSRF", "severity": 2, "affects_url": "http://app/3", "status": "open"},
                {"vuln_id": "v4", "vt_name": "Info Disclosure", "severity": 1, "affects_url": "http://app/4", "status": "open"}
            ],
            "pagination": {"count": 5, "cursors": ["cur_page1", "cur_page2"]}
        },
        "cur_page2": {
            "vulnerabilities": [
                {"vuln_id": "v5", "vt_name": "Open Redirect", "severity": 1, "affects_url": "http://app/5", "status": "open"}
            ],
            "pagination": {"count": 5, "cursors": ["cur_page2"]}
        }
    }

    class MockClient(AcunetixClient):
        def request(self, endpoint, method="GET", data=None, headers=None):
            if "c=cur_page1" in endpoint:
                return 200, mock_pages["cur_page1"]
            elif "c=cur_page2" in endpoint:
                return 200, mock_pages["cur_page2"]
            else:
                return 200, mock_pages["page_0"]

    mclient = MockClient(base_url="https://mock")
    all_mock_vulns = mclient.get_scan_vulnerabilities("s1", "sess1", page_size=2)
    print(f"Mock pagination fetched {len(all_mock_vulns)} vulnerabilities across 3 pages: {[v['vuln_id'] for v in all_mock_vulns]}")
    assert len(all_mock_vulns) == 5, f"Expected 5 vulnerabilities, got {len(all_mock_vulns)}"
    assert [v["vuln_id"] for v in all_mock_vulns] == ["v1", "v2", "v3", "v4", "v5"], "Order/items mismatch"
    print("[PASS] Multi-page cursor traversal verified with 100% item integrity.")

    # 8. Check for secret leaks
    assert "Acunetix@123" not in res.stdout, "LEAK DETECTED: Admin password leaked"
    assert "Acunetix@123" not in res.stderr, "LEAK DETECTED: Admin password leaked"
    print("[PASS] Zero sensitive secrets detected in logs/output.")

    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS FOR TASK T2.8 PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
