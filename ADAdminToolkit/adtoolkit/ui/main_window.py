"""Main window: sidebar navigation, connection status bar, global search, read-only switch, task progress, toasts."""
from __future__ import annotations

import logging
from datetime import timezone

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QProgressBar,
                               QPushButton, QStackedWidget, QStatusBar, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..core.app_config import SettingsManager
from ..core.errors import OperationCancelledError
from ..ldap.adtypes import format_dt
from ..security.audit_log import OperationJournal
from ..services.bulk_service import BulkOperation
from ..storage.database import Database
from ..workers.tasks import TaskManager
from . import theme
from .actions import Actions
from .widgets.common import ToastHost, confirm, show_error

log = logging.getLogger(__name__)

PAGES = [
    ("dashboard", "🏠  Главная"),
    ("users", "👤  Пользователи"),
    ("computers", "🖥  Компьютеры"),
    ("groups", "👥  Группы"),
    ("ous", "🗂  Структура OU"),
    ("audit", "🛡  Аудит и диагностика"),
    ("events", "📜  Журналы безопасности"),
    ("bulk", "📦  Массовые операции"),
    ("explorer", "🔎  LDAP Explorer"),
    ("tools", "🧰  Инструменты"),
    ("reports", "📊  Отчёты"),
    ("oplog", "🕘  Журнал операций"),
    ("settings", "⚙  Настройки"),
]


class ConnectionBridge(QObject):
    """Thread-safe bridge from gateway listeners (worker threads) to the GUI."""
    state = Signal(str, str)


