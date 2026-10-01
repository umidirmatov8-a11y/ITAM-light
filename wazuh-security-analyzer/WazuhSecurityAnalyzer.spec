# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build specification for Wazuh Security Analyzer.
#
#   pyinstaller --noconfirm --clean WazuhSecurityAnalyzer.spec
#
# Environment switches:
#   WSA_ONEFILE=1 (default)  -> dist/WazuhSecurityAnalyzer.exe (single portable file)
#   WSA_ONEFILE=0            -> dist/WazuhSecurityAnalyzer/WazuhSecurityAnalyzer.exe (portable folder, faster start)
#   WSA_CONSOLE=1            -> console subsystem (shows CLI output, useful for --analyze / --self-test)
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ONEFILE = os.environ.get("WSA_ONEFILE", "1") == "1"
CONSOLE = os.environ.get("WSA_CONSOLE", "0") == "1"
NAME = "WazuhSecurityAnalyzer"

datas = [
    ("resources", "resources"),
    ("config", "config"),
    ("sample_data", "sample_data"),
]

hiddenimports = (
    collect_submodules("keyring.backends")
    + collect_submodules("app")
    + ["defusedxml.ElementTree", "openpyxl.cell._writer", "reportlab.graphics.barcode.common",
       "sqlalchemy.dialects.sqlite"]
)

excludes = [
    "tkinter", "matplotlib", "numpy", "pandas", "scipy", "IPython", "pytest", "_pytest",
    "fastapi", "uvicorn", "starlette",  # the optional REST API is not part of the desktop build
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DExtras",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtQml", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtNfc", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtHttpServer", "PySide6.QtWebSockets", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtSvgWidgets", "PySide6.QtCanvasPainter",
]

a = Analysis(
    ["main.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

icon = os.path.join("resources", "icons", "app.ico")
version_file = os.path.join("scripts", "version_info.txt") if sys.platform == "win32" else None

common = dict(
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed binaries are frequently flagged by antivirus engines
    console=CONSOLE,
    disable_windowed_traceback=False,
    icon=icon,
    version=version_file,
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **common)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=NAME)
