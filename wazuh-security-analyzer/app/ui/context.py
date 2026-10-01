"""Shared application state for all pages."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from app.analyzers.rule_knowledge import default_rule_kb
from app.core.config import AppConfig, ConfigManager
from app.core.secrets import SecretStore
from app.database.state import StateStore
from app.intelligence.mitre import default_catalog
from app.services.session import AnalysisSession

log = logging.getLogger(__name__)


class AppContext(QObject):
    sessionChanged = Signal(object)
    configChanged = Signal()
    navigateRequested = Signal(str, dict)
    statusMessage = Signal(str)

    def __init__(self, config_manager: ConfigManager, secrets: SecretStore, state: StateStore):
        super().__init__()
        self.config_manager = config_manager
        self.secrets = secrets
        self.state = state
        self.session: AnalysisSession | None = None
        self.rule_kb = default_rule_kb()
        self.catalog = default_catalog()

    @property
    def config(self) -> AppConfig:
        return self.config_manager.config

    def set_session(self, session: AnalysisSession | None) -> None:
        old = self.session
        self.session = session
        self.sessionChanged.emit(session)
        if old is not None and old is not session:
            try:
                old.close()
            except Exception:
                log.debug("closing previous session failed", exc_info=True)

    def update_config(self, config: AppConfig) -> None:
        self.config_manager.update(config)
        self.configChanged.emit()

    def navigate(self, page: str, **kwargs) -> None:
        self.navigateRequested.emit(page, kwargs)
