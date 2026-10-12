"""Release helper used by CI (job "release") and by maintainers.

    python scripts/release_notes.py --tag arc-v1.0.0 --out notes.md

Checks that the tag, app/package.json and the backend __version__ name the same version and
that CHANGELOG.md has a section for it; writes that section as the release notes.
Exit code 1 with a readable message when anything does not match.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = re.compile(r"^arc-v(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)$")


def versions() -> dict[str, str]:
    package = json.loads((ROOT / "app" / "package.json").read_text(encoding="utf-8"))["version"]
    init = (ROOT / "backend" / "arc_backend" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    return {"app/package.json": package, "backend __version__": match.group(1) if match else "?"}


def changelog_section(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    pattern = re.compile(rf"^## {re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def check(tag: str) -> tuple[str, str]:
    match = TAG.match(tag)
    if not match:
        raise SystemExit(f"tag {tag!r} must look like arc-v1.2.3")
    version = match.group(1)
    wrong = {k: v for k, v in versions().items() if v != version}
    if wrong:
        raise SystemExit(f"version mismatch with tag {tag}: " + ", ".join(f"{k}={v}" for k, v in wrong.items()))
    notes = changelog_section(version)
    if not notes:
        raise SystemExit(f"CHANGELOG.md has no section '## {version}'")
    return version, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    version, notes = check(args.tag)
    Path(args.out).write_text(notes + "\n", encoding="utf-8")
    sys.stdout.write(f"release {version}: notes {len(notes)} chars\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
