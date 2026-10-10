# PyInstaller runtime hook. faster-whisper imports PyAV (FFmpeg, ~125 MB) only to decode audio
# files; A.R.C. always passes raw 16 kHz samples, so the frozen build ships a stub instead.
import sys
import types

if "av" not in sys.modules:
    def _not_bundled(*_args, **_kwargs):
        raise RuntimeError("PyAV is not bundled with A.R.C.: decoding audio files is not supported")

    stub = types.ModuleType("av")
    stub.__getattr__ = lambda _name: _not_bundled  # type: ignore[attr-defined]
    sys.modules["av"] = stub
