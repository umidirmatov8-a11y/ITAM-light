"""First-run onboarding dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app import __app_name__


class OnboardingDialog(QDialog):
    OFFLINE, ONLINE, CONFIGURE_AI = "offline", "online", "configure_ai"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Welcome to {__app_name__}")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.choice = self.OFFLINE
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        title = QLabel(f"Welcome to {__app_name__}")
        title.setStyleSheet("font-size: 18pt; font-weight: 800;")
        lay.addWidget(title)
        text = QLabel(
            "Load Wazuh alerts (JSON, CSV, logs, ZIP) and get a prioritized, explained analysis with correlation, "
            "MITRE ATT&CK mapping, CVE and IOC context and concrete response recommendations.<br><br>"
            "<b>Choose analysis mode:</b><br>"
            "• <b>Offline</b> — everything stays on this computer (recommended for confidential logs).<br>"
            "• <b>Online</b> — adds NVD/CISA KEV CVE data and IOC reputation (only public indicators are sent).<br>"
            "• <b>Configure AI</b> — optional AI analyst (local Ollama or cloud providers).<br><br>"
            "You can change this at any time in Settings.")
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        lay.addWidget(text)
        buttons = QHBoxLayout()
        for label, choice, primary in (("Offline", self.OFFLINE, True), ("Online", self.ONLINE, False),
                                       ("Configure AI", self.CONFIGURE_AI, False)):
            btn = QPushButton(label)
            btn.setMinimumHeight(44)
            if primary:
                btn.setObjectName("primary")
                btn.setDefault(True)
            btn.clicked.connect(lambda _c=False, ch=choice: self._choose(ch))
            buttons.addWidget(btn)
        lay.addLayout(buttons)

    def _choose(self, choice: str) -> None:
        self.choice = choice
        self.accept()
