"""Discovery of installed programs from trusted sources: Start menu shortcuts, Steam and Epic
libraries, and UWP apps registered in the Start menu. Nothing is launched during discovery."""
from __future__ import annotations

import json
import logging
import os
import re
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from ..router.text import normalize
from .matcher import default_aliases
from .registry import AppInput, AppKind, AppRegistry, LaunchType

log = logging.getLogger(__name__)

_SKIP_WORDS = ("uninstall", "удал", "readme", "read me", "help", "справк", "documentation", "license",
               "лиценз", "website", "web site", "release notes", "what's new", "setup", "remove", "repair",
               "manual", "руководство", "support", "поддержк", "changelog", "faq")
_STEAM_SKIP = re.compile(r"steamworks|redistributable|proton|steam linux runtime|steamvr|dedicated server|sdk",
                         re.IGNORECASE)


# --------------------------------------------------------------------------- .lnk
@dataclass
class ShellLink:
    target: Optional[str] = None
    arguments: str = ""
    working_dir: str = ""
    description: str = ""


def parse_lnk(data: bytes) -> ShellLink:
    """Minimal MS-SHLLINK reader: local target path, arguments, working directory."""
    link = ShellLink()
    if len(data) < 0x4C or struct.unpack_from("<I", data, 0)[0] != 0x4C:
        raise ValueError("not a shell link")
    flags = struct.unpack_from("<I", data, 0x14)[0]
    is_unicode = bool(flags & 0x80)
    pos = 0x4C
    if flags & 0x01:  # HasLinkTargetIDList
        pos += 2 + struct.unpack_from("<H", data, pos)[0]
    if flags & 0x02:  # HasLinkInfo
        info_size = struct.unpack_from("<I", data, pos)[0]
        info = data[pos:pos + info_size]
        header_size, info_flags, _vol, base_off, _net, suffix_off = struct.unpack_from("<IIIIII", info, 4)
        if info_flags & 0x01:
            if header_size >= 0x24:
                base_u, suffix_u = struct.unpack_from("<II", info, 28)
                base = _read_cstr_w(info, base_u) if base_u else _read_cstr(info, base_off)
                suffix = _read_cstr_w(info, suffix_u) if suffix_u else _read_cstr(info, suffix_off)
            else:
                base, suffix = _read_cstr(info, base_off), _read_cstr(info, suffix_off)
            link.target = base + suffix if suffix else base
        pos += info_size
    strings: dict[int, str] = {}
    for bit in (0x04, 0x08, 0x10, 0x20, 0x40):
        if flags & bit:
            count = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            size = count * (2 if is_unicode else 1)
            raw = data[pos:pos + size]
            strings[bit] = raw.decode("utf-16-le" if is_unicode else "mbcs" if sys.platform == "win32" else "latin-1",
                                      errors="replace")
            pos += size
    link.description = strings.get(0x04, "")
    link.working_dir = strings.get(0x10, "")
    link.arguments = strings.get(0x20, "")
    # ExtraData: EnvironmentVariableDataBlock (0xA0000001) holds targets like %ProgramFiles%\...
    while pos + 8 <= len(data):
        size = struct.unpack_from("<I", data, pos)[0]
        if size < 8 or pos + size > len(data):
            break
        signature = struct.unpack_from("<I", data, pos + 4)[0]
        if signature == 0xA0000001 and size >= 0x314 and not link.target:
            target = data[pos + 8 + 260:pos + 8 + 260 + 520].decode("utf-16-le", errors="ignore").split("\x00")[0]
            link.target = os.path.expandvars(target) if target else None
        pos += size
    return link


def _read_cstr(buf: bytes, offset: int) -> str:
    end = buf.find(b"\x00", offset)
    raw = buf[offset:end if end >= 0 else len(buf)]
    return raw.decode("mbcs" if sys.platform == "win32" else "latin-1", errors="replace")


def _read_cstr_w(buf: bytes, offset: int) -> str:
    out = bytearray()
    for i in range(offset, len(buf) - 1, 2):
        pair = buf[i:i + 2]
        if pair == b"\x00\x00":
            break
        out += pair
    return out.decode("utf-16-le", errors="replace")


def start_menu_dirs() -> list[Path]:
    dirs = []
    for env, sub in (("ProgramData", r"Microsoft\Windows\Start Menu\Programs"),
                     ("APPDATA", r"Microsoft\Windows\Start Menu\Programs")):
        base = os.environ.get(env)
        if base:
            dirs.append(Path(base) / sub)
    return [d for d in dirs if d.is_dir()]


def scan_shortcuts(dirs: Iterable[Path]) -> list[AppInput]:
    found: list[AppInput] = []
    for root in dirs:
        for path in sorted(root.rglob("*.lnk")):
            name = path.stem
            low = name.lower()
            if any(word in low for word in _SKIP_WORDS):
                continue
            try:
                link = parse_lnk(path.read_bytes())
            except (OSError, ValueError, struct.error) as exc:
                log.debug("skip %s: %s", path, exc)
                continue
            if link.target and not link.target.lower().endswith(".exe"):
                continue
            rel = path.parent.relative_to(root)
            category = rel.parts[0] if rel.parts else ""
            process = re.split(r"[\\/]", link.target)[-1] if link.target else ""
            try:
                found.append(AppInput(name=name, kind=AppKind.APP, category=category, launch_type=LaunchType.LNK,
                                      target=str(path), process_name=process, source="start_menu",
                                      aliases=default_aliases(name)))
            except ValueError:
                continue
    return found


