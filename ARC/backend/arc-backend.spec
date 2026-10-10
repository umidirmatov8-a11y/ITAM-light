# PyInstaller spec: onedir build of the backend, placed by electron-builder into resources/backend.
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("uvicorn") + collect_submodules("arc_backend")
try:
    hidden += collect_submodules("pycaw") + collect_submodules("comtypes")
except Exception:
    pass

a = Analysis(
    ["run_backend.py"],
    pathex=["."],
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "PIL", "numpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="arc-backend",
    console=True,   # stdout carries the readiness line; Electron hides the window (windowsHide)
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="arc-backend", upx=False)
