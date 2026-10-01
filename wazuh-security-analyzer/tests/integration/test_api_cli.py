import pytest

from app.cli import main, self_test


def test_self_test_passes(capsys):
    assert self_test() == 0
    assert "SELF-TEST PASSED" in capsys.readouterr().out


def test_headless_cli(tmp_path, sample_dir, capsys):
    code = main(["--analyze", str(sample_dir / "sample_bruteforce.json"), "--report-dir", str(tmp_path),
                 "--formats", "json,html"])
    assert code == 0
    out = capsys.readouterr().out
    assert "INC-" in out and (tmp_path / "wazuh_report.json").exists()


def test_rest_api(tmp_path, sample_dir):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.api.server import create_app

    client = TestClient(create_app("secret-token", workspace=tmp_path))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/analyze", json={"paths": [str(sample_dir)]}).status_code == 401
    headers = {"Authorization": "Bearer secret-token"}
    assert client.post("/analyze", json={"paths": ["/no/such/path"]}, headers=headers).status_code == 400
    resp = client.post("/analyze", json={"paths": [str(sample_dir / "sample_malware.json")]}, headers=headers)
    assert resp.status_code == 200
    sid = resp.json()["session_id"]
    assert client.get(f"/sessions/{sid}/incidents", headers=headers).json()
    assert client.get(f"/sessions/{sid}/findings?severity=critical", headers=headers).status_code == 200
    assert client.get(f"/sessions/{sid}/search?q=fs-01", headers=headers).json()["alerts"] > 0
    assert client.get("/sessions/unknown/summary", headers=headers).status_code == 404
