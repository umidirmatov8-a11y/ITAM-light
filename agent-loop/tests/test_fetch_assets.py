import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_assets  # noqa: E402

RELEASES = [
    {"tag_name": "v0.6.0", "assets": [{"name": "llama-cpp-python-src.tar.gz"}]},
    {"tag_name": "b7001", "prerelease": True, "assets": [{"name": "llama-b7001-bin-win-cpu-x64.zip"}]},
    {"tag_name": "b7000", "assets": [
        {"name": "llama-b7000-bin-win-cuda-12.4-x64.zip"},
        {"name": "llama-b7000-bin-win-cpu-x64.zip"},
        {"name": "llama-b7000-bin-ubuntu-x64.zip"},
    ]},
]


def fake_get(payload, routes=None):
    def _get(url, headers=None):
        for suffix, body in (routes or {}).items():
            if url.endswith(suffix):
                return io.BytesIO(body if isinstance(body, bytes) else json.dumps(body).encode())
        return io.BytesIO(json.dumps(payload).encode())
    return _get


def test_stable_release_without_binaries_follows_nightly_tag(monkeypatch):
    stable = {"tag_name": "v0.6.0", "assets": [
        {"name": "nightly-tag.txt", "browser_download_url": "https://x/nightly-tag.txt"}]}
    build = {"tag_name": "b6990", "prerelease": True,
             "assets": [{"name": "llama-b6990-bin-win-cpu-x64.zip"}]}
    newer_build = {"tag_name": "b7005", "prerelease": True,
                   "assets": [{"name": "llama-b7005-bin-win-cpu-x64.zip"}]}
    monkeypatch.setattr(fetch_assets, "_get", fake_get(
        [newer_build, stable, build], {"/nightly-tag.txt": b"b6990\n", "/tags/b6990": build}))
    release, asset = fetch_assets.find_llama_release("latest")
    assert release["tag_name"] == "b6990"  # the build the stable release points to, not the newest nightly
    assert asset["name"] == "llama-b6990-bin-win-cpu-x64.zip"


def test_falls_back_to_newest_build_with_windows_cpu_zip(monkeypatch):
    monkeypatch.setattr(fetch_assets, "_get", fake_get(RELEASES))
    release, asset = fetch_assets.find_llama_release("latest")
    assert release["tag_name"] == "b7000"
    assert asset["name"] == "llama-b7000-bin-win-cpu-x64.zip"


def test_reports_available_assets_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(fetch_assets, "_get", fake_get(RELEASES[:1]))
    with pytest.raises(SystemExit, match="llama-cpp-python-src"):
        fetch_assets.find_llama_release("latest")
