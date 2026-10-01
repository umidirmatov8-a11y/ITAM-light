"""Discovery and safe opening of input files, folders, ZIP and GZIP archives.

Archives are never extracted to disk: members are streamed directly through a
size-capped reader.  This removes the Zip Slip class of vulnerabilities entirely,
and suspicious member names are still rejected and reported.  Decompression bombs
are stopped by enforcing the per-file limit, the total archive limit and the
compression-ratio limit on the *actual* decompressed byte count, not on the sizes
declared in archive headers (which an attacker controls).
"""

from __future__ import annotations

import gzip
import io
import logging
import os
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable

from app.core.config import LimitsConfig
from app.core.errors import InputRejectedError

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".ndjson", ".log", ".txt", ".csv", ".xml", ".cef", ".tsv"}
ARCHIVE_EXTENSIONS = {".zip", ".gz"}
MB = 1024 * 1024


class CappedReader(io.RawIOBase):
    """Read-only stream wrapper that enforces byte and compression-ratio limits."""

    def __init__(self, raw: BinaryIO, max_bytes: int, name: str, compressed_size: int | None = None,
                 max_ratio: int | None = None, on_close: Callable[[], None] | None = None,
                 shared_budget: "ArchiveBudget | None" = None):
        super().__init__()
        self._raw = raw
        self._max = max_bytes
        self._name = name
        self._compressed = compressed_size
        self._ratio = max_ratio
        self._on_close = on_close
        self._budget = shared_budget
        self.bytes_read = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        data = self._raw.read(len(buffer))
        n = len(data)
        if not n:
            return 0
        self.bytes_read += n
        if self.bytes_read > self._max:
            raise InputRejectedError(f"{self._name}: exceeds the maximum allowed size of {self._max // MB} MB")
        if self._compressed and self._ratio and self.bytes_read > 10 * MB:
            if self.bytes_read / max(self._compressed, 1) > self._ratio:
                raise InputRejectedError(
                    f"{self._name}: compression ratio exceeds {self._ratio}:1 (possible decompression bomb)")
        if self._budget is not None:
            self._budget.consume(n, self._name)
        buffer[:n] = data
        return n

    def close(self) -> None:
        if not self.closed:
            try:
                self._raw.close()
            finally:
                if self._on_close:
                    self._on_close()
        super().close()


class ArchiveBudget:
    """Total decompressed byte budget shared by all members of one archive."""

    def __init__(self, max_total: int):
        self.max_total = max_total
        self.used = 0

    def consume(self, n: int, name: str) -> None:
        self.used += n
        if self.used > self.max_total:
            raise InputRejectedError(
                f"{name}: archive exceeds the total decompressed limit of {self.max_total // MB} MB")


@dataclass
class InputSource:
    display_name: str
    size: int
    opener: Callable[[], BinaryIO]
    origin: str
    is_compressed: bool = False

    def open(self) -> BinaryIO:
        return self.opener()


@dataclass
class DiscoveryResult:
    sources: list[InputSource] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(s.size for s in self.sources)


def _is_unsafe_member_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        return True
    parts = PurePosixPath(normalized).parts
    return any(part == ".." for part in parts)


def _gzip_uncompressed_size(path: Path) -> int:
    """Read the ISIZE trailer (size modulo 2**32). Used only for progress estimation."""
    try:
        with path.open("rb") as fh:
            fh.seek(-4, os.SEEK_END)
            return struct.unpack("<I", fh.read(4))[0]
    except OSError:
        return path.stat().st_size * 8


def _extension(name: str) -> str:
    return Path(name).suffix.lower()


