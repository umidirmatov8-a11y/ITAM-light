"""Filesystem locations used by the backend."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """Per-user data directory (%LOCALAPPDATA%\\ARC on Windows). ARC_DATA_DIR overrides it."""
    override = os.environ.get("ARC_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / "ARC"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "arc"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def known_folders() -> dict[str, Path]:
    """User folders that can be referenced by voice ("на рабочем столе", "в документах")."""
    home = Path.home()
    folders = {
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "downloads": home / "Downloads",
        "pictures": home / "Pictures",
        "music": home / "Music",
        "videos": home / "Videos",
    }
    if sys.platform == "win32":
        folders.update(_windows_known_folders(folders))
    return folders


def _windows_known_folders(defaults: dict[str, Path]) -> dict[str, Path]:
    """Resolve redirected folders (OneDrive "Рабочий стол" etc.) via SHGetKnownFolderPath."""
    import ctypes
    from ctypes import wintypes
    import uuid

    ids = {
        "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
        "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
        "downloads": "374DE290-123F-4565-9164-39C4925E467B",
        "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
        "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
        "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
    }

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    result: dict[str, Path] = {}
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    for key, text in ids.items():
        raw = uuid.UUID(text).bytes_le
        guid = GUID.from_buffer_copy(raw)
        ptr = ctypes.c_wchar_p()
        try:
            if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ptr)) == 0:
                result[key] = Path(ptr.value)
        except OSError:
            result[key] = defaults[key]
        finally:
            if ptr:
                ole32.CoTaskMemFree(ptr)
    return result
