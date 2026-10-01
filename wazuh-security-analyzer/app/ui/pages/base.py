"""Base class for pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.i18n import tr
from app.ui.context import AppContext
from app.ui.widgets.common import label


class BasePage(QWidget):
    title = "Page"
    subtitle = ""

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.ctx = ctx
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 16, 20, 16)
        self.root.setSpacing(12)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title_label = label(tr(self.title), "pageTitle")
        titles.addWidget(self.title_label)
        self.subtitle_label = label(tr(self.subtitle), "muted", wrap=True)
        if self.subtitle:
            titles.addWidget(self.subtitle_label)
        header.addLayout(titles, 1)
        self.header_actions = QHBoxLayout()
        header.addLayout(self.header_actions)
        self.root.addLayout(header)
        self.empty_label = QLabel(tr("Load Wazuh alerts on the Dashboard to see results here."))
        self.empty_label.setObjectName("muted")
        ctx.sessionChanged.connect(self.on_session)

    @property
    def session(self):
        return self.ctx.session

    def on_session(self, session) -> None:  # pragma: no cover - overridden
        pass

    def on_show(self, **kwargs) -> None:
        """Called when the page becomes visible (optionally with navigation arguments)."""
