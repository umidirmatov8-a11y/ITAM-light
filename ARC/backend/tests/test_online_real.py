"""Real internet (runs in CI with ARC_TEST_ONLINE=1). Wikipedia must work; DuckDuckGo is reported only,
because it may rate-limit shared CI addresses."""
import os

import pytest

from arc_backend.automation.controller import MockController
from arc_backend.models import Status
from arc_backend.online.client import OnlineError
from arc_backend.online.secrets import MemorySecretStore
from arc_backend.services import Services

from conftest import offline_planner, refusing_transport

pytestmark = pytest.mark.skipif(not os.environ.get("ARC_TEST_ONLINE"), reason="ARC_TEST_ONLINE not set")


@pytest.fixture
def svc(tmp_path):
    services = Services.create(tmp_path / "data", controller=MockController(), folders=lambda: {"desktop": str(tmp_path)},
                               planner=offline_planner(), ai_transport=refusing_transport(), secrets=MemorySecretStore())
    services.settings.update({"network": {"mode": "ONLINE"}})
    yield services
    services.close()


def test_wikipedia(svc):
    svc.settings.update({"online": {"providers": ["wikipedia"]}})
    report = svc.research.search("квантовый компьютер")
    for r in report.results:
        print(f"  {r.title} — {r.url}\n    {r.snippet[:120]}")
    assert report.results, report.errors
    assert all(r.url.startswith("https://ru.wikipedia.org/") for r in report.results)
    assert any("кубит" in r.snippet.lower() or "квант" in r.title.lower() for r in report.results)


def test_duckduckgo_report(svc):
    svc.settings.update({"online": {"providers": ["duckduckgo"]}})
    try:
        report = svc.research.search("python programming language")
        print(f"DuckDuckGo: {len(report.results)} results")
        for r in report.results[:3]:
            print(f"  {r.title} — {r.url}")
        assert all(r.url.startswith(("http://", "https://")) for r in report.results)
    except OnlineError as exc:
        print(f"DuckDuckGo unavailable from CI: {exc}")


def test_command_end_to_end(svc):
    response = svc.assistant.handle_text("найди в интернете столица Австралии")
    print(response.message)
    assert response.status == Status.DONE, response.message
    assert response.data["research"]["results"]
    hosts = {e["params"]["host"] for e in svc.journal.audit_entries() if e["action"] == "net.request"}
    assert "ru.wikipedia.org" in hosts
