import urllib.request
import ssl
import json
import hashlib
import os

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

pwd_hash = hashlib.sha256('Acunetix@123'.encode()).hexdigest()
data = json.dumps({'email': 'admin@acunetix.com', 'password': pwd_hash, 'remember_me': False}).encode()
req = urllib.request.Request('https://127.0.0.1:3443/api/v1/me/login', data=data, headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req, context=ctx) as resp:
    x_auth = resp.headers.get('X-Auth')
    cookie = resp.headers.get('Set-Cookie').split(';')[0]

headers = {'X-Auth': x_auth, 'Cookie': cookie}

def get_json(url):
    r = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(r, context=ctx) as res:
        return json.loads(res.read().decode())

os.makedirs('docs/samples', exist_ok=True)

# 1. Full web app scan: demo.testfire.net (33 vulnerabilities across all severities)
scan_id_web = '7100dd13-8e31-432d-9c2c-6673f062cc89'
scan_info_web = get_json(f'https://127.0.0.1:3443/api/v1/scans/{scan_id_web}')
result_id_web = scan_info_web['current_session']['scan_session_id']
with open('docs/samples/sample_webapp_scan_info.json', 'w', encoding='utf-8') as f:
    json.dump(scan_info_web, f, indent=2)

vulns_web = get_json(f'https://127.0.0.1:3443/api/v1/scans/{scan_id_web}/results/{result_id_web}/vulnerabilities')
with open('docs/samples/sample_webapp_vulnerabilities.json', 'w', encoding='utf-8') as f:
    json.dump(vulns_web, f, indent=2)

stats_web = get_json(f'https://127.0.0.1:3443/api/v1/scans/{scan_id_web}/results/{result_id_web}/statistics')
with open('docs/samples/sample_webapp_statistics.json', 'w', encoding='utf-8') as f:
    json.dump(stats_web, f, indent=2)

# Detail of critical vuln
crit_vuln = [v for v in vulns_web['vulnerabilities'] if v['severity'] >= 3][0]
crit_detail = get_json(f'https://127.0.0.1:3443/api/v1/scans/{scan_id_web}/results/{result_id_web}/vulnerabilities/{crit_vuln["vuln_id"]}')
with open('docs/samples/sample_vulnerability_detail_critical.json', 'w', encoding='utf-8') as f:
    json.dump(crit_detail, f, indent=2)

# 2. API Scan: petstore.swagger.io
scan_id_api = '4ae7b222-96eb-4648-aadd-630dce755225'
scan_info_api = get_json(f'https://127.0.0.1:3443/api/v1/scans/{scan_id_api}')
result_id_api = scan_info_api['current_session']['scan_session_id']
with open('docs/samples/sample_api_scan_info.json', 'w', encoding='utf-8') as f:
    json.dump(scan_info_api, f, indent=2)

vulns_api = get_json(f'https://127.0.0.1:3443/api/v1/scans/{scan_id_api}/results/{result_id_api}/vulnerabilities')
with open('docs/samples/sample_api_vulnerabilities.json', 'w', encoding='utf-8') as f:
    json.dump(vulns_api, f, indent=2)

stats_api = get_json(f'https://127.0.0.1:3443/api/v1/scans/{scan_id_api}/results/{result_id_api}/statistics')
with open('docs/samples/sample_api_statistics.json', 'w', encoding='utf-8') as f:
    json.dump(stats_api, f, indent=2)

print("Saved samples for WebApp and API scans successfully!")
print(f"WebApp Vulns count: {len(vulns_web['vulnerabilities'])}, Critical sample: {crit_vuln['vt_name']}")
print(f"API Vulns count: {len(vulns_api['vulnerabilities'])}")
