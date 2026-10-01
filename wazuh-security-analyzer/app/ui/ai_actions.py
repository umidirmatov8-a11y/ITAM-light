"""Running AI analysis from the GUI (with privacy confirmation)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QCheckBox, QMessageBox, QWidget

from app.ai.engine import EXTERNAL_WARNING, AIAnalysisEngine
from app.ai.providers.factory import PROVIDER_LABELS
from app.models.analysis import AlertGroup, Incident
from app.ui import workers
from app.ui.context import AppContext

_confirmed_this_session = {"value": False}


def confirm_external(parent: QWidget, ctx: AppContext, engine: AIAnalysisEngine) -> bool:
    if engine.provider is None or not engine.provider.is_external or _confirmed_this_session["value"]:
        return True
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("External AI provider")
    box.setText(EXTERNAL_WARNING)
    box.setInformativeText(
        f"Provider: {PROVIDER_LABELS.get(ctx.config.ai.provider)} ({engine.provider.model}).\n\n"
        "Usernames, hostnames, internal IPs, e-mails, domains and secrets will be replaced with placeholders "
        "before sending. Only the normalized context of this finding is sent - never the full log files.\n\n"
        "Continue?")
    remember = QCheckBox("Do not ask again until the application is restarted")
    box.setCheckBox(remember)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    if box.exec() != QMessageBox.Yes:
        return False
    if remember.isChecked():
        _confirmed_this_session["value"] = True
    return True


def run_ai(parent: QWidget, ctx: AppContext, groups: list[AlertGroup], incident: Incident | None,
           on_done: Callable[[dict], None], on_error: Callable[[str], None]) -> bool:
    session = ctx.session
    if session is None or not groups:
        return False
    engine = AIAnalysisEngine(ctx.config, ctx.secrets)
    if not engine.available:
        QMessageBox.information(parent, "AI analysis",
                                "AI analysis is disabled.\n\nChoose a provider in Settings › AI provider "
                                "(Ollama is recommended for confidential data). The local analysis engine works "
                                "without AI.")
        return False
    if not confirm_external(parent, ctx, engine):
        return False
    ioc_values = {(t, v) for g in groups for t, v, _ in g.ioc_items()}
    iocs = [r for r in session.store.iocs(include_internal=False, limit=5000) if (r.type, r.value) in ioc_values]
    cve_ids = {c for g in groups for c in g.cves}
    cves = [c for c in session.store.cves() if c.cve in cve_ids]

    def job(progress, cancel):
        return engine.analyze(groups, incident, iocs, cves)

    task = workers.Task(job)
    task.signals.finished.connect(lambda result: on_done(result.to_dict()))
    task.signals.failed.connect(on_error)
    workers.start(task)
    return True
