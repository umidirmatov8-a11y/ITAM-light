# PyInstaller runtime hook: stubs for heavy optional dependencies that A.R.C. never calls.
#  * av (PyAV/FFmpeg, ~125 MB): faster-whisper imports it only to decode audio files; A.R.C.
#    always passes raw 16 kHz samples.
#  * matplotlib (~30 MB): MediaPipe imports it only for a 3D plotting helper.
# Calling anything on a stub raises a clear error instead of crashing at import time.
import sys
import types


def _stub(name):
    def _not_bundled(*_args, **_kwargs):
        raise RuntimeError(f"{name} is not bundled with A.R.C.")

    module = types.ModuleType(name)
    module.__getattr__ = lambda _attr: _not_bundled  # type: ignore[attr-defined]
    return module


for _name in ("av", "matplotlib", "matplotlib.pyplot"):
    if _name not in sys.modules:
        sys.modules[_name] = _stub(_name)
sys.modules["matplotlib"].pyplot = sys.modules["matplotlib.pyplot"]  # type: ignore[attr-defined]