class MainWindow(QMainWindow, ToastHost):
    def __init__(self, db: Database | None = None, settings_mgr: SettingsManager | None = None):
        super().__init__()
        self._init_toasts()
        self.db = db or Database()
        self.settings_mgr = settings_mgr or SettingsManager(self.db)
        self.journal = OperationJournal(self.db)
        self.tasks = TaskManager(self)
        self.actions = Actions(self)
        self.ctx = None
        self.bridge = ConnectionBridge()
        self.bridge.state.connect(self._on_gateway_state)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1440, 900)
        self.setMinimumSize(1024, 640)
        self._build()
        self.health_timer = QTimer(self)
        self.health_timer.setInterval(60_000)
        self.health_timer.timeout.connect(self._health_check)
        self._health_running = False
        geom = self.db.get_setting("window_geometry")
        if geom:
            try:
                import base64
                self.restoreGeometry(base64.b64decode(geom))
            except Exception:  # noqa: BLE001
                pass

    @property
    def settings(self):
        return self.settings_mgr.settings

    # ---------------------------------------------------------------------------------------------------------
    def _build(self):
        from .pages import create_pages
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QWidget()
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        sub = QLabel(f"Active Directory · v{__version__}")
        sub.setObjectName("AppSubtitle")
        self.nav = QListWidget()
        self.nav.setObjectName("Sidebar")
        for key, text in PAGES:
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, key)
            self.nav.addItem(item)
        sl.addWidget(title)
        sl.addWidget(sub)
        sl.addWidget(self.nav, 1)
        h.addWidget(side)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        top = QWidget()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(12, 8, 12, 8)
        self.status_pill = QLabel("● Нет подключения")
        self.status_pill.setObjectName("Pill")
        self.domain_label = QLabel("")
        self.domain_label.setObjectName("Muted")
        self.security_label = QLabel("")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Глобальный поиск: пользователи, компьютеры, группы (Ctrl+F)…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(320)
        self.search.setMaximumWidth(520)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._global_search)
        self.search.textChanged.connect(self._search_changed)
        self.search.returnPressed.connect(self._global_search)
        self.ro_btn = QPushButton("🔒 Только чтение")
        self.ro_btn.setCheckable(True)
        self.ro_btn.setChecked(True)
        self.ro_btn.setToolTip("Режим только для чтения. Нажмите, чтобы разрешить изменения (требует подтверждения).")
        self.ro_btn.clicked.connect(self._toggle_read_only)
        self.connect_btn = QPushButton("Подключиться…")
        self.connect_btn.setProperty("primary", True)
        self.connect_btn.clicked.connect(self.show_connect_dialog)
        self.disconnect_btn = QPushButton("Отключиться")
        self.disconnect_btn.clicked.connect(self.disconnect)
        self.disconnect_btn.setVisible(False)
        tl.addWidget(self.status_pill)
        tl.addWidget(self.domain_label)
        tl.addWidget(self.security_label)
        tl.addStretch(1)
        tl.addWidget(self.search, 2)
        tl.addWidget(self.ro_btn)
        tl.addWidget(self.connect_btn)
        tl.addWidget(self.disconnect_btn)
        rl.addWidget(top)
        self.stack = QStackedWidget()
        rl.addWidget(self.stack, 1)
        h.addWidget(right, 1)
        self.setCentralWidget(central)

        self.pages = create_pages(self)
        for key, _ in PAGES + [("search", "")]:
            self.stack.addWidget(self.pages[key])
        self.nav.currentRowChanged.connect(self._nav_changed)

        sb = QStatusBar()
        self.task_label = QLabel("Готово")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setVisible(False)
        self.cancel_btn = QPushButton("Отменить")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_tasks)
        self.last_ok = QLabel("")
        self.last_ok.setObjectName("Muted")
        sb.addWidget(self.task_label, 1)
        sb.addPermanentWidget(self.last_ok)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.cancel_btn)
        self.setStatusBar(sb)
        self.tasks.changed.connect(self._tasks_changed)
        self.tasks.progress.connect(self._task_progress)

        find = QAction(self)
        find.setShortcut(QKeySequence.Find)
        find.triggered.connect(lambda: (self.search.setFocus(), self.search.selectAll()))
        self.addAction(find)
        self.nav.setCurrentRow(0)
        self._update_status()

    # ---------------------------------------------------------------------------------------------------------
    def navigate(self, key: str):
        keys = [k for k, _ in PAGES]
        if key in keys:
            self.nav.setCurrentRow(keys.index(key))
        else:
            self.stack.setCurrentWidget(self.pages[key])
            self.pages[key].on_shown()

    def _nav_changed(self, row: int):
        if row < 0:
            return
        key = PAGES[row][0]
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        page.on_shown()

    # ---------------------------------------------------------------------------------------------------------
    def run_task(self, fn, on_done=None, *, title: str = "", on_error=None, cancellable: bool = True, silent: bool = False):
        def default_error(exc):
            if isinstance(exc, OperationCancelledError):
                self.toast("Операция отменена", "info")
                return
            show_error(self, exc)
        return self.tasks.run(fn, on_done, on_error or default_error, title=title, cancellable=cancellable, silent=silent)

    def _tasks_changed(self):
        visible = self.tasks.visible_tasks()
        busy = bool(visible)
        self.progress.setVisible(busy)
        self.cancel_btn.setVisible(busy and any(t.cancellable for t in visible))
        if not busy:
            self.task_label.setText("Готово")
            self.progress.setRange(0, 100)
        else:
            self.task_label.setText(visible[-1].title + (f" (+{len(visible) - 1})" if len(visible) > 1 else ""))
        self._update_last_ok()

    def _task_progress(self, percent, message):
        if percent is None:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(percent))
        if message:
            self.task_label.setText(message)

    def _cancel_tasks(self):
        self.tasks.cancel_all()
        self.task_label.setText("Отмена… (текущий LDAP-запрос завершится по тайм-ауту)")

    # ---------------------------------------------------------------------------------------------------------
    def show_connect_dialog(self):
        from .dialogs.connection_dialog import ConnectionDialog
        dlg = ConnectionDialog(self)
        if dlg.exec() and dlg.result_ctx is not None:
            self.set_context(dlg.result_ctx)

    def set_context(self, ctx):
        if self.ctx is not None:
            self.disconnect(silent=True)
        self.ctx = ctx
        ctx.gateway.add_listener(lambda state, msg: self.bridge.state.emit(state, msg))
        self.ro_btn.setChecked(ctx.gateway.read_only)
        self._update_status()
        for p in self.pages.values():
            p.on_connected()
        self.health_timer.start()
        info = ctx.gateway.info
        self.toast(f"Подключено: {info.domain_dns} ({info.dc_host})" + (" — ДЕМО-РЕЖИМ" if info.is_demo else ""), "success")
        for w in info.warnings:
            self.toast(w, "warning", 8000)
        current = self.stack.currentWidget()
        if hasattr(current, "on_shown"):
            current.on_shown()

    def disconnect(self, silent: bool = False):
        if self.ctx is None:
            return
        self.tasks.cancel_all()
        try:
            self.ctx.gateway._listeners.clear()
            self.ctx.gateway.close()
        except Exception:  # noqa: BLE001
            pass
        self.journal.record("disconnect", self.ctx.gateway.info.dc_host, "success")
        self.ctx = None
        self.health_timer.stop()
        for p in self.pages.values():
            p.on_disconnected()
        self._update_status()
        if not silent:
            self.toast("Отключено от домена", "info")

    def _on_gateway_state(self, state: str, message: str):
        if state == "reconnecting":
            self._set_pill("● Переподключение…", "warning")
            self.task_label.setText(message)
        elif state == "disconnected":
            self._set_pill("● Нет связи", "danger")
            if message:
                self.toast(message, "error", 6000)
        elif state == "connected":
            self._update_status()

    def _health_check(self):
        if self.ctx is None or self._health_running:
            return
        self._health_running = True
        gw = self.ctx.gateway

        def job(cancel, progress):
            if gw.ping():
                return True
            gw.reconnect()
            return gw.ping()

        def done(ok):
            self._health_running = False
            if ok:
                self._update_status()
            else:
                self._set_pill("● Нет связи", "danger")

        def failed(exc):
            self._health_running = False
            self._set_pill("● Нет связи", "danger")
            self.task_label.setText(f"Связь с контроллером потеряна: {getattr(exc, 'message', exc)}")
        self.run_task(job, done, title="Проверка связи", on_error=failed, silent=True, cancellable=False)

    def _set_pill(self, text: str, kind: str):
        c = theme.colors()
        color = {"ok": c["ok"], "warning": c["warning"], "danger": c["danger"], "muted": c["muted"]}[kind]
        self.status_pill.setText(text)
        self.status_pill.setStyleSheet(f"color: {color}; border: 1px solid {color};")

    def _update_status(self):
        if self.ctx is None:
            self._set_pill("● Нет подключения", "muted")
            self.domain_label.setText("")
            self.security_label.setText("")
            self.connect_btn.setVisible(True)
            self.disconnect_btn.setVisible(False)
            self.ro_btn.setEnabled(False)
            self.last_ok.setText("")
            return
        info = self.ctx.gateway.info
        demo = " · ДЕМО" if info.is_demo else ""
        self._set_pill("● Подключено" + demo, "ok")
        self.domain_label.setText(f"{info.domain_dns} ({info.netbios_name}) · DC: {info.dc_host} · {info.bound_identity}")
        c = theme.colors()
        if info.encrypted:
            self.security_label.setText("🔐 " + ("TLS" if not info.is_demo else "демо"))
            self.security_label.setStyleSheet(f"color: {c['ok']};")
            self.security_label.setToolTip(info.security_label + (f"\nСертификат: {info.certificate_subject}\n"
                                                                   f"Издатель: {info.certificate_issuer}\n"
                                                                   f"Действителен до: {info.certificate_not_after}"
                                                                   if info.certificate_subject else ""))
        else:
            self.security_label.setText("⚠ Не зашифровано")
            self.security_label.setStyleSheet(f"color: {c['danger']}; font-weight: 600;")
            self.security_label.setToolTip("Данные каталога передаются открыто. Операции с паролями заблокированы.")
        self.connect_btn.setVisible(False)
        self.disconnect_btn.setVisible(True)
        self.ro_btn.setEnabled(True)
        self._sync_ro_button()
        self._update_last_ok()

    def _update_last_ok(self):
        if self.ctx is None:
            return
        info = self.ctx.gateway.info
        ts = info.last_success_at
        self.last_ok.setText(f"Последний успешный обмен: {format_dt(ts.astimezone(timezone.utc)) if ts else '—'}")

    def _sync_ro_button(self):
        ro = self.ctx.gateway.read_only if self.ctx else True
        self.ro_btn.setChecked(ro)
        self.ro_btn.setText("🔒 Только чтение" if ro else "✏ Изменения разрешены")
        c = theme.colors()
        self.ro_btn.setStyleSheet("" if ro else f"color: {c['warning']}; border-color: {c['warning']}; font-weight: 600;")

    def _toggle_read_only(self):
        if self.ctx is None:
            self._sync_ro_button()
            return
        gw = self.ctx.gateway
        if gw.read_only:
            ok = confirm(self, "Разрешить изменения",
                         "Включить режим изменений Active Directory?",
                         details="Станут доступны операции изменения объектов. Каждое изменение требует подтверждения "
                                 "и записывается в журнал приложения. Права проверяются перед каждой операцией.",
                         danger=True, ok_text="Разрешить изменения")
            if ok:
                gw.read_only = False
                self.journal.record("mode.write_enabled", gw.info.dc_host, "success")
                self.toast("Режим изменений включён", "warning")
        else:
            gw.read_only = True
            self.journal.record("mode.read_only", gw.info.dc_host, "success")
            self.toast("Режим «только чтение» включён", "info")
        self._sync_ro_button()

    # ---------------------------------------------------------------------------------------------------------
    def _search_changed(self, text: str):
        self.search_timer.setInterval(self.settings.search_debounce_ms)
        if len(text.strip()) >= 2:
            self.search_timer.start()
        else:
            self.search_timer.stop()

    def _global_search(self):
        text = self.search.text().strip()
        if len(text) < 2:
            return
        if self.ctx is None:
            self.toast("Нет подключения к домену", "warning")
            return
        self.navigate("search")
        self.pages["search"].search(text)

    # ---------------------------------------------------------------------------------------------------------
    def open_user(self, dn: str):
        from .dialogs.user_dialogs import UserDetailsDialog
        if self.ctx:
            UserDetailsDialog(self, dn).show()

    def open_group(self, dn: str):
        from .dialogs.group_dialogs import GroupDetailsDialog
        if self.ctx:
            GroupDetailsDialog(self, dn).show()

    def open_computer(self, dn: str):
        from .dialogs.computer_dialog import ComputerDetailsDialog
        if self.ctx:
            ComputerDetailsDialog(self, dn).show()

    def start_bulk(self, operation: BulkOperation, dns: list[str], kind: str = "user", params: dict | None = None):
        self.navigate("bulk")
        self.pages["bulk"].prefill(operation, dns, kind, params or {})
        self.toast(f"Выбрано объектов: {len(dns)} — проверьте план в мастере массовых операций", "info", 6000)

    def apply_theme(self, name: str):
        from PySide6.QtWidgets import QApplication
        theme.apply_theme(QApplication.instance(), name)
        self._update_status()

    def resizeEvent(self, event):  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._relayout_toasts()

    def closeEvent(self, event):  # noqa: N802 - Qt API
        import base64
        try:
            self.db.set_setting("window_geometry", base64.b64encode(bytes(self.saveGeometry())).decode("ascii"))
            for p in self.pages.values():
                for child in p.findChildren(QWidget):
                    if hasattr(child, "save_state") and hasattr(child, "view_id"):
                        child.save_state()
        except Exception:  # noqa: BLE001
            log.exception("Не удалось сохранить состояние окна")
        self.tasks.cancel_all()
        if self.ctx is not None:
            try:
                self.ctx.gateway._listeners.clear()
                self.ctx.gateway.close()
            except Exception:  # noqa: BLE001
                pass
        self.tasks.wait_all(3000)
        super().closeEvent(event)
