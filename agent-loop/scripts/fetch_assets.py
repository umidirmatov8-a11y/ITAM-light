"""Download what the installer bundles: llama.cpp's llama-server (Windows, CPU) and GGUF weights.

    python scripts/fetch_assets.py                      # defaults below
    python scripts/fetch_assets.py --llama-tag b6500 --model-repo Qwen/Qwen2.5-1.5B-Instruct-GGUF \
        --model-file qwen2.5-1.5b-instruct-q4_k_m.gguf

Results: runtime/ (llama-server.exe + DLLs) and models/<file>.gguf next to this project's main.py.
The weights are verified against the SHA-256 that Hugging Face publishes for the file and are not
downloaded again when an identical file is already present.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_REPO = "Qwen/Qwen2.5-3B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "qwen2.5-3b-instruct-q4_k_m.gguf"
LLAMA_REPO = "ggml-org/llama.cpp"
# The Vulkan build = the CPU build + ggml-vulkan.dll (backends load dynamically): it uses a GPU when the
# machine has a Vulkan driver and runs on the CPU otherwise.
DEFAULT_BACKEND = "vulkan"


def asset_pattern(backend: str) -> re.Pattern:
    return re.compile(rf"win-{re.escape(backend)}-x64\.zip$")
CHUNK = 8 * 1024 * 1024


def _get(url: str, headers: dict | None = None):
    request = urllib.request.Request(url, headers={"User-Agent": "AgentLoop-build", **(headers or {})})
    return urllib.request.urlopen(request, timeout=120)


def _github_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _pick_asset(release: dict, backend: str = DEFAULT_BACKEND) -> dict | None:
    pattern = asset_pattern(backend)
    assets = [a for a in release.get("assets", []) if pattern.search(a["name"].lower())]
    # Prefer the plain CPU build over variants (e.g. "-cpu-avx2-" or archives with extra tooling).
    assets.sort(key=lambda a: (len(a["name"]), a["name"]))
    return assets[0] if assets else None


def _release_by_tag(tag: str) -> dict:
    with _get(f"https://api.github.com/repos/{LLAMA_REPO}/releases/tags/{tag}", _github_headers()) as resp:
        return json.load(resp)


def find_llama_release(tag: str, backend: str = DEFAULT_BACKEND) -> tuple[dict, dict]:
    """The release with a Windows x64 build for `backend` (vulkan, cpu...) and that asset.

    llama.cpp's stable releases (vX.Y.Z) only carry nightly-tag.txt naming the build they were cut from;
    the binaries live in that build's (pre-)release. Order: the given tag, else the newest stable release
    (following nightly-tag.txt), else the newest build that has the asset.
    """
    if tag != "latest":
        releases = [_release_by_tag(tag)]
    else:
        with _get(f"https://api.github.com/repos/{LLAMA_REPO}/releases?per_page=40", _github_headers()) as resp:
            releases = [r for r in json.load(resp) if not r.get("draft")]
        releases.sort(key=lambda r: bool(r.get("prerelease")))  # stable first, newest first within each
    for release in releases:
        asset = _pick_asset(release, backend)
        if asset:
            return release, asset
        pointer = next((a for a in release.get("assets", []) if a["name"] == "nightly-tag.txt"), None)
        if pointer:
            with _get(pointer["browser_download_url"]) as resp:
                build_tag = resp.read().decode("utf-8").strip()
            if build_tag:
                build = _release_by_tag(build_tag)
                asset = _pick_asset(build, backend)
                if asset:
                    print(f"llama.cpp {release['tag_name']} -> build {build_tag}", flush=True)
                    return build, asset
    names = sorted({a["name"] for r in releases[:3] for a in r.get("assets", [])})
    raise SystemExit(f"No llama.cpp release with an asset matching {asset_pattern(backend).pattern}; "
                     f"recent assets: {names}")


def fetch_llama_server(tag: str, dest: Path, backend: str = DEFAULT_BACKEND) -> str:
    release, asset = find_llama_release(tag, backend)
    print(f"llama.cpp {release['tag_name']}: downloading {asset['name']} ({asset['size'] / 1e6:.0f} MB)", flush=True)
    with _get(asset["browser_download_url"]) as resp:
        archive = zipfile.ZipFile(io.BytesIO(resp.read()))
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for info in archive.infolist():
        name = Path(info.filename).name
        if info.is_dir() or not (name.lower().endswith(".dll") or name.lower() == "llama-server.exe"
                                 or name.upper().startswith("LICENSE")):
            continue
        with archive.open(info) as src, open(dest / name, "wb") as out:
            shutil.copyfileobj(src, out)
    if not (dest / "llama-server.exe").is_file():
        raise SystemExit(f"{asset['name']} does not contain llama-server.exe")
    (dest / "VERSION.txt").write_text(f"llama.cpp {release['tag_name']} ({backend})\n{asset['browser_download_url']}\n",
                                      encoding="utf-8")
    return release["tag_name"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def hf_file_info(repo: str, filename: str) -> dict:
    """{'size': int, 'sha256': str} for a file of a Hugging Face model repo."""
    with _get(f"https://huggingface.co/api/models/{repo}/tree/main") as resp:
        entries = json.load(resp)
    for entry in entries:
        if entry.get("path") == filename:
            lfs = entry.get("lfs") or {}
            return {"size": int(lfs.get("size") or entry.get("size") or 0), "sha256": lfs.get("oid", "")}
    raise SystemExit(f"{filename} not found in https://huggingface.co/{repo}")


def fetch_model(repo: str, filename: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / filename
    info = hf_file_info(repo, filename)
    if target.is_file() and target.stat().st_size == info["size"] and _sha256(target) == info["sha256"]:
        print(f"{filename}: already present and verified", flush=True)
        return target
    for stale in dest.glob("*.gguf"):
        stale.unlink()
    part = target.with_suffix(".part")
    url = f"https://huggingface.co/{repo}/resolve/main/{filename}"
    print(f"Downloading {url} ({info['size'] / 1e9:.2f} GB)", flush=True)
    done, next_report = 0, 0
    with _get(url) as resp, open(part, "wb") as out:
        for block in iter(lambda: resp.read(CHUNK), b""):
            out.write(block)
            done += len(block)
            if done >= next_report:
                print(f"  {done / 1e9:.2f} / {info['size'] / 1e9:.2f} GB", flush=True)
                next_report += 256 * 1024 * 1024
    actual = _sha256(part)
    if info["sha256"] and actual != info["sha256"]:
        part.unlink()
        raise SystemExit(f"{filename}: SHA-256 mismatch ({actual} != {info['sha256']})")
    part.replace(target)
    (dest / "SOURCE.txt").write_text(
        f"{filename}\nhttps://huggingface.co/{repo}\nSHA-256: {actual}\n"
        f"Лицензия модели — см. страницу модели на Hugging Face.\n", encoding="utf-8")
    print(f"{filename}: verified SHA-256 {actual}", flush=True)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--llama-tag", default=os.environ.get("LLAMA_CPP_TAG", "latest"))
    parser.add_argument("--backend", default=os.environ.get("LLAMA_CPP_BACKEND", DEFAULT_BACKEND),
                        help="vulkan (GPU with CPU fallback, default) or cpu")
    parser.add_argument("--model-repo", default=os.environ.get("AGENTLOOP_MODEL_REPO", DEFAULT_MODEL_REPO))
    parser.add_argument("--model-file", default=os.environ.get("AGENTLOOP_MODEL_FILE", DEFAULT_MODEL_FILE))
    parser.add_argument("--skip-runtime", action="store_true")
    parser.add_argument("--skip-model", action="store_true")
    args = parser.parse_args(argv)
    if not args.skip_runtime:
        fetch_llama_server(args.llama_tag, ROOT / "runtime", args.backend)
    if not args.skip_model:
        fetch_model(args.model_repo, args.model_file, ROOT / "models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
