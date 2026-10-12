"""CPU / RAM / GPU / disk metrics and the list of running programs."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Optional

import psutil

_BACKGROUND = {"system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
               "lsass.exe", "svchost.exe", "fontdrvhost.exe", "dwm.exe", "winlogon.exe", "sihost.exe",
               "taskhostw.exe", "ctfmon.exe", "runtimebroker.exe", "searchhost.exe", "startmenuexperiencehost.exe",
               "textinputhost.exe", "shellexperiencehost.exe", "applicationframehost.exe", "conhost.exe",
               "dllhost.exe", "smartscreen.exe", "securityhealthsystray.exe", "memory compression",
               "systemsettingsbroker.exe", "lockapp.exe", "widgets.exe", "searchindexer.exe", "spoolsv.exe",
               "audiodg.exe", "wmiprvse.exe", "msmpeng.exe", "nissrv.exe", "explorer.exe"}


class GpuProbe:
    """nvidia-smi based probe with caching; returns None when no NVIDIA GPU/driver is present."""

    def __init__(self, ttl_s: float = 3.0):
        self._ttl = ttl_s
        self._lock = threading.Lock()
        self._cached: tuple[float, Optional[dict[str, Any]]] = (0.0, None)
        self._exe = shutil.which("nvidia-smi")
        if not self._exe and sys.platform == "win32":
            candidate = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
            self._exe = candidate if os.path.exists(candidate) else None

    @property
    def available(self) -> bool:
        return self._exe is not None

    def read(self) -> Optional[dict[str, Any]]:
        if not self._exe:
            return None
        with self._lock:
            ts, value = self._cached
            if time.monotonic() - ts < self._ttl:
                return value
            value = self._query()
            self._cached = (time.monotonic(), value)
            return value

    def _query(self) -> Optional[dict[str, Any]]:
        try:
            out = subprocess.run(
                [self._exe, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        except (OSError, subprocess.TimeoutExpired):
            return None
        line = out.strip().splitlines()[0] if out.strip() else ""
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            return None
        try:
            return {"name": parts[0], "load": float(parts[1]), "mem_used_mb": float(parts[2]),
                    "mem_total_mb": float(parts[3]), "temp_c": float(parts[4])}
        except ValueError:
            return None


def stats(gpu: GpuProbe) -> dict[str, Any]:
    mem = psutil.virtual_memory()
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": {"percent": mem.percent, "used_gb": round(mem.used / 2**30, 1), "total_gb": round(mem.total / 2**30, 1)},
        "gpu": gpu.read(),
        "ts": time.time(),
    }


def disks() -> list[dict[str, Any]]:
    result = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        if usage.total < 2**30:
            continue  # tiny system/virtual mounts
        result.append({"mount": part.mountpoint, "free_gb": round(usage.free / 2**30, 1),
                       "total_gb": round(usage.total / 2**30, 1), "percent": usage.percent})
    return result


def running_programs(windowed: Optional[set[int]], limit: int = 20) -> list[dict[str, Any]]:
    """Distinct user programs; on Windows only processes with visible windows are listed."""
    try:
        me = psutil.Process().username()
    except psutil.Error:
        me = None
    programs: dict[str, dict[str, Any]] = {}
    for proc in psutil.process_iter(["pid", "name", "username", "memory_info"]):
        info = proc.info
        name = info.get("name") or ""
        if not name or name.lower() in _BACKGROUND:
            continue
        if windowed is not None:
            if info["pid"] not in windowed:
                continue
        elif me and info.get("username") != me:
            continue
        mem = info.get("memory_info")
        rss = mem.rss if mem else 0
        item = programs.setdefault(name.lower(), {"name": name, "pids": [], "memory_mb": 0.0})
        item["pids"].append(info["pid"])
        item["memory_mb"] += rss / 2**20
    items = sorted(programs.values(), key=lambda p: p["memory_mb"], reverse=True)[:limit]
    for item in items:
        item["memory_mb"] = round(item["memory_mb"], 1)
    return items
