"""Regression tests for the issues found in the stage 6 security review (docs/SECURITY_REVIEW.md)."""
from __future__ import annotations

import csv
import io
import os

import httpx
import pytest

from arc_backend.automation.files import is_executable
from arc_backend.models import Status
from arc_backend.online.client import OnlineError
from arc_backend.online.secrets import MemorySecretStore
from arc_backend.services import Services

from conftest import offline_planner, refusing_transport


def test_audit_csv_export_cannot_carry_formulas(services):
    services.assistant.handle_text('=HYPERLINK("http://evil.example","x")')
    services.assistant.handle_text("@SUM(1+1)*cmd|' /C calc'!A0")
    services.journal.audit(action="test", params={}, risk="A", source="text", decision="allow", status="done",
                           message="=1+2")
    rows = list(csv.reader(io.StringIO(services.journal.export("csv"))))
    for row in rows[1:]:
        for cell in row:
            assert not cell.startswith(("=", "+", "-", "@")), cell
    assert any(cell == "'=1+2" for row in rows for cell in row)


@pytest.mark.parametrize("name", ["report.docm", "book.xlsm", "deck.pptm", "help.chm", "disk.iso", "x.msc",
                                  "a.settingcontent-ms", "b.appref-ms", "c.library-ms", "d.scf", "e.theme",
                                  "f.CMD", "g.vhdx", "h.xll", "i.one"])
def test_risky_file_types_are_not_opened(name):
    assert is_executable(name)


def test_files_open_refuses_macro_documents(services, folders, controller):
    path = os.path.join(folders["documents"], "отчёт.docm")
    with open(path, "wb") as fh:
        fh.write(b"PK")
    services.settings.update({"safety": {"dry_run": False}})
    from arc_backend.models import ActionRequest, Source
    response = services.assistant.run_action(ActionRequest(action="files.open", params={"path": path},
                                                           source=Source.UI))
    assert response.status == Status.DENIED and not controller.called("shell_open")


def redirecting_net(requests: list):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.host == "hop.example":
            return httpx.Response(302, headers={"Location": "http://plain.example/leak?q=secret"})
        if request.url.host == "ok-hop.example":
            return httpx.Response(301, headers={"Location": "https://final.example/page"})
        if request.url.host == "loop.example":
            return httpx.Response(302, headers={"Location": "https://loop.example/again"})
        return httpx.Response(200, text="ok")
    return httpx.MockTransport(handler)


def test_intermediate_redirect_to_http_is_never_followed(tmp_path, folders, controller):
    seen: list = []
    svc = Services.create(tmp_path / "data", controller=controller, folders=lambda: folders, planner=offline_planner(),
                          online_transport=redirecting_net(seen), ai_transport=refusing_transport(),
                          secrets=MemorySecretStore())
    try:
        svc.settings.update({"network": {"mode": "ONLINE"}})
        with pytest.raises(OnlineError, match="https"):
            svc.online.request("test", "GET", "https://hop.example/")
        assert not any(url.startswith("http://") for url in seen)
        assert svc.online.request("test", "GET", "https://ok-hop.example/").text == "ok"
        assert seen[-1] == "https://final.example/page"
        with pytest.raises(OnlineError, match="перенаправлений"):
            svc.online.request("test", "GET", "https://loop.example/")
    finally:
        svc.close()
