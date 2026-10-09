"""Connection dialog: profiles, security mode, authentication, step-by-step test, connect, demo mode."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ...core.errors import ToolkitError
from ...models.connection import AuthMethod, ConnectionProfile, SecurityMode
from ...security import credentials
from ...services.ldap_service import ConnectionService
from ..widgets.common import PasswordField, banner, set_banner, show_error
from ..widgets.table import Column, DataTable


class ConnectionDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Подключение к Active Directory")
        self.resize(760, 760)
        self.result_ctx = None
        self.cred_store = credentials.CredentialStore()
        lay = QVBoxLayout(self)

        prow = QHBoxLayout()
        self.profiles = QComboBox()
        self.profiles.setMinimumWidth(260)
        prow.addWidget(QLabel("Профиль:"))
        prow.addWidget(self.profiles, 1)
        save = QPushButton("Сохранить профиль")
        save.clicked.connect(self._save_profile)
        delete = QPushButton("Удалить")
        delete.clicked.connect(self._delete_profile)
        prow.addWidget(save)
        prow.addWidget(delete)
        lay.addLayout(prow)

        box = QGroupBox("Сервер")
        form = QFormLayout(box)
        self.server = QLineEdit()
        self.server.setPlaceholderText("FQDN контроллера домена, например dc01.company.local")
        self.security = QComboBox()
        for m in SecurityMode:
            self.security.addItem(m.label, m)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(636)
        self.base_dn = QLineEdit()
        self.base_dn.setPlaceholderText("пусто — определить автоматически (defaultNamingContext)")
        self.ca_file = QLineEdit()
        self.ca_file.setPlaceholderText("пусто — доверенные корневые сертификаты Windows")
        ca_btn = QPushButton("…")
        ca_btn.setFixedWidth(34)
        ca_btn.setProperty("small", True)
        ca_btn.clicked.connect(self._pick_ca)
        ca_row = QHBoxLayout()
        ca_row.addWidget(self.ca_file, 1)
        ca_row.addWidget(ca_btn)
        ca_w = QWidget()
        ca_row.setContentsMargins(0, 0, 0, 0)
        ca_w.setLayout(ca_row)
        self.tls_name = QLineEdit()
        self.tls_name.setPlaceholderText("необязательно: имя в сертификате, если подключение по IP")
        form.addRow("LDAP-сервер / DC:", self.server)
        form.addRow("Режим безопасности:", self.security)
        form.addRow("Порт:", self.port)
        form.addRow("Base DN:", self.base_dn)
        form.addRow("Сертификат ЦС (PEM):", ca_w)
        form.addRow("Имя сертификата:", self.tls_name)
        lay.addWidget(box)

        abox = QGroupBox("Аутентификация")
        af = QFormLayout(abox)
        self.auth = QComboBox()
        for m in AuthMethod:
            self.auth.addItem(m.label, m)
        self.username = QLineEdit()
        self.username.setPlaceholderText("administrator@company.local или COMPANY\\administrator")
        self.password = PasswordField(self, "Пароль (не сохраняется в настройках)")
        self.save_cred = QCheckBox("Сохранить пароль в Диспетчере учётных данных Windows (с моего согласия)")
        ok, reason = credentials.available()
        if not ok:
            self.save_cred.setEnabled(False)
            self.save_cred.setToolTip(reason)
        self.allow_plain = QCheckBox("Разрешить Kerberos без TLS (данные каталога передаются открыто)")
        af.addRow("Способ:", self.auth)
        af.addRow("Пользователь:", self.username)
        af.addRow("Пароль:", self.password)
        af.addRow("", self.save_cred)
        af.addRow("", self.allow_plain)
        lay.addWidget(abox)

        obox = QGroupBox("Параметры")
        of = QFormLayout(obox)
        self.connect_timeout = QSpinBox()
        self.connect_timeout.setRange(1, 120)
        self.connect_timeout.setValue(10)
        self.op_timeout = QSpinBox()
        self.op_timeout.setRange(5, 900)
        self.op_timeout.setValue(60)
        self.page_size = QSpinBox()
        self.page_size.setRange(50, 1000)
        self.page_size.setValue(500)
        self.retries = QSpinBox()
        self.retries.setRange(0, 10)
        self.retries.setValue(3)
        self.read_only = QCheckBox("Режим «только чтение» (рекомендуется; изменения включаются отдельно)")
        self.read_only.setChecked(True)
        of.addRow("Тайм-аут подключения, с:", self.connect_timeout)
        of.addRow("Тайм-аут операций, с:", self.op_timeout)
        of.addRow("Размер страницы LDAP:", self.page_size)
        of.addRow("Попыток переподключения:", self.retries)
        of.addRow("", self.read_only)
        lay.addWidget(obox)

        self.warning = banner(danger=True)
        lay.addWidget(self.warning)
        self.steps = DataTable([Column("name", "Шаг"), Column("status", "Результат", lambda s: {True: "OK", False: "Ошибка", None: "Внимание"}[s.ok]),
                                Column("message", "Подробности")], show_toolbar=False)
        self.steps.set_state_fn(lambda s: {True: "ok", False: "danger", None: "warning"}[s.ok])
        self.steps.setMinimumHeight(150)
        lay.addWidget(self.steps, 1)

        bb = QDialogButtonBox()
        self.test_btn = bb.addButton("Проверить подключение", QDialogButtonBox.ActionRole)
        self.demo_btn = bb.addButton("Демо-режим (без DC)", QDialogButtonBox.ActionRole)
        self.connect_btn = bb.addButton("Подключиться", QDialogButtonBox.AcceptRole)
        self.connect_btn.setProperty("primary", True)
        bb.addButton("Отмена", QDialogButtonBox.RejectRole)
        self.test_btn.clicked.connect(self._test)
        self.demo_btn.clicked.connect(self._demo)
        bb.accepted.connect(self._connect)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.security.currentIndexChanged.connect(self._security_changed)
        self.auth.currentIndexChanged.connect(self._update_warning)
        self.allow_plain.toggled.connect(self._update_warning)
        self.profiles.currentIndexChanged.connect(self._load_selected)
        self._load_profiles()
        self._update_warning()

    # ---------------------------------------------------------------------------------------------------------
    def _load_profiles(self):
        self.profiles.blockSignals(True)
        self.profiles.clear()
        seen = set()
        for p in self.win.db.list_profiles() + self.win.settings_mgr.org_profiles():
            try:
                prof = ConnectionProfile.from_dict(p)
            except (ValueError, TypeError):
                continue
            if prof.name in seen:
                continue
            seen.add(prof.name)
            self.profiles.addItem(prof.name, prof)
        if self.profiles.count() == 0:
            self.profiles.addItem("Новое подключение", ConnectionProfile())
        self.profiles.blockSignals(False)
        self._load_selected()

    def _load_selected(self):
        p: ConnectionProfile = self.profiles.currentData()
        if p is None:
            return
        self.server.setText(p.server)
        self.security.setCurrentIndex(list(SecurityMode).index(p.security))
        self.port.setValue(p.port)
        self.base_dn.setText(p.base_dn)
        self.ca_file.setText(p.ca_file)
        self.tls_name.setText(p.tls_server_name)
        self.auth.setCurrentIndex(list(AuthMethod).index(p.auth))
        self.username.setText(p.username)
        self.connect_timeout.setValue(p.connect_timeout)
        self.op_timeout.setValue(p.operation_timeout)
        self.page_size.setValue(p.page_size)
        self.retries.setValue(p.reconnect_attempts)
        self.read_only.setChecked(p.read_only)
        self.allow_plain.setChecked(p.allow_unencrypted_kerberos)
        self.save_cred.setChecked(p.use_credential_manager and self.save_cred.isEnabled())
        self.password.clear()
        if p.use_credential_manager and p.server and p.username:
            stored = self.cred_store.load(p.credential_target())
            if stored:
                self.password.setText(stored)

    def profile(self) -> ConnectionProfile:
        cur: ConnectionProfile = self.profiles.currentData() or ConnectionProfile()
        return ConnectionProfile(
            name=cur.name if cur.name != "Новое подключение" else (self.server.text().strip() or cur.name),
            server=self.server.text().strip(), port=self.port.value(), security=SecurityMode(self.security.currentData()),
            auth=AuthMethod(self.auth.currentData()), base_dn=self.base_dn.text().strip(), username=self.username.text().strip(),
            ca_file=self.ca_file.text().strip(), tls_server_name=self.tls_name.text().strip(),
            connect_timeout=self.connect_timeout.value(), operation_timeout=self.op_timeout.value(),
            page_size=self.page_size.value(), reconnect_attempts=self.retries.value(),
            allow_unencrypted_kerberos=self.allow_plain.isChecked(), use_credential_manager=self.save_cred.isChecked(),
            read_only=self.read_only.isChecked())

    def _security_changed(self):
        mode = SecurityMode(self.security.currentData()) if self.security.currentData() else None
        if mode is not None:
            self.port.setValue(mode.default_port)
        self._update_warning()

    def _update_warning(self):
        mode = SecurityMode(self.security.currentData())
        auth = AuthMethod(self.auth.currentData())
        lines = []
        if mode is SecurityMode.PLAIN:
            if auth is not AuthMethod.KERBEROS:
                lines.append("LDAP без шифрования: пароль НЕ будет отправлен. Выберите LDAPS/StartTLS или Kerberos.")
            else:
                lines.append("Соединение не зашифровано: данные каталога передаются открыто, операции с паролями заблокированы. "
                             "ldap3 не поддерживает SASL-шифрование (sealing) — для защиты используйте LDAPS/StartTLS.")
        if auth is AuthMethod.KERBEROS:
            if sys.platform != "win32":
                lines.append("Kerberos с текущими учётными данными Windows доступен только при запуске на Windows (winkerberos).")
            self.username.setEnabled(False)
            self.password.setEnabled(False)
            self.save_cred.setEnabled(False)
        else:
            self.username.setEnabled(True)
            self.password.setEnabled(True)
            self.save_cred.setEnabled(credentials.available()[0])
        set_banner(self.warning, lines)
        self.allow_plain.setVisible(mode is SecurityMode.PLAIN)

    def _pick_ca(self):
        path, _ = QFileDialog.getOpenFileName(self, "Сертификат ЦС", "", "PEM (*.pem *.crt *.cer);;Все файлы (*)")
        if path:
            self.ca_file.setText(path)

    def _save_profile(self):
        p = self.profile()
        name, ok = QInputDialog.getText(self, "Профиль", "Имя профиля:", text=p.name)
        if not ok or not name.strip():
            return
        p.name = name.strip()
        self.win.db.save_profile(p.to_dict())
        self._store_credential(p)
        self._load_profiles()
        idx = self.profiles.findText(p.name)
        if idx >= 0:
            self.profiles.setCurrentIndex(idx)
        self.win.toast("Профиль сохранён (без пароля)", "success")

    def _delete_profile(self):
        p: ConnectionProfile = self.profiles.currentData()
        if p is None:
            return
        self.win.db.delete_profile(p.name)
        if p.server and p.username:
            self.cred_store.delete(p.credential_target())
        self._load_profiles()

    def _store_credential(self, p: ConnectionProfile):
        if not p.auth.needs_password or not p.server or not p.username:
            return
        if p.use_credential_manager and self.password.text():
            try:
                self.cred_store.save(p.credential_target(), p.username, self.password.text(), consent=True)
            except ToolkitError as exc:
                self.win.toast(exc.message, "warning")
        elif not p.use_credential_manager:
            self.cred_store.delete(p.credential_target())

    # ---------------------------------------------------------------------------------------------------------
    def _set_busy(self, busy: bool):
        for b in (self.test_btn, self.demo_btn, self.connect_btn):
            b.setEnabled(not busy)

    def _test(self):
        p = self.profile()
        pwd = self.password.text() if p.auth.needs_password else None
        svc = ConnectionService(self.win.journal, self.win.settings)
        self._set_busy(True)

        def done(report):
            self._set_busy(False)
            self.steps.set_rows(report.steps)
            self.win.toast("Проверка пройдена" if report.success else "Проверка выявила проблемы",
                           "success" if report.success else "warning")

        def failed(exc):
            self._set_busy(False)
            show_error(self, exc)
        self.win.run_task(lambda c, pr: svc.test(p, pwd, c, pr), done, title="Проверка подключения", on_error=failed)

    def _connect(self):
        p = self.profile()
        pwd = self.password.text() if p.auth.needs_password else None
        svc = ConnectionService(self.win.journal, self.win.settings)
        self._set_busy(True)

        def done(ctx):
            self._set_busy(False)
            self.win.db.save_profile(p.to_dict())
            self._store_credential(p)
            self.password.clear()
            self.result_ctx = ctx
            self.accept()

        def failed(exc):
            self._set_busy(False)
            show_error(self, exc, "Подключение не выполнено")
        self.win.run_task(lambda c, pr: svc.connect(p, pwd), done, title="Подключение к домену", on_error=failed,
                          cancellable=False)

    def _demo(self):
        svc = ConnectionService(self.win.journal, self.win.settings)
        self.result_ctx = svc.connect_demo(read_only=self.read_only.isChecked())
        self.password.clear()
        self.accept()

