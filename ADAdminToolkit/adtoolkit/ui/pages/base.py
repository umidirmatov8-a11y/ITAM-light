"""Base class for main-window pages."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..widgets.common import ask_export_path, report_meta, write_report

if TYPE_CHECKING:  # pragma: no cover
    from ..main_window import MainWindow


class BasePage(QWidget):
    title = ""
    subtitle = ""
    needs_connection = True

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(16, 12, 16, 12)
        self.root.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel(self.title)
        t.setObjectName("PageTitle")
        head.addWidget(t)
        if self.subtitle:
            s = QLabel(self.subtitle)
            s.setObjectName("Muted")
            head.addWidget(s)
        head.addStretch(1)
        self.header_actions = head
        self.root.addLayout(head)
        self._loaded_once = False

    # ---------------------------------------------------------------------------------------------------------
    @property
    def ctx(self):
        return self.win.ctx

    @property
    def db(self):
        return self.win.db

    def connected(self) -> bool:
        return self.win.ctx is not None

    def need_ctx(self) -> bool:
        if self.win.ctx is None:
            self.win.toast("Нет подключения к Active Directory. Подключитесь к домену или запустите демо-режим.", "warning")
            return False
        return True

    def run(self, fn: Callable, on_done: Callable[[Any], None] | None = None, title: str = "",
            on_error: Callable[[BaseException], None] | None = None, cancellable: bool = True):
        return self.win.run_task(fn, on_done, title=title, on_error=on_error, cancellable=cancellable)

    def export(self, tables, base_name: str, *, html: bool = False, kpis=None, title: str = "") -> None:
        tables = tables if isinstance(tables, list) else [tables]
        info = self.ctx.gateway.info if self.ctx else None
        for t in tables:
            report_meta(t, info)
        path = ask_export_path(self, base_name, html=html, last_dir=self.db.get_setting("last_export_dir", ""))
        if not path:
            return
        import os
        self.db.set_setting("last_export_dir", os.path.dirname(path))

        def job(cancel, progress):
            progress(None, "Экспорт…")
            return write_report(tables, path, title=title, kpis=kpis)
        self.run(job, lambda p: self.win.toast(f"Экспортировано: {p}", "success"), "Экспорт отчёта")

    # hooks -------------------------------------------------------------------------------------------------------
    def on_connected(self) -> None:
        self._loaded_once = False

    def on_disconnected(self) -> None:
        self._loaded_once = False

    def on_shown(self) -> None:
        if not self._loaded_once and (self.connected() or not self.needs_connection):
            self._loaded_once = True
            self.initial_load()

    def initial_load(self) -> None:
        """Lazy first load when the page is opened after connecting."""
