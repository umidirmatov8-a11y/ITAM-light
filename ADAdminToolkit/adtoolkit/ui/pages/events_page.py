"""Windows Security events from domain controllers (wevtutil, current Windows credentials)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QSpinBox, QTabWidget, QVBoxLayout)

from ...services.events_service import (EVENT_GROUPS, REQUIREMENTS_TEXT, SEVERITY_LABEL, SEVERITY_ORDER, EventQuery, EventsService,
                                        availability, lockout_summary)
from ..widgets.common import banner, set_banner
from ..widgets.table import Column, DataTable
from .base import BasePage


class EventsPage(BasePage):
    title = "Журналы безопасности"
    subtitle = "события Windows Security на контроллерах домена"

    def __init__(self, win):
        super().__init__(win)
        ok, reason = availability()
        req = banner("Требования модуля (LDAP не предоставляет журнал безопасности):\n" + "\n".join(f"• {r}" for r in REQUIREMENTS_TEXT)
                     + ("" if ok else f"\n\nНЕДОСТУПНО В ТЕКУЩЕЙ СРЕДЕ: {reason}"), danger=not ok)
        req.setVisible(True)
        self.root.addWidget(req)
        top = QHBoxLayout()
        dc_box = QGroupBox("Контроллеры домена")
        dl = QVBoxLayout(dc_box)
        self.dcs = QListWidget()
        self.dcs.setMaximumHeight(120)
        dl.addWidget(self.dcs)
        add_row = QHBoxLayout()
        self.extra_dc = QLineEdit()
        self.extra_dc.setPlaceholderText("Добавить DC вручную (FQDN)")
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add_dc)
        add_row.addWidget(self.extra_dc)
        add_row.addWidget(add_btn)
        dl.addLayout(add_row)
        top.addWidget(dc_box, 1)
        ev_box = QGroupBox("События")
        el = QVBoxLayout(ev_box)
        self.groups = QListWidget()
        self.groups.setMaximumHeight(150)
        for name, ids in EVENT_GROUPS.items():
            item = QListWidgetItem(f"{name} ({', '.join(map(str, ids))})")
            item.setData(Qt.UserRole, ids)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name.startswith("Блокировки") else Qt.Unchecked)
            self.groups.addItem(item)
        el.addWidget(self.groups)
        self.custom_ids = QLineEdit()
        self.custom_ids.setPlaceholderText("Доп. коды через запятую, например 4740, 4625")
        el.addWidget(self.custom_ids)
        top.addWidget(ev_box, 2)
        par = QGroupBox("Фильтр")
        g = QGridLayout(par)
        self.hours = QSpinBox()
        self.hours.setRange(1, 24 * 90)
        self.hours.setValue(24)
        self.hours.setSuffix(" ч")
        self.user = QLineEdit()
        self.user.setPlaceholderText("Пользователь (TargetUserName)")
        self.min_sev = QComboBox()
        for key in ("info", "low", "medium", "high", "critical"):
            self.min_sev.addItem(f"от «{SEVERITY_LABEL[key]}»", key)
        self.max_events = QSpinBox()
        self.max_events.setRange(10, 20000)
        self.max_events.setValue(win.settings.events_max)
        g.addWidget(QLabel("Период:"), 0, 0)
        g.addWidget(self.hours, 0, 1)
        g.addWidget(QLabel("Пользователь:"), 1, 0)
        g.addWidget(self.user, 1, 1)
        g.addWidget(QLabel("Критичность:"), 2, 0)
        g.addWidget(self.min_sev, 2, 1)
        g.addWidget(QLabel("Макс. событий на DC:"), 3, 0)
        g.addWidget(self.max_events, 3, 1)
        self.query_btn = QPushButton("Получить события")
        self.query_btn.setProperty("primary", True)
        self.query_btn.clicked.connect(self._query)
        self.query_btn.setEnabled(ok)
        g.addWidget(self.query_btn, 4, 0, 1, 2)
        top.addWidget(par, 1)
        self.root.addLayout(top)
        self.errors = banner(danger=True)
        self.root.addWidget(self.errors)
        tabs = QTabWidget()
        self.table = DataTable([Column("time", "Время"), Column("dc", "DC"), Column("event_id", "Код", align_right=True),
                                Column("title", "Событие"), Column("severity", "Критичность", lambda e: SEVERITY_LABEL.get(e.severity),
                                       sort=lambda e: SEVERITY_ORDER.get(e.severity, 9)),
                                Column("target_user", "Учётная запись"), Column("subject_user", "Инициатор"),
                                Column("source", "Источник/компьютер"), Column("status", "Статус"), Column("message", "Подробности")],
                               "events", win.db, export_cb=self._export)
        self.table.set_state_fn(lambda e: {"critical": "danger", "high": "danger", "medium": "warning"}.get(e.severity))
        tabs.addTab(self.table, "События")
        self.lockouts = DataTable([Column("user", "Учётная запись"), Column("source", "Компьютер-источник"),
                                   Column("count", "Блокировок", align_right=True), Column("last", "Последняя")],
                                  "events_lockouts", win.db)
        tabs.addTab(self.lockouts, "Анализ блокировок (4740)")
        self.root.addWidget(tabs, 1)
        self.last = None

    def on_connected(self):
        super().on_connected()
        self.dcs.clear()
        for dc in self.ctx.gateway.info.domain_controllers or [self.ctx.gateway.info.dc_host]:
            self._add_dc_item(dc, True)

    def _add_dc_item(self, dc: str, checked: bool):
        item = QListWidgetItem(dc)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.dcs.addItem(item)

    def _add_dc(self):
        t = self.extra_dc.text().strip()
        if t:
            self._add_dc_item(t, True)
            self.extra_dc.clear()

    def _query(self):
        dcs = [self.dcs.item(i).text() for i in range(self.dcs.count()) if self.dcs.item(i).checkState() == Qt.Checked]
        ids: list[int] = []
        for i in range(self.groups.count()):
            if self.groups.item(i).checkState() == Qt.Checked:
                ids += self.groups.item(i).data(Qt.UserRole)
        for part in self.custom_ids.text().replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        if not dcs:
            self.win.toast("Укажите хотя бы один контроллер домена", "info")
            return
        if not ids:
            self.win.toast("Выберите типы событий", "info")
            return
        q = EventQuery(dcs=dcs, event_ids=sorted(set(ids)), hours=self.hours.value(), user=self.user.text(),
                       max_events=self.max_events.value(), min_severity=self.min_sev.currentData(),
                       timeout_s=self.win.settings.events_timeout_s)
        self.query_btn.setEnabled(False)

        def done(res):
            self.query_btn.setEnabled(True)
            self.last = (q, res)
            self.table.set_rows(res.events)
            self.lockouts.set_rows(lockout_summary(res.events))
            set_banner(self.errors, [f"{dc}: {err}" for dc, err in res.errors.items()])
            self.win.toast(f"Получено событий: {len(res.events)}" + (f"; ошибок DC: {len(res.errors)}" if res.errors else ""),
                           "warning" if res.errors else "success")

        def failed(exc):
            self.query_btn.setEnabled(True)
            from ..widgets.common import show_error
            show_error(self, exc)
        self.run(lambda c, p: EventsService().query(q, c, p), done, "Чтение журналов безопасности", on_error=failed)

    def _export(self):
        if not self.last:
            return
        q, res = self.last
        rep = self.table.to_report("События безопасности контроллеров домена",
                                   criteria={"DC": ", ".join(q.dcs), "Коды": ", ".join(map(str, q.event_ids)),
                                             "Период, ч": q.hours, "Пользователь": q.user},
                                   limitations=[f"Не получены данные: {dc} — {e}" for dc, e in res.errors.items()] +
                                   [f"Не более {q.max_events} последних событий с каждого DC."],
                                   info=self.ctx.gateway.info if self.ctx else None)
        self.export(rep, "security_events")

