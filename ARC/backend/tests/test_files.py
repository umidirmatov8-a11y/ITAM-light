import os
import sys

import pytest

from arc_backend.automation.files import PathError, PathGuard, is_executable, search_files, stem, validate_folder_name


def test_guard_allows_only_inside(tmp_path):
    allowed = tmp_path / "allowed"
    (allowed / "sub").mkdir(parents=True)
    other = tmp_path / "allowed_evil"
    other.mkdir()
    guard = PathGuard([str(allowed)])
    assert guard.check(str(allowed / "sub" / "file.txt"))
    assert guard.check(str(allowed))
    for path in (str(other / "x"), str(allowed / ".." / "x"), str(tmp_path), "relative/path", "", "C\x00:"):
        with pytest.raises(PathError):
            guard.check(path)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_guard_resolves_symlinks(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    secret = tmp_path / "secret"
    secret.mkdir()
    os.symlink(secret, allowed / "link")
    with pytest.raises(PathError):
        PathGuard([str(allowed)]).check(str(allowed / "link" / "x"))


def test_guard_with_no_dirs(tmp_path):
    with pytest.raises(PathError):
        PathGuard([]).check(str(tmp_path))


@pytest.mark.parametrize("name", ["", "a/b", "a\\b", "con", "NUL.txt", "x:y", "dot.", "a" * 200, "..", "ctl\x01name"])
def test_folder_name_rejected(name):
    with pytest.raises(PathError):
        validate_folder_name(name)


def test_folder_name_ok():
    assert validate_folder_name("  Новый   проект ") == "Новый проект"


def test_executable_detection():
    assert is_executable("C:\\x\\run.EXE") and is_executable("a.ps1") and is_executable("a.lnk")
    assert not is_executable("отчет.docx")


def test_stem():
    assert stem("отчётом") == "отчет"
    assert stem("презентации") == "презентаци"
    assert stem("budget") == "budget"


def test_search(tmp_path):
    (tmp_path / "a" / "node_modules").mkdir(parents=True)
    (tmp_path / "a" / "Отчёт.docx").write_text("x")
    (tmp_path / "a" / "node_modules" / "отчет.js").write_text("x")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "отчет.txt").write_text("x")
    for i in range(30):
        (tmp_path / f"отчет {i}.txt").write_text("x")
    results, truncated = search_files("отчетом", [str(tmp_path)], limit=50)
    names = {r.name for r in results}
    assert "Отчёт.docx" in names and "отчет.js" not in names and len(names) == 31 and not truncated
    results, truncated = search_files("отчет", [str(tmp_path)], limit=5)
    assert len(results) == 5 and truncated
