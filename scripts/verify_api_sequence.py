import urllib.request
import ssl
import json
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

API_BASE = "https://127.0.0.1:8888/api/v1"
API_KEY = "1986ad8c0a5b3df4d7028d5f3c06e936cc6423db254c54503b2a9510552130f6c"

def api_call(path, method="GET", data=None):
    url = f"{API_BASE}{path}"
    headers = {"X-Auth": API_KEY, "Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        resp_data = resp.read()
        return resp.status, resp.headers, (json.loads(resp_data.decode()) if resp_data else None)

print("[1] Healthcheck /api/v1/info...")
status, _, info = api_call("/info")
print(f"    Status: {status}, Acunetix build: {info.get('build_number')}")

print("[2] Create Target for http://127.0.0.1:3000...")
status, _, target = api_call("/targets", method="POST", data={
    "address": "http://127.0.0.1:3000",
    "description": "T0.6 API Sequence Verification",
    "criticality": 10
})
target_id = target["target_id"]
print(f"    Status: {status}, Target ID: {target_id}")

print("[3] Configure Target (headers, login, excluded paths)...")
status, _, _ = api_call(f"/targets/{target_id}/configuration", method="PATCH", data={
    "scan_speed": "fast",
    "limit_crawler_scope": True,
    "custom_headers": ["X-Test-Driver: MockDeepReview"],
    "excluded_paths": ["/logout"],
    "login": {
        "kind": "automatic",
        "credentials": {
            "enabled": True,
            "username": "admin@juice-sh.op",
            "password": "adminpassword"
        }
    }
})
print(f"    Status: {status} (Config updated)")

print("[4] Start Crawl-Only Scan...")
status, headers, scan_resp = api_call("/scans", method="POST", data={
    "target_id": target_id,
    "profile_id": "11111111-1111-1111-1111-111111111117", # Crawl Only
    "schedule": {"disable": False, "start_date": None, "time_sensitive": False}
})
# Location header format: /api/v1/scans/{scan_id}
loc = headers.get("Location")
scan_id = loc.split("/")[-1] if loc else (scan_resp.get("scan_id") if scan_resp else None)
print(f"    Status: {status}, Scan ID: {scan_id}")

print("[5] Polling Scan Status (3 iterations)...")
for i in range(3):
    time.sleep(2)
    status, _, scan_info = api_call(f"/scans/{scan_id}")
    curr = scan_info.get("current_session", {})
    print(f"    Iter {i+1}: status={curr.get('status')}, progress={curr.get('progress')}%, manual_intervention={scan_info.get('manual_intervention')}")

print("[6] Abort Scan (cleanup test)...")
status, _, _ = api_call(f"/scans/{scan_id}/abort", method="POST")
print(f"    Status: {status} (Scan aborted)")

print("[7] Delete Target...")
status, _, _ = api_call(f"/targets/{target_id}", method="DELETE")
print(f"    Status: {status} (Target deleted cleanly)")

print("\n--> T0.6 FULL SEQUENCE VERIFIED SUCCESSFULLY!")
