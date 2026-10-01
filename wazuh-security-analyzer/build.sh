#!/usr/bin/env bash
# Linux/macOS build of the same application (the Windows .exe is produced by build.ps1 on Windows).
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -r requirements-dev.txt
python3 scripts/generate_demo_data.py
QT_QPA_PLATFORM=offscreen python3 -m pytest -q -m "not slow"
WSA_ONEFILE="${WSA_ONEFILE:-1}" python3 -m PyInstaller --noconfirm --clean WazuhSecurityAnalyzer.spec
BIN=dist/WazuhSecurityAnalyzer
[ -d "$BIN" ] && BIN="$BIN/WazuhSecurityAnalyzer"
WSA_HOME="$(mktemp -d)" QT_QPA_PLATFORM=offscreen "$BIN" --self-test
