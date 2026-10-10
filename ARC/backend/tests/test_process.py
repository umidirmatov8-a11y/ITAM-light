"""The backend as a real process: readiness line, token check, graceful shutdown, parent watchdog."""
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
TOKEN = "p" * 48


def start_backend(tmp_path, parent_pid=0):
    env = {**os.environ, "ARC_API_TOKEN": TOKEN, "PYTHONPATH": str(BACKEND_DIR)}
    args = [sys.executable, "-m", "arc_backend", "--mock", "--data-dir", str(tmp_path / "data")]
    if parent_pid:
        args += ["--parent-pid", str(parent_pid)]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(BACKEND_DIR))
    line = proc.stdout.readline().decode()
    ready = json.loads(line)
    assert ready["event"] == "ready", line
    return proc, ready["port"]


def wait_exit(proc, timeout=15):
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("backend did not exit")


def test_starts_offline_and_shuts_down(tmp_path):
    proc, port = start_backend(tmp_path)
    try:
        base = f"http://127.0.0.1:{port}"
        assert httpx.get(base + "/api/health", trust_env=False).status_code == 403
        health = httpx.get(base + "/api/health", headers={"X-ARC-Token": TOKEN}, trust_env=False).json()
        assert health["ok"] and health["simulated"]
        result = httpx.post(base + "/api/command", json={"text": "который час"}, headers={"X-ARC-Token": TOKEN},
                            trust_env=False).json()
        assert result["status"] == "done"
        httpx.post(base + "/api/shutdown", headers={"X-ARC-Token": TOKEN}, trust_env=False)
        assert wait_exit(proc) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert (tmp_path / "data" / "arc.db").exists()
    assert (tmp_path / "data" / "logs" / "backend.log").exists()


def test_exits_when_parent_dies(tmp_path):
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    proc, _port = start_backend(tmp_path, parent_pid=parent.pid)
    try:
        assert proc.poll() is None
        parent.kill()
        parent.wait()
        assert wait_exit(proc) == 0
    finally:
        if proc.poll() is None:
            proc.kill()


def test_refuses_to_start_without_token(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "ARC_API_TOKEN"}
    env["PYTHONPATH"] = str(BACKEND_DIR)
    out = subprocess.run([sys.executable, "-m", "arc_backend", "--mock", "--data-dir", str(tmp_path)],
                         capture_output=True, env=env, cwd=str(BACKEND_DIR), timeout=60)
    assert out.returncode == 2
    assert b"ARC_API_TOKEN" in out.stdout


def test_selftest_cli():
    out = subprocess.run([sys.executable, "-m", "arc_backend", "--selftest"], capture_output=True,
                         cwd=str(BACKEND_DIR), timeout=120)
    assert out.returncode == 0, out.stdout.decode() + out.stderr.decode()
    assert json.loads(out.stdout.decode("utf-8"))["passed"] is True
