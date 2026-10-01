import gzip
import io
import zipfile

import pytest

from app.core.config import LimitsConfig
from app.core.errors import InputRejectedError
from app.parsers.sources import SourceDiscovery


def read_all(source) -> bytes:
    with source.open() as fh:
        return fh.read()


def test_plain_file_and_folder(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.log").write_text("x")
    (tmp_path / "ignored.exe").write_text("x")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "c.json").write_text("{}")
    result = SourceDiscovery(LimitsConfig()).discover([tmp_path])
    names = sorted(s.display_name for s in result.sources)
    assert names == ["a.json", "b.log"]


def test_missing_file_rejected(tmp_path):
    result = SourceDiscovery(LimitsConfig()).discover([tmp_path / "nope.json"])
    assert not result.sources and "not found" in result.rejected[0]


def test_zip_members_streamed(tmp_path):
    zpath = tmp_path / "logs.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("alerts/a.json", '{"rule": {"id": "1"}}')
        zf.writestr("readme.pdf", "binary")
        zf.writestr("inner.json.gz", gzip.compress(b'{"x": 1}'))
    result = SourceDiscovery(LimitsConfig()).discover([zpath])
    names = sorted(s.display_name for s in result.sources)
    assert names == ["logs.zip/alerts/a.json", "logs.zip/inner.json"]
    data = {s.display_name: read_all(s) for s in result.sources}
    assert data["logs.zip/inner.json"] == b'{"x": 1}'


def test_zip_slip_member_rejected(tmp_path):
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../../../../tmp/evil.json", "{}")
        zf.writestr("/abs/path.json", "{}")
        zf.writestr("C:/windows/x.json", "{}")
        zf.writestr("ok.json", "{}")
    result = SourceDiscovery(LimitsConfig()).discover([zpath])
    assert [s.display_name for s in result.sources] == ["evil.zip/ok.json"]
    assert sum("path traversal" in r for r in result.rejected) == 3
    # nothing was written outside (we never extract)
    assert not (tmp_path.parent / "tmp" / "evil.json").exists()


def test_zip_bomb_ratio_rejected(tmp_path):
    zpath = tmp_path / "bomb.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.json", b"0" * (60 * 1024 * 1024))
    result = SourceDiscovery(LimitsConfig(max_compression_ratio=100)).discover([zpath])
    assert not result.sources
    assert "ratio" in result.rejected[0]


def test_zip_total_size_limit(tmp_path):
    zpath = tmp_path / "huge.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as zf:
        for i in range(3):
            zf.writestr(f"f{i}.json", b"x" * (600 * 1024))
    result = SourceDiscovery(LimitsConfig(max_archive_total_mb=1)).discover([zpath])
    assert not result.sources
    assert "total uncompressed size" in result.rejected[0]


def test_zip_lying_header_stopped_by_actual_bytes(tmp_path):
    """Declared sizes are not trusted: the reader enforces the limit on actual output."""
    zpath = tmp_path / "data.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.json", b"y" * (3 * 1024 * 1024))
    disc = SourceDiscovery(LimitsConfig(max_file_size_mb=10))
    result = disc.discover([zpath])
    disc.max_file = 1 * 1024 * 1024  # simulate a header that under-reports the size
    source = result.sources[0]
    with pytest.raises(InputRejectedError):
        read_all(source)


def test_too_many_entries(tmp_path):
    zpath = tmp_path / "many.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for i in range(20):
            zf.writestr(f"{i}.json", "{}")
    result = SourceDiscovery(LimitsConfig(max_archive_entries=10)).discover([zpath])
    assert not result.sources and "entries" in result.rejected[0]


def test_nested_zip_warning(tmp_path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("x.json", "{}")
    zpath = tmp_path / "outer.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("inner.zip", inner.getvalue())
    result = SourceDiscovery(LimitsConfig()).discover([zpath])
    assert not result.sources and "nested ZIP" in result.warnings[0]


def test_gzip_file_and_bomb(tmp_path):
    good = tmp_path / "alerts.json.gz"
    good.write_bytes(gzip.compress(b'{"a": 1}\n'))
    bomb = tmp_path / "bomb.json.gz"
    bomb.write_bytes(gzip.compress(b"\0" * (40 * 1024 * 1024)))
    result = SourceDiscovery(LimitsConfig(max_compression_ratio=50)).discover([good, bomb])
    by_name = {s.display_name: s for s in result.sources}
    assert read_all(by_name["alerts.json"]) == b'{"a": 1}\n'
    with pytest.raises(InputRejectedError):
        read_all(by_name["bomb.json"])


def test_oversized_file_rejected(tmp_path):
    big = tmp_path / "big.json"
    big.write_bytes(b"x" * (2 * 1024 * 1024))
    result = SourceDiscovery(LimitsConfig(max_file_size_mb=1)).discover([big])
    assert not result.sources and "exceeds" in result.rejected[0]


def test_corrupt_zip(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"PK\x03\x04garbage")
    result = SourceDiscovery(LimitsConfig()).discover([bad])
    assert not result.sources and result.rejected
