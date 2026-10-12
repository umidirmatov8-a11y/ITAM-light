"""The release job publishes only when versions match and the changelog has the version."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release_notes.py")
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

from arc_backend import __version__  # noqa: E402


def test_current_version_is_releasable(tmp_path):
    out = tmp_path / "notes.md"
    assert release_notes.main(["--tag", f"arc-v{__version__}", "--out", str(out)]) == 0
    assert "Возможности" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("tag", ["v1.0.0", "arc-v1.0", "arc-v9.9.9", "arc-v1.0.0; rm -rf /"])
def test_wrong_tags_are_refused(tag, tmp_path):
    with pytest.raises(SystemExit):
        release_notes.main(["--tag", tag, "--out", str(tmp_path / "n.md")])
