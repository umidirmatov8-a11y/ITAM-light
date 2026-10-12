# PyInstaller spec: onedir build of the backend, placed by electron-builder into resources/backend.
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

hidden = collect_submodules("uvicorn") + collect_submodules("arc_backend")
try:
    hidden += collect_submodules("pycaw") + collect_submodules("comtypes")
except Exception:
    pass

datas = collect_data_files("faster_whisper") + collect_data_files("mediapipe")
# document templates (default.pptx, default.docx) and ReportLab resources
datas += collect_data_files("pptx") + collect_data_files("docx") + collect_data_files("reportlab")
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("mediapipe")

a = Analysis(
    ["run_backend.py"],
    pathex=["."],
    hiddenimports=hidden + ["faster_whisper", "ctranslate2", "sounddevice", "tokenizers", "cv2",
                            "mediapipe.tasks.python.vision", "pptx", "docx", "openpyxl", "pypdf",
                            "reportlab.pdfbase.ttfonts", "reportlab.platypus"]
                  + collect_submodules("mediapipe.tasks.python"),
    datas=datas,
    binaries=binaries,
    # onnxruntime is only used by faster-whisper's optional Silero VAD, which A.R.C. does not use
    # av (FFmpeg) and matplotlib are replaced by stubs (see pyi_hooks/rth_stubs.py); hf_xet is an optional HF uploader
    excludes=["tkinter", "pytest", "onnxruntime", "matplotlib", "IPython", "av", "hf_xet"],
    runtime_hooks=["pyi_hooks/rth_stubs.py"],
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
