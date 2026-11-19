import subprocess
import time
import urllib.request
import ssl
import json
import hashlib

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def run_cmd(args):
    return subprocess.check_output(args).decode().strip()

def check_instance(port):
    url = f"https://127.0.0.1:{port}/api/v1/info"
    ready = False
    for i in range(25):
        try:
            r = urllib.request.Request(url)
            with urllib.request.urlopen(r, context=ctx, timeout=2) as res:
                ready = True
                break
        except urllib.error.HTTPError as e:
            if e.code in [400, 401]:
                ready = True
                break
        except Exception:
            time.sleep(2)
    if not ready:
        raise Exception(f"Port {port} not ready in 50s")

    # Login
    pwd_hash = hashlib.sha256('Acunetix@123'.encode()).hexdigest()
    data = json.dumps({'email': 'admin@acunetix.com', 'password': pwd_hash, 'remember_me': False}).encode()
    req = urllib.request.Request(f'https://127.0.0.1:{port}/api/v1/me/login', data=data, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
        x_auth = resp.headers.get('X-Auth')
        cookie = resp.headers.get('Set-Cookie').split(';')[0]

    headers = {'X-Auth': x_auth, 'Cookie': cookie}
    r_targets = urllib.request.Request(f'https://127.0.0.1:{port}/api/v1/targets', headers=headers)
    with urllib.request.urlopen(r_targets, context=ctx, timeout=5) as res:
        targets = json.loads(res.read().decode())['targets']

    r_scans = urllib.request.Request(f'https://127.0.0.1:{port}/api/v1/scans', headers=headers)
    with urllib.request.urlopen(r_scans, context=ctx, timeout=5) as res:
        scans = json.loads(res.read().decode())['scans']

    r_info = urllib.request.Request(f'https://127.0.0.1:{port}/api/v1/info', headers=headers)
    with urllib.request.urlopen(r_info, context=ctx, timeout=5) as res:
        info = json.loads(res.read().decode())
        license_act = info.get('license', {}).get('activated')

    return len(targets), len(scans), license_act, headers

print("[1] Spawning Instance 1 (ephemeral_test)...")
run_cmd(["docker", "run", "-d", "-p", "8890:3443", "--name", "ephemeral_test", "acunetix:24.4"])
time.sleep(2)
run_cmd(["docker", "exec", "-u", "0", "ephemeral_test", "chmod", "777", "/home/acunetix/.acunetix/data/license"])

t_cnt, s_cnt, lic, headers = check_instance(8890)
print(f"    Instance 1: Targets={t_cnt}, Scans={s_cnt}, LicenseActivated={lic}")

print("[2] Creating a target in Instance 1 to dirty the state...")
target_body = json.dumps({'address': 'http://127.0.0.1:3000', 'description': 'Dirtied state'}).encode()
h = dict(headers)
h['Content-Type'] = 'application/json'
r = urllib.request.Request('https://127.0.0.1:8890/api/v1/targets', data=target_body, headers=h, method='POST')
with urllib.request.urlopen(r, context=ctx) as res:
    print("    Target created. Status:", res.status)

print("[3] Deleting Instance 1 completely (docker rm -f)...")
run_cmd(["docker", "rm", "-f", "ephemeral_test"])
print("    Instance 1 deleted.")

print("[4] Spawning Instance 2 fresh from image (ephemeral_test2)...")
run_cmd(["docker", "run", "-d", "-p", "8890:3443", "--name", "ephemeral_test2", "acunetix:24.4"])
time.sleep(2)
run_cmd(["docker", "exec", "-u", "0", "ephemeral_test2", "chmod", "777", "/home/acunetix/.acunetix/data/license"])

t_cnt2, s_cnt2, lic2, _ = check_instance(8890)
print(f"    Instance 2: Targets={t_cnt2}, Scans={s_cnt2}, LicenseActivated={lic2}")

print("[5] Cleaning up Instance 2...")
run_cmd(["docker", "rm", "-f", "ephemeral_test2"])
print("    Instance 2 cleaned up.")

assert t_cnt2 == 0, "Targets must be 0 in clean instance"
assert s_cnt2 == 0, "Scans must be 0 in clean instance"
assert lic2 == True, "License must be activated"
print("\n--> T0.11 EPHEMERAL POD LIFECYCLE VERIFIED SUCCESSFULLY!")
