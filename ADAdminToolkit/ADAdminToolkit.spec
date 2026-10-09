# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for AD Admin Toolkit.
#   onedir (default, easier diagnostics):  pyinstaller ADAdminToolkit.spec
#   onefile:                               set ADTK_ONEFILE=1 && pyinstaller ADAdminToolkit.spec
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from adtoolkit import __version__  # noqa: E402

ONEFILE = os.environ.get("ADTK_ONEFILE") == "1"
ver = tuple(int(x) for x in __version__.split(".")) + (0,)

hidden = [
    "keyring.backends.Windows", "keyring.backends.chainer", "win32ctypes.core", "win32ctypes.pywin32.win32cred",
    "winkerberos", "dns.resolver", "dns.rdtypes.IN.SRV", "dns.rdtypes.ANY", "Crypto.Hash.MD4",
    "ldap3.protocol.sasl.kerberos", "ldap3.protocol.microsoft", "openpyxl.cell._writer",
]
excludes = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.Qt3DCore",
            "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtPdf", "PySide6.QtBluetooth", "PySide6.QtPositioning", "tkinter", "pytest"]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[("resources/icon.png", "resources"), ("resources/icon.ico", "resources"),
           ("config/settings.example.json", "config")],
    hiddenimports=hidden,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

version_file = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    version_file = VSVersionInfo(
        ffi=FixedFileInfo(filevers=ver, prodvers=ver),
        kids=[StringFileInfo([StringTable("041904B0", [
            StringStruct("FileDescription", "AD Admin Toolkit — консоль администратора Active Directory"),
            StringStruct("ProductName", "AD Admin Toolkit"), StringStruct("FileVersion", __version__),
            StringStruct("ProductVersion", __version__), StringStruct("OriginalFilename", "ADAdminToolkit.exe")])]),
              VarFileInfo([VarStruct("Translation", [0x0419, 1200])])])

common = dict(name="ADAdminToolkit", debug=False, strip=False, upx=False, console=False, icon="resources/icon.ico",
              version=version_file)
if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **common)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ADAdminToolkit")
