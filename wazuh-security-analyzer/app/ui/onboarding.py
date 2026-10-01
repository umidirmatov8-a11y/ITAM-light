"""First-run onboarding dialog (language + analysis mode)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app import __app_name__
from app.i18n import SUPPORTED, get_language, set_language, tr

_INTRO = ("Load Wazuh alerts (JSON, CSV, logs, ZIP) and get a prioritized, explained analysis with correlation, "
          "MITRE ATT&CK mapping, CVE and IOC context and concrete response recommendations.<br><br>"
          "<b>Choose analysis mode:</b><br>"
          "• <b>Offline</b> — everything stays on this computer (recommended for confidential logs).<br>"
          "• <b>Online</b> — adds NVD/CISA KEV CVE data and IOC reputation (only public indicators are sent).<br>"
          "• <b>Configure AI</b> — optional AI analyst (local Ollama or cloud providers).<br><br>"
          "You can change this at any time in Settings.")


class OnboardingDialog(QDialog):
    OFFLINE, ONLINE, CONFIGURE_AI = "offline", "online", "configure_ai"
    _BUTTONS = (("Offline", "offline", True), ("Online", "online", False), ("Configure AI", "configure_ai", False))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(640)
        self.choice = self.OFFLINE
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Language / Язык:"))
        self.language = QComboBox()
        for code, name in SUPPORTED.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(get_language())))
        self.language.currentIndexChanged.connect(self._language_changed)
        lang_row.addWidget(self.language)
        lang_row.addStretch(1)
        lay.addLayout(lang_row)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 18pt; font-weight: 800;")
        lay.addWidget(self.title)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.RichText)
        lay.addWidget(self.text)
        buttons = QHBoxLayout()
        self.buttons: list[tuple[QPushButton, str]] = []
        for label, choice, primary in self._BUTTONS:
            btn = QPushButton()
            btn.setMinimumHeight(44)
            if primary:
                btn.setObjectName("primary")
                btn.setDefault(True)
            btn.clicked.connect(lambda _c=False, ch=choice: self._choose(ch))
            buttons.addWidget(btn)
            self.buttons.append((btn, label))
        lay.addLayout(buttons)
        self._retranslate()

    def _retranslate(self) -> None:
        self.setWindowTitle(tr("Welcome to {app}", app=__app_name__))
        self.title.setText(tr("Welcome to {app}", app=__app_name__))
        self.text.setText(tr(_INTRO))
        for btn, label in self.buttons:
            btn.setText(tr(label))

    def _language_changed(self, _index: int) -> None:
        set_language(self.language.currentData())
        self._retranslate()

    def _choose(self, choice: str) -> None:
        self.choice = choice
        self.accept()