class SourceDiscovery:
    def __init__(self, limits: LimitsConfig):
        self.limits = limits
        self.max_file = limits.max_file_size_mb * MB
        self.max_total = limits.max_archive_total_mb * MB

    def discover(self, paths: list[str | Path]) -> DiscoveryResult:
        result = DiscoveryResult()
        files: list[tuple[Path, bool]] = []  # (path, explicitly_selected)
        for raw in paths:
            path = Path(raw)
            if not path.exists():
                result.rejected.append(f"{path}: file not found")
                continue
            if path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file() and not any(p.startswith(".") for p in child.relative_to(path).parts):
                        ext = _extension(child.name)
                        if ext in SUPPORTED_EXTENSIONS or ext in ARCHIVE_EXTENSIONS:
                            files.append((child, False))
            else:
                files.append((path, True))
        if len(files) > self.limits.max_files:
            result.warnings.append(
                f"{len(files)} files found; only the first {self.limits.max_files} will be analyzed")
            files = files[: self.limits.max_files]

        for path, explicit in files:
            try:
                self._add_file(path, explicit, result)
            except InputRejectedError as exc:
                result.rejected.append(str(exc))
            except (OSError, zipfile.BadZipFile, EOFError) as exc:
                result.rejected.append(f"{path.name}: cannot be read ({exc})")
        return result

    def _add_file(self, path: Path, explicit: bool, result: DiscoveryResult) -> None:
        size = path.stat().st_size
        ext = _extension(path.name)
        if ext == ".zip":
            self._add_zip(path, result)
            return
        if size > self.max_file:
            raise InputRejectedError(f"{path.name}: {size // MB} MB exceeds the {self.max_file // MB} MB file limit")
        if ext == ".gz":
            inner_name = path.name[:-3]
            uncompressed = _gzip_uncompressed_size(path)

            def open_gz(p=path, compressed=size, name=inner_name):
                return io.BufferedReader(CappedReader(gzip.open(p, "rb"), self.max_file, name,
                                                      compressed_size=compressed,
                                                      max_ratio=self.limits.max_compression_ratio),
                                         buffer_size=1 << 20)

            result.sources.append(InputSource(inner_name, uncompressed, open_gz, str(path), True))
            return
        if ext not in SUPPORTED_EXTENSIONS and not explicit:
            return
        if ext not in SUPPORTED_EXTENSIONS:
            result.warnings.append(f"{path.name}: unknown extension, format will be auto-detected")

        def open_plain(p=path, name=path.name):
            return io.BufferedReader(CappedReader(p.open("rb"), self.max_file, name), buffer_size=1 << 20)

        result.sources.append(InputSource(path.name, size, open_plain, str(path)))

    def _add_zip(self, path: Path, result: DiscoveryResult) -> None:
        if not zipfile.is_zipfile(path):
            raise InputRejectedError(f"{path.name}: not a valid ZIP archive")
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
        if len(infos) > self.limits.max_archive_entries:
            raise InputRejectedError(
                f"{path.name}: {len(infos)} entries exceed the limit of {self.limits.max_archive_entries}")
        declared_total = 0
        budget = ArchiveBudget(self.max_total)
        for info in infos:
            if info.is_dir():
                continue
            label = f"{path.name}:{info.filename}"
            if _is_unsafe_member_name(info.filename):
                result.rejected.append(f"{label}: unsafe path in archive (path traversal attempt) - skipped")
                continue
            if info.flag_bits & 0x1:
                result.rejected.append(f"{label}: encrypted archive member - skipped")
                continue
            ext = _extension(info.filename)
            if ext == ".zip":
                result.warnings.append(f"{label}: nested ZIP archives are not processed")
                continue
            if ext not in SUPPORTED_EXTENSIONS and ext != ".gz":
                continue
            if info.file_size > self.max_file:
                result.rejected.append(f"{label}: declared size exceeds the per-file limit - skipped")
                continue
            if info.compress_size and info.file_size > 10 * MB and \
                    info.file_size / info.compress_size > self.limits.max_compression_ratio:
                result.rejected.append(f"{label}: compression ratio too high (possible ZIP bomb) - skipped")
                continue
            declared_total += info.file_size
            if declared_total > self.max_total:
                raise InputRejectedError(
                    f"{path.name}: total uncompressed size exceeds {self.max_total // MB} MB (possible ZIP bomb)")

            def open_member(p=path, member=info.filename, csize=info.compress_size, name=label,
                            gz=(ext == ".gz")):
                zf = zipfile.ZipFile(p)
                try:
                    stream: BinaryIO = zf.open(member, "r")
                    if gz:
                        stream = gzip.GzipFile(fileobj=stream, mode="rb")  # type: ignore[assignment]
                    capped = CappedReader(stream, self.max_file, name, compressed_size=csize,
                                          max_ratio=self.limits.max_compression_ratio, on_close=zf.close,
                                          shared_budget=budget)
                    return io.BufferedReader(capped, buffer_size=1 << 20)
                except Exception:
                    zf.close()
                    raise

            display = info.filename[:-3] if ext == ".gz" else info.filename
            est = info.file_size * (8 if ext == ".gz" else 1)
            result.sources.append(InputSource(f"{path.name}/{display}", est, open_member, str(path), True))
