#!/usr/bin/env python3
"""
Test script for Task T2.12: Package driver into non-root Dockerfile and container image.
Verifies:
1. Docker image deepreview-acunetix-driver:local builds cleanly from driver/Dockerfile.
2. Container executes under non-root security context: uid=1000(driver), gid=1000(driver).
3. CLI help and arguments work properly inside the container.
4. Container executes in pod giả setup with mounted read-only secrets and inputs.
5. Zero password or token leaks in logs/output.
"""
import sys
import json
import subprocess
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def main():
    print("=" * 60)
    print("RUNNING VERIFICATION FOR TASK T2.12 (NON-ROOT DRIVER DOCKER IMAGE)")
    print("=" * 60)

    image_tag = "deepreview-acunetix-driver:local"

    # 1. Verify build
    print("\n--- TEST 1: Docker Build ---")
    build_cmd = [
        "docker", "build",
        "-t", image_tag,
        "-f", str(BASE_DIR / "driver" / "Dockerfile"),
        str(BASE_DIR)
    ]
    res_build = subprocess.run(build_cmd, capture_output=True, text=True)
    assert res_build.returncode == 0, f"Docker build failed: {res_build.stderr}"
    print(f"[PASS] Docker image '{image_tag}' built successfully.")

    # 2. Verify non-root user
    print("\n--- TEST 2: Security Context (Non-Root User Check) ---")
    id_cmd = ["docker", "run", "--rm", "--entrypoint", "id", image_tag]
    res_id = subprocess.run(id_cmd, capture_output=True, text=True)
    print(f"Container identity output: {res_id.stdout.strip()}")
    assert res_id.returncode == 0, f"Failed to execute id command: {res_id.stderr}"
    assert "uid=1000(driver)" in res_id.stdout, "Container is NOT running as UID 1000"
    assert "gid=1000(driver)" in res_id.stdout, "Container is NOT running as GID 1000"
    assert "root" not in res_id.stdout.splitlines()[0], "Root user detected!"
    print("[PASS] Verified non-root security context: UID 1000 (driver).")

    # 3. Verify CLI usage
    print("\n--- TEST 3: CLI Options and Help ---")
    help_cmd = ["docker", "run", "--rm", image_tag, "--help"]
    res_help = subprocess.run(help_cmd, capture_output=True, text=True)
    assert res_help.returncode == 0, f"Help command failed: {res_help.stderr}"
    assert "Deep Review Acunetix Scanner Driver" in res_help.stdout, "Missing banner in help output"
    assert "--scan-id" in res_help.stdout, "Missing --scan-id option"
    assert "--job-timeout" in res_help.stdout, "Missing --job-timeout option"
    assert "--webhook-retries" in res_help.stdout, "Missing --webhook-retries option"
    print("[PASS] Container CLI interface works cleanly with full options.")

    # 4. Verify running in pod giả volume mounts (dry-run mode)
    print("\n--- TEST 4: Execution with Volume Mounts ---")
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        sec_dir = tmp_path / "secrets"
        inp_dir = tmp_path / "inputs"
        sec_dir.mkdir(parents=True, exist_ok=True)
        inp_dir.mkdir(parents=True, exist_ok=True)

        raw_secrets = {
            "admin_email": "admin@acunetix.com",
            "admin_password": "Acunetix@123",
            "target_url": "http://127.0.0.1:3000"
        }
        (sec_dir / "credentials.json").write_text(json.dumps(raw_secrets), encoding="utf-8")
        (inp_dir / "options.json").write_text(json.dumps({"profile": "crawl_only"}), encoding="utf-8")

        run_cmd = [
            "docker", "run", "--rm",
            "-v", f"{sec_dir}:/secrets:ro",
            "-v", f"{inp_dir}:/inputs:ro",
            image_tag,
            "--scan-id", "test-t212-mount",
            "--secrets-file", "/secrets/credentials.json",
            "--options-file", "/inputs/options.json",
            "--no-scan",
            "--ready-timeout", "2",
            "--acunetix-url", "https://127.0.0.1:59999"
        ]
        res_run = subprocess.run(run_cmd, capture_output=True, text=True)
        # Should exit with code 10 (not ready) since 59999 is unreachable, but successfully read mounts and executed as non-root
        print(f"Container dry run exited with returncode {res_run.returncode}")
        assert res_run.returncode == 10, f"Expected code 10, got {res_run.returncode}"
        assert "Driver configuration loaded successfully" in res_run.stdout, "Failed to load config from mounts"
        assert "Acunetix@123" not in res_run.stdout, "Secret leaked in container stdout"
        print("[PASS] Container successfully read mounted configuration as non-root.")

    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS FOR TASK T2.12 PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
