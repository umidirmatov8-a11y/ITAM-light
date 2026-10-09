"""Computer details: directory data (with precision notes) and separate real network reachability checks."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from ...ldap.adtypes import display_value, format_dt
from ...services import network_service as N
from ...services.computer_service import ACTIVITY_NOTE, ComputerService
from ...services.explorer_service import ExplorerService
from ..widgets.table import Column, DataTable


def _ro(text):
    lbl = QLabel(text or "—")
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lbl.setWordWrap(True)
    return lbl


class ComputerDetailsDialog(QDialog):
    def __init__(self, win, dn: str):
        super().__init__(win)
        self.win = win
        self.dn = dn
        self.record = None
        self.setWindowTitle("Компьютер")
        self.resize(860, 600)
        lay = QVBoxLayout(self)
        self.header = QLabel("Загрузка…")
        self.header.setObjectName("PageTitle")
        lay.addWidget(self.header)
        note = QLabel(ACTIVITY_NOTE)
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)
        gw = QWidget()
        self.form = QFormLayout(gw)
        tabs.addTab(gw, "Сведения из каталога")
        nw = QWidget()
        nl = QVBoxLayout(nw)
        self.net_btn = QPushButton("Проверить доступность по сети (DNS, ping, TCP 135/445/3389/5985/5986)")
        self.net_btn.clicked.connect(self._check)
        nl.addWidget(self.net_btn, 0, Qt.AlignLeft)
        self.net = DataTable([Column("check", "Проверка"), Column("status_text", "Результат"), Column("message", "Подробности"),
                              Column("duration_ms", "мс", align_right=True)], show_toolbar=False)
        self.net.set_state_fn(lambda r: {True: "ok", False: "danger"}.get(r.ok))
        nl.addWidget(self.net, 1)
        tabs.addTab(nw, "Сетевая доступность")
        self.attrs = DataTable([Column("name", "Атрибут"), Column("value", "Значение")], "computer_attrs", win.db)
        tabs.addTab(self.attrs, "Все атрибуты")
        btns = QHBoxLayout()
        self.b_enable = QPushButton("Включить")
        self.b_disable = QPushButton("Отключить")
        b_move = QPushButton("Переместить…")
        b_copy = QPushButton("Копировать имя")
        b_dn = QPushButton("Копировать DN")
        b_ref = QPushButton("Обновить")
        a = win.actions
        rows = lambda: [self.record] if self.record else []  # noqa: E731
        self.b_enable.clicked.connect(lambda: a.set_computer_enabled(rows(), True, self.reload))
        self.b_disable.clicked.connect(lambda: a.set_computer_enabled(rows(), False, self.reload))
        b_move.clicked.connect(lambda: a.move(rows(), "computer", self.accept))
        b_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.record.name if self.record else ""))
        b_dn.clicked.connect(lambda: QApplication.clipboard().setText(self.dn))
        b_ref.clicked.connect(self.reload)
        for b in (self.b_enable, self.b_disable, b_move, b_copy, b_dn, b_ref):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)
        self.reload()

    def reload(self):
        ctx = self.win.ctx

        def job(cancel, progress):
            return ComputerService(ctx).get(self.dn), ExplorerService(ctx).object_attributes(self.dn)
        self.win.run_task(job, self._fill, title="Загрузка компьютера")

    def _fill(self, data):
        c, entry = data
        self.record = c
        self.setWindowTitle(f"Компьютер — {c.name}")
        self.header.setText(c.name + ("  (контроллер домена)" if c.is_dc else ""))
        while self.form.rowCount():
            self.form.removeRow(0)
        for label, value in [("DNS-имя", c.dns_host_name), ("ОС", c.os), ("Версия ОС", c.os_version),
                             ("Поддержка ОС", {"supported": "поддерживается", "outdated": "устарела", "unknown": "неизвестно"}[c.os_support.value] + (f" — {c.os_note}" if c.os_note else "")),
                             ("Включён", "Да" if c.enabled else "Нет"),
                             ("Последняя активность (lastLogonTimestamp)", format_dt(c.last_logon_timestamp) or "нет данных"),
                             ("Пароль компьютера сменён", format_dt(c.pwd_last_set)), ("Создан", format_dt(c.when_created)),
                             ("Изменён", format_dt(c.when_changed)), ("Описание", c.description), ("Размещение", c.location),
                             ("Ответственный", c.managed_by), ("OU", c.ou), ("DN", c.dn)]:
            self.form.addRow(label + ":", _ro(value))
        self.attrs.set_rows(sorted(({"name": k, "value": "; ".join(display_value(k, v) for v in vals)}
                                    for k, vals in entry.attributes.items()), key=lambda r: r["name"].lower()))
        self.b_enable.setEnabled(not c.enabled and not c.is_dc)
        self.b_disable.setEnabled(c.enabled and not c.is_dc)

    def _check(self):
        if self.record is None:
            return
        host = self.record.dns_host_name or self.record.name
        if self.win.ctx and self.win.ctx.gateway.is_demo:
            self.win.toast("Демо-режим: проверка выполняется по-настоящему, но имена demo.local, скорее всего, не разрешатся", "info", 6000)
        timeout = float(self.win.settings.network_timeout_s)
        self.win.run_task(lambda cancel, progress: N.computer_reachability(host, timeout, cancel, progress),
                          self.net.set_rows, title=f"Проверка доступности {host}")
