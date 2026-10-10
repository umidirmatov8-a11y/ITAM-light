# PyInstaller spec: onedir build of the backend, placed by electron-builder into resources/backend.
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

hidden = collect_submodules("uvicorn") + collect_submodules("arc_backend")
try:
    hidden += collect_submodules("pycaw") + collect_submodules("comtypes")
except Exception:
    pass

datas = collect_data_files("faster_whisper")
binaries = collect_dynamic_libs("ctranslate2")

a = Analysis(
    ["run_backend.py"],
    pathex=["."],
    hiddenimports=hidden + ["faster_whisper", "ctranslate2", "sounddevice", "tokenizers"],
    datas=datas,
    binaries=binaries,
    # onnxruntime is only used by faster-whisper's optional Silero VAD, which A.R.C. does not use
    # av (FFmpeg) is replaced by a stub: A.R.C. never decodes audio files; hf_xet is an optional HF uploader
    excludes=["tkinter", "pytest", "PIL", "onnxruntime", "matplotlib", "IPython", "av", "hf_xet"],
    runtime_hooks=["pyi_hooks/rth_av_stub.py"],
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
