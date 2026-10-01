import os
import sys
import time
from pathlib import Path

import pytest

from app.core.config import AppConfig
from app.services.pipeline import AnalysisPipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from generate_large_dataset import write  # noqa: E402


@pytest.mark.slow
def test_100k_alerts(tmp_path):
    path = write(tmp_path / "big.json.gz", 100_000, use_gzip=True)
    progress = []
    started = time.time()
    session = AnalysisPipeline(AppConfig(), workspace=tmp_path / "ws", progress=progress.append).run([path])
    elapsed = time.time() - started
    s = session.summary
    assert s.events == 100_000 and s.parse_errors == 0
    assert s.agents == 200 and s.incidents > 0
    assert elapsed < 180, f"100k alerts took {elapsed:.1f}s"
    # GUI paging stays fast on large data
    t = time.time()
    rows = session.store.query_alerts(None, "high", "", 50_000, 500)
    assert time.time() - t < 2.0 and len(rows) <= 500
    assert session.store.count_alerts() == 100_000
    parse_updates = [p for p in progress if p.stage == "parse" and p.processed]
    assert parse_updates and parse_updates[-1].total
    print(f"\n100k alerts analyzed in {elapsed:.1f}s")
    session.close()


@pytest.mark.slow
@pytest.mark.skipif(not os.environ.get("WSA_TEST_1M"), reason="set WSA_TEST_1M=1 to run the 1M alert test")
def test_1m_alerts(tmp_path):
    path = write(tmp_path / "huge.json.gz", 1_000_000, use_gzip=True)
    started = time.time()
    session = AnalysisPipeline(AppConfig(), workspace=tmp_path / "ws").run([path])
    print(f"\n1M alerts analyzed in {time.time() - started:.1f}s")
    assert session.summary.events == 1_000_000
    session.close()
