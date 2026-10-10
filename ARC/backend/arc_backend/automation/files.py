"""File operations restricted to user-approved directories."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..router.text import normalize

_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SKIP_DIRS = {"node_modules", "$recycle.bin", "appdata", "system volume information", ".git", "__pycache__",
              "windows", "program files", "program files (x86)", "programdata"}
_EXECUTABLE = {".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".msi",
               ".msp", ".scr", ".pif", ".hta", ".cpl", ".reg", ".lnk", ".url", ".jar", ".psm1", ".dll", ".sys"}


class PathError(ValueError):
    """User-facing path validation error."""


def _norm(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


@dataclass
class PathGuard:
    allowed_dirs: list[str]

    def roots(self) -> list[str]:
        return [_norm(d) for d in self.allowed_dirs if d and os.path.isabs(d)]

    def check(self, path: str) -> str:
        """Returns the resolved path if it lies inside an allowed directory, else raises PathError."""
        if not path or "\x00" in path:
            raise PathError("Пустой или некорректный путь")
        if not os.path.isabs(path):
            raise PathError("Нужен абсолютный путь")
        resolved = _norm(path)
        for root in self.roots():
            if resolved == root or resolved.startswith(root.rstrip(os.sep) + os.sep):
                return os.path.realpath(os.path.abspath(path))
        raise PathError("Путь вне разрешённых каталогов. Добавьте каталог в «Разрешения → Каталоги».")


def validate_folder_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise PathError("Имя папки пустое")
    if len(name) > 120:
        raise PathError("Имя папки слишком длинное")
    if _BAD_CHARS.search(name) or name in (".", "..") or name.endswith((".", " ")):
        raise PathError('Имя папки содержит недопустимые символы (< > : " / \\ | ? *)')
    if _RESERVED.match(name):
        raise PathError("Это имя зарезервировано Windows")
    return name


def is_executable(path: str) -> bool:
    return Path(path).suffix.lower() in _EXECUTABLE


_ENDINGS = sorted(["ами", "ями", "ого", "его", "ому", "ему", "ыми", "ими", "ом", "ем", "ах", "ях", "ов", "ев",
                   "ей", "ой", "ий", "ый", "ая", "яя", "ое", "ее", "ую", "юю", "ам", "ям", "а", "я", "у", "ю",
                   "е", "ы", "и", "о", "ь"], key=len, reverse=True)


def stem(word: str) -> str:
    """Very small Russian stemmer: "отчётом" → "отчет", "презентации" → "презентац"."""
    word = normalize(word)
    if not re.search(r"[а-я]", word):
        return word
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[: -len(ending)]
    return word


@dataclass
class FoundFile:
    path: str
    name: str
    size: int
    modified: float
    is_dir: bool


def search_files(query: str, roots: Iterable[str], *, limit: int = 20, max_depth: int = 6,
                 time_budget_s: float = 5.0, max_entries: int = 60000) -> tuple[list[FoundFile], bool]:
    """Case-insensitive search by name fragments. Returns (results, truncated)."""
    tokens = [stem(t) for t in normalize(query).split() if len(t) >= 2]
    if not tokens:
        return [], False
    deadline = time.monotonic() + time_budget_s
    results: list[FoundFile] = []
    seen = 0
    truncated = False
    stack: list[tuple[str, int]] = [(r, 0) for r in roots if os.path.isdir(r)]
    while stack:
        current, depth = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    seen += 1
                    if seen > max_entries or time.monotonic() > deadline:
                        return _sorted(results), True
                    name = entry.name
                    if name.startswith((".", "~$")):
                        continue
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir and name.lower() in _SKIP_DIRS:
                        continue
                    hay = normalize(name)
                    if all(t in hay for t in tokens):
                        try:
                            st = entry.stat(follow_symlinks=False)
                            results.append(FoundFile(entry.path, name, st.st_size, st.st_mtime, is_dir))
                        except OSError:
                            pass
                        if len(results) >= limit:
                            truncated = True
                            return _sorted(results), truncated
                    if is_dir and depth + 1 < max_depth and not entry.is_symlink():
                        stack.append((entry.path, depth + 1))
        except OSError:
            continue
    return _sorted(results), truncated


def _sorted(items: list[FoundFile]) -> list[FoundFile]:
    return sorted(items, key=lambda f: f.modified, reverse=True)
