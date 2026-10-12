"""Offline guarantee: a whole working session in LOCAL mode never opens a connection outside this
computer (the socket guard fails the test on any non-loopback connect)."""
from __future__ import annotations

import os

from arc_backend.models import Source, Status
from arc_backend.online.secrets import MemorySecretStore
from arc_backend.services import Services


def test_full_local_session_makes_no_external_connections(tmp_path, folders, controller, no_network):
    # real network stack (no fake transports): only the socket guard stands between A.R.C. and the internet
    svc = Services.create(tmp_path / "data", controller=controller, folders=lambda: folders,
                          secrets=MemorySecretStore())
    try:
        svc.settings.update({"safety": {"dry_run": False}, "ai": {"timeout_s": 3}})
        with open(os.path.join(folders["desktop"], "отчёт.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        script = [
            ("открой блокнот", {Status.DONE}),
            ("увеличь громкость на 10", {Status.DONE}),
            ("сверни все окна", {Status.DONE}),
            ("сколько свободного места на диске", {Status.DONE}),
            ("найди файл отчёт", {Status.DONE}),
            ("какие программы запущены", {Status.DONE}),
            ("найди в интернете курс валют", {Status.DENIED}),
            ("загугли погоду", {Status.DENIED}),
            ("абракадабра шмяк", {Status.UNKNOWN, Status.REPLY, Status.CLARIFY, Status.DONE}),
        ]
        for text, expected in script:
            response = svc.assistant.handle_text(text)
            assert response.status in expected, (text, response.status, response.message)
        # a document "with data from the internet" is refused in LOCAL; a plain one is created locally
        response = svc.assistant.handle_text("сделай презентацию про кошек с данными из интернета")
        done = svc.assistant.confirm(response.confirmation.id, True, Source.UI)
        assert done.status == Status.DENIED
        response = svc.assistant.handle_text("сделай презентацию про кошек")
        done = svc.assistant.confirm(response.confirmation.id, True, Source.UI)
        job = svc.documents.wait(done.data["job_id"], timeout=60)
        assert job.status == "done", job.message
        assert svc.online.status()["recent"] == [] or all(a["status"] == "refused" for a in svc.online.status()["recent"])
    finally:
        svc.close()