# --------------------------------------------------------------------------- Steam
def parse_vdf(text: str) -> dict[str, Any]:
    """Valve KeyValues text format (libraryfolders.vdf, appmanifest_*.acf)."""
    tokens = re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text)
    stack: list[dict[str, Any]] = [{}]
    key: Optional[str] = None
    for quoted, brace in tokens:
        if brace == "{":
            child: dict[str, Any] = {}
            if key is None:
                raise ValueError("unexpected {")
            stack[-1][key] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) == 1:
                raise ValueError("unexpected }")
            stack.pop()
        else:
            value = quoted.replace('\\\\', '\\').replace('\\"', '"')
            if key is None:
                key = value
            else:
                stack[-1][key] = value
                key = None
    return stack[0]


def steam_root() -> Optional[Path]:
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            value, _ = winreg.QueryValueEx(key, "SteamPath")
            path = Path(value)
            return path if path.is_dir() else None
    except OSError:
        return None


def scan_steam(root: Optional[Path]) -> list[AppInput]:
    if root is None:
        return []
    libraries = {root}
    lib_file = root / "steamapps" / "libraryfolders.vdf"
    if lib_file.is_file():
        try:
            data = parse_vdf(lib_file.read_text(encoding="utf-8", errors="replace"))
            for entry in data.get("libraryfolders", {}).values():
                if isinstance(entry, dict) and entry.get("path"):
                    libraries.add(Path(entry["path"]))
        except ValueError as exc:
            log.warning("libraryfolders.vdf: %s", exc)
    found: list[AppInput] = []
    for library in sorted(libraries):
        for manifest in sorted((library / "steamapps").glob("appmanifest_*.acf")):
            try:
                state = parse_vdf(manifest.read_text(encoding="utf-8", errors="replace")).get("AppState", {})
            except (OSError, ValueError):
                continue
            appid, name = state.get("appid"), state.get("name")
            if not appid or not name or not str(appid).isdigit() or _STEAM_SKIP.search(name):
                continue
            found.append(AppInput(name=name, kind=AppKind.GAME, category="Steam", launch_type=LaunchType.PROTOCOL,
                                  target=f"steam://rungameid/{appid}", source="steam", aliases=default_aliases(name)))
    return found


# --------------------------------------------------------------------------- Epic
def epic_manifest_dir() -> Optional[Path]:
    base = os.environ.get("ProgramData")
    if not base:
        return None
    path = Path(base) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    return path if path.is_dir() else None


def scan_epic(manifest_dir: Optional[Path]) -> list[AppInput]:
    if manifest_dir is None:
        return []
    found: list[AppInput] = []
    for item in sorted(manifest_dir.glob("*.item")):
        try:
            data = json.loads(item.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        name, app, ns, cat = (data.get("DisplayName"), data.get("AppName"), data.get("CatalogNamespace"),
                              data.get("CatalogItemId"))
        if not all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_\-.]+", v) for v in (app, ns, cat)) or not name:
            continue
        exe = str(data.get("LaunchExecutable") or "")
        try:
            found.append(AppInput(
                name=name, kind=AppKind.GAME, category="Epic Games", launch_type=LaunchType.PROTOCOL,
                target=f"com.epicgames.launcher://apps/{ns}%3A{cat}%3A{app}?action=launch&silent=true",
                process_name=re.split(r"[\\/]", exe)[-1] if exe.lower().endswith(".exe") else "",
                source="epic", aliases=default_aliases(name)))
        except ValueError:
            continue
    return found


# --------------------------------------------------------------------------- UWP
def scan_uwp(timeout: float = 25.0) -> list[AppInput]:
    """Get-StartApps lists Store apps with their AppUserModelID. Fixed command, no user input."""
    if sys.platform != "win32":
        return []
    command = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
               "Get-StartApps | Where-Object { $_.AppID -like '*!*' } | Select-Object Name, AppID | ConvertTo-Json -Compress")
    try:
        proc = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-Command", command], capture_output=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("Get-StartApps failed: %s", exc)
        return []
    return parse_start_apps(proc.stdout.decode("utf-8", errors="replace"))


def parse_start_apps(output: str) -> list[AppInput]:
    output = output.strip()
    if not output:
        return []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    found = []
    for item in data:
        name, aumid = item.get("Name"), item.get("AppID")
        if not name or not aumid:
            continue
        try:
            found.append(AppInput(name=name, kind=AppKind.APP, category="Microsoft Store", launch_type=LaunchType.UWP,
                                  target=aumid, source="uwp", aliases=default_aliases(name)))
        except ValueError:
            continue
    return found


# --------------------------------------------------------------------------- orchestration
@dataclass
class DiscoveryReport:
    added: list[str] = field(default_factory=list)
    skipped: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def discover_all() -> list[AppInput]:
    items: list[AppInput] = []
    for name, scan in (("steam", lambda: scan_steam(steam_root())), ("epic", lambda: scan_epic(epic_manifest_dir())),
                       ("start_menu", lambda: scan_shortcuts(start_menu_dirs())), ("uwp", scan_uwp)):
        try:
            items.extend(scan())
        except Exception as exc:  # one broken source must not break the others
            log.exception("discovery source %s failed: %s", name, exc)
    return items


def import_discovered(registry: AppRegistry, items: Iterable[AppInput]) -> DiscoveryReport:
    report = DiscoveryReport()
    known_names = {normalize(e.name) for e in registry.list()}
    for item in items:
        key = normalize(item.name)
        if key in known_names or registry.find_by_target(item.launch_type, item.target):
            report.skipped += 1
            continue
        try:
            registry.add(item)
        except ValueError as exc:
            report.errors.append(f"{item.name}: {exc}")
            continue
        known_names.add(key)
        report.added.append(item.name)
        report.by_source[item.source] = report.by_source.get(item.source, 0) + 1
    return report
