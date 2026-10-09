"""Reports, operation journal, settings and global search pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea,
                               QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ...core.app_config import AppSettings
from ...ldap.dn import rdn_value
from ...ldap.filters import And, Or, Substring
from ...reports.exporters import ReportTable
from ...security.audit_log import JOURNAL_DISCLAIMER, RESULT_LABELS
from ...services import ad_queries as Q
from ...services.report_service import ReportService
from ...storage.database import default_data_dir
from ..widgets.common import banner, report_meta
from ..widgets.table import Column, DataTable
from .base import BasePage


class ReportsPage(BasePage):
    title = "Отчёты"
    subtitle = "готовые отчёты с датой, доменом, DC, критериями и ограничениями данных"

    def __init__(self, win):
        super().__init__(win)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        ll.addWidget(self.list, 1)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.desc.setObjectName("Muted")
        ll.addWidget(self.desc)
        form = QFormLayout()
        self.days = QSpinBox()
        self.days.setRange(1, 3650)
        self.days.setValue(win.settings.stale_user_days)
        self.days.setSuffix(" дн.")
        form.addRow("Период неактивности:", self.days)
        ll.addLayout(form)
        self.build_btn = QPushButton("Сформировать")
        self.build_btn.setProperty("primary", True)
        self.build_btn.clicked.connect(self.build)
        ll.addWidget(self.build_btn)
        mgmt = QPushButton("Отчёт для руководителя ИТ/ИБ (HTML)…")
        mgmt.clicked.connect(self._management)
        ll.addWidget(mgmt)
        bulk_note = QLabel("Отчёт «Результаты массовых операций» выгружается в мастере массовых операций после выполнения.")
        bulk_note.setWordWrap(True)
        bulk_note.setObjectName("Muted")
        ll.addWidget(bulk_note)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        self.meta = QLabel("")
        self.meta.setWordWrap(True)
        head.addWidget(self.meta, 1)
        exp = QPushButton("Экспорт (XLSX/CSV/HTML)…")
        exp.clicked.connect(self._export)
        head.addWidget(exp)
        rl.addLayout(head)
        self.lim = banner()
        rl.addWidget(self.lim)
        self.tabs = QTabWidget()
        rl.addWidget(self.tabs, 1)
        split.addWidget(right)
        split.setSizes([340, 900])
        self.root.addWidget(split, 1)
        self.tables: list[ReportTable] = []
        self.list.currentRowChanged.connect(self._sel)

    def on_connected(self):
        super().on_connected()
        self.list.clear()
        for d in ReportService(self.ctx).reports:
            item = QListWidgetItem(d.title)
            item.setData(Qt.UserRole, d.report_id)
            item.setToolTip(d.description)
            self.list.addItem(item)
        self.list.setCurrentRow(0)

    def on_disconnected(self):
        super().on_disconnected()
        self.list.clear()

    def _sel(self, row):
        if row < 0 or self.ctx is None:
            return
        d = ReportService(self.ctx).reports[row]
        self.desc.setText(d.description)
        self.days.setEnabled("days" in d.params)
        if d.report_id == "stale_computers":
            self.days.setValue(self.win.settings.stale_computer_days)
        elif d.report_id == "stale_users":
            self.days.setValue(self.win.settings.stale_user_days)

    def build(self):
        if not self.need_ctx():
            return
        item = self.list.currentItem()
        if item is None:
            return
        rid = item.data(Qt.UserRole)
        ctx, params = self.ctx, {"days": self.days.value()}
        self.build_btn.setEnabled(False)

        def done(tables):
            self.build_btn.setEnabled(True)
            self.show_tables(tables)

        def failed(exc):
            self.build_btn.setEnabled(True)
            from ..widgets.common import show_error
            show_error(self, exc)
        self.run(lambda c, p: ReportService(ctx).build(rid, params, c, p), done, f"Отчёт: {item.text()}", on_error=failed)

    def show_tables(self, tables: list[ReportTable]):
        self.tables = tables
        self.tabs.clear()
        for t in tables:
            dt = DataTable([Column(k, h) for k, h in t.columns], "", None)
            dt.set_rows(t.rows)
            if any(k == "severity" for k, _ in t.columns):
                dt.set_state_fn(lambda r: {"critical": "danger", "high": "danger", "medium": "warning"}.get(r.get("severity_key")))
            self.tabs.addTab(dt, f"{t.sheet_name or t.title} ({len(t.rows)})")
        if tables:
            t0 = tables[0]
            gen = t0.generated_at.astimezone().strftime("%Y-%m-%d %H:%M") if t0.generated_at else ""
            self.meta.setText(f"<b>{t0.title}</b><br>Сформирован: {gen} · домен {t0.domain} · DC {t0.dc} · "
                              f"сформировал {t0.generated_by}<br>Критерии: " +
                              "; ".join(f"{k}: {v}" for k, v in t0.criteria.items() if v not in (None, "", [])))
            lims = sorted({lim for t in tables for lim in t.limitations})
            from ..widgets.common import set_banner
            set_banner(self.lim, lims)

    def _export(self):
        if not self.tables:
            self.win.toast("Сначала сформируйте отчёт", "info")
            return
        self.export(self.tables, self.tables[0].title, html=True, title=self.tables[0].title)

    def _management(self):
        if not self.need_ctx():
            return
        ctx = self.ctx

        def done(tables):
            self.show_tables(tables)
            stats = next((t for t in tables if t.title == "Статистика домена"), None)
            kpis = [(r["metric"], str(r["value"])) for r in (stats.rows if stats else [])][:12]
            self.export(tables, "management_report", html=True, kpis=kpis,
                        title=f"Состояние Active Directory: {ctx.gateway.info.domain_dns}")
        self.run(lambda c, p: ReportService(ctx).build("domain_health", {}, c, p), done, "Отчёт для руководителя")


class OperationLogPage(BasePage):
    title = "Журнал операций"
    subtitle = "операции, выполненные через это приложение"
    needs_connection = False

    def __init__(self, win):
        super().__init__(win)
        disc = banner(JOURNAL_DISCLAIMER)
        disc.setVisible(True)
        self.root.addWidget(disc)
        row = QHBoxLayout()
        self.text = QLineEdit()
        self.text.setPlaceholderText("Поиск по операции, объекту или ошибке")
        self.text.returnPressed.connect(self.refresh)
        self.result = QComboBox()
        self.result.addItem("Любой результат", "")
        for k, v in RESULT_LABELS.items():
            self.result.addItem(v, k)
        self.limit = QSpinBox()
        self.limit.setRange(10, 100000)
        self.limit.setValue(1000)
        b = QPushButton("Обновить")
        b.clicked.connect(self.refresh)
        for w in (self.text, self.result, QLabel("Записей:"), self.limit, b):
            row.addWidget(w, 1 if w is self.text else 0)
        self.root.addLayout(row)
        self.table = DataTable([Column("ts", "Время (UTC)"), Column("windows_user", "Пользователь Windows"),
                                Column("ldap_identity", "Учётная запись LDAP"), Column("operation", "Операция"),
                                Column("target", "Объект"), Column("result", "Результат", lambda r: RESULT_LABELS.get(r["result"], r["result"])),
                                Column("error", "Ошибка"), Column("details", "Параметры"), Column("batch_id", "Пакет"),
                                Column("domain", "Домен", visible=False), Column("dc", "DC", visible=False)],
                               "oplog", win.db, export_cb=self._export)
        self.table.set_state_fn(lambda r: {"failed": "danger", "dry-run": "info", "skipped": "muted"}.get(r["result"]))
        self.root.addWidget(self.table, 1)
        win.journal.listeners.append(self._journal_changed)
        self._dirty = True

    def _journal_changed(self):
        self._dirty = True
        if self.isVisible():
            self.refresh()

    def on_shown(self):
        if self._dirty:
            self.refresh()

    def refresh(self):
        self._dirty = False
        self.table.set_rows(self.db.operations(self.limit.value(), self.text.text().strip(), self.result.currentData()))

    def _export(self):
        rep = report_meta(self.table.to_report("Журнал операций приложения", limitations=[JOURNAL_DISCLAIMER]),
                          self.ctx.gateway.info if self.ctx else None)
        self.export(rep, "operations_journal")


class SettingsPage(BasePage):
    title = "Настройки"
    subtitle = "параметры приложения (секреты не сохраняются)"
    needs_connection = False

    def __init__(self, win):
        super().__init__(win)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        lay = QVBoxLayout(body)
        s = win.settings
        ui = QGroupBox("Интерфейс")
        f = QFormLayout(ui)
        self.theme = QComboBox()
        self.theme.addItem("Тёмная", "dark")
        self.theme.addItem("Светлая", "light")
        self.theme.setCurrentIndex(0 if s.theme == "dark" else 1)
        self.debounce = QSpinBox()
        self.debounce.setRange(100, 3000)
        self.debounce.setSuffix(" мс")
        self.limit = QSpinBox()
        self.limit.setRange(100, 1_000_000)
        self.clip = QSpinBox()
        self.clip.setRange(0, 600)
        self.clip.setSuffix(" с")
        f.addRow("Тема:", self.theme)
        f.addRow("Задержка поиска:", self.debounce)
        f.addRow("Лимит строк в таблицах:", self.limit)
        f.addRow("Очистка буфера после копирования пароля:", self.clip)
        lay.addWidget(ui)
        pol = QGroupBox("Политика проверок")
        pf = QFormLayout(pol)
        self.stale_u = QSpinBox()
        self.stale_u.setRange(1, 3650)
        self.stale_c = QSpinBox()
        self.stale_c.setRange(1, 3650)
        self.pwd_exp = QSpinBox()
        self.pwd_exp.setRange(1, 365)
        self.recent = QSpinBox()
        self.recent.setRange(1, 365)
        self.required = QLineEdit()
        self.std_groups = QLineEdit()
        self.std_groups.setPlaceholderText("sAMAccountName групп через запятую, например GG-VPN-Users")
        self.extra_priv = QLineEdit()
        self.expiry_ous = QPlainTextEdit()
        self.expiry_ous.setMaximumHeight(60)
        self.expiry_ous.setPlaceholderText("DN OU (по одному в строке), где у включённых УЗ обязателен срок действия")
        self.os_rules = QPlainTextEdit()
        self.os_rules.setMaximumHeight(120)
        self.os_rules.setToolTip("Формат: подстрока ОС | примечание")
        pf.addRow("Неактивные пользователи, дней:", self.stale_u)
        pf.addRow("Неактивные компьютеры, дней:", self.stale_c)
        pf.addRow("«Пароль скоро истечёт», дней:", self.pwd_exp)
        pf.addRow("«Недавно созданные», дней:", self.recent)
        pf.addRow("Обязательные атрибуты пользователей:", self.required)
        pf.addRow("Стандартные группы организации:", self.std_groups)
        pf.addRow("Доп. привилегированные группы:", self.extra_priv)
        pf.addRow("OU с обязательным сроком УЗ:", self.expiry_ous)
        pf.addRow("Устаревшие ОС (подстрока | примечание):", self.os_rules)
        lay.addWidget(pol)
        bulk = QGroupBox("Массовые операции и сеть")
        bf = QFormLayout(bulk)
        self.bulk_max = QSpinBox()
        self.bulk_max.setRange(1, 10000)
        self.bulk_rate = QDoubleSpinBox()
        self.bulk_rate.setRange(0.2, 50)
        self.bulk_priv = QCheckBox("Разрешить массовые изменения привилегированных УЗ (с отдельным подтверждением)")
        self.net_timeout = QDoubleSpinBox()
        self.net_timeout.setRange(0.5, 60)
        self.net_timeout.setSuffix(" с")
        self.ev_max = QSpinBox()
        self.ev_max.setRange(10, 50000)
        self.ev_timeout = QSpinBox()
        self.ev_timeout.setRange(5, 600)
        self.upn = QLineEdit()
        self.upn.setPlaceholderText("суффикс UPN по умолчанию (пусто — DNS-имя домена)")
        bf.addRow("Максимум объектов в операции:", self.bulk_max)
        bf.addRow("Скорость, операций/с:", self.bulk_rate)
        bf.addRow("", self.bulk_priv)
        bf.addRow("Тайм-аут сетевых проверок:", self.net_timeout)
        bf.addRow("Событий с DC (по умолчанию):", self.ev_max)
        bf.addRow("Тайм-аут чтения журналов, с:", self.ev_timeout)
        bf.addRow("UPN-суффикс:", self.upn)
        lay.addWidget(bulk)
        info = QLabel(f"Данные приложения: {default_data_dir()}\nПароли не сохраняются ни в настройках, ни в журнале; "
                      "по желанию — только в Диспетчере учётных данных Windows.")
        info.setObjectName("Muted")
        info.setWordWrap(True)
        lay.addWidget(info)
        row = QHBoxLayout()
        save = QPushButton("Сохранить")
        save.setProperty("primary", True)
        save.clicked.connect(self.save)
        reset = QPushButton("Сбросить к умолчаниям")
        reset.clicked.connect(lambda: self._load(AppSettings()))
        row.addWidget(save)
        row.addWidget(reset)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        scroll.setWidget(body)
        self.root.addWidget(scroll, 1)
        self._load(s)

    def _load(self, s: AppSettings):
        self.theme.setCurrentIndex(0 if s.theme == "dark" else 1)
        self.debounce.setValue(s.search_debounce_ms)
        self.limit.setValue(s.search_result_limit)
        self.clip.setValue(s.clipboard_clear_s)
        self.stale_u.setValue(s.stale_user_days)
        self.stale_c.setValue(s.stale_computer_days)
        self.pwd_exp.setValue(s.password_expiring_days)
        self.recent.setValue(s.recent_days)
        self.required.setText(", ".join(s.required_user_attributes))
        self.std_groups.setText(", ".join(s.standard_groups))
        self.extra_priv.setText(", ".join(s.extra_privileged_groups))
        self.expiry_ous.setPlainText("\n".join(s.require_account_expiry_ous))
        self.os_rules.setPlainText("\n".join(f"{r.get('pattern', '')} | {r.get('note', '')}" for r in s.outdated_os))
        self.bulk_max.setValue(s.bulk_max_items)
        self.bulk_rate.setValue(s.bulk_rate_per_second)
        self.bulk_priv.setChecked(s.bulk_allow_privileged)
        self.net_timeout.setValue(s.network_timeout_s)
        self.ev_max.setValue(s.events_max)
        self.ev_timeout.setValue(s.events_timeout_s)
        self.upn.setText(s.upn_suffix)

    def save(self):
        split = lambda t: [x.strip() for x in t.split(",") if x.strip()]  # noqa: E731
        rules = []
        for line in self.os_rules.toPlainText().splitlines():
            if line.strip():
                pat, _, note = line.partition("|")
                rules.append({"pattern": pat.strip(), "note": note.strip()})
        from ...ldap.dn import DNSyntaxError, validate_dn
        ous = [l.strip() for l in self.expiry_ous.toPlainText().splitlines() if l.strip()]
        for ou in ous:
            try:
                validate_dn(ou)
            except DNSyntaxError as exc:
                from ..widgets.common import show_error
                show_error(self, exc)
                return
        s = AppSettings(theme=self.theme.currentData(), stale_user_days=self.stale_u.value(),
                        stale_computer_days=self.stale_c.value(), password_expiring_days=self.pwd_exp.value(),
                        recent_days=self.recent.value(), required_user_attributes=split(self.required.text()),
                        standard_groups=split(self.std_groups.text()), extra_privileged_groups=split(self.extra_priv.text()),
                        outdated_os=rules, require_account_expiry_ous=ous, bulk_max_items=self.bulk_max.value(),
                        bulk_rate_per_second=self.bulk_rate.value(), bulk_allow_privileged=self.bulk_priv.isChecked(),
                        search_debounce_ms=self.debounce.value(), search_result_limit=self.limit.value(),
                        events_max=self.ev_max.value(), events_timeout_s=self.ev_timeout.value(),
                        network_timeout_s=self.net_timeout.value(), clipboard_clear_s=self.clip.value(),
                        upn_suffix=self.upn.text().strip())
        old_theme = self.win.settings.theme
        self.win.settings_mgr.save(s)
        if self.win.ctx is not None:
            self.win.ctx.settings = s
            self.win.ctx.privileged.extra_names = list(s.extra_privileged_groups)
            self.win.ctx.privileged.invalidate()
        if s.theme != old_theme:
            self.win.apply_theme(s.theme)
        self.win.journal.record("settings.save", "app_settings", "success")
        self.win.toast("Настройки сохранены", "success")


class SearchPage(BasePage):
    title = "Результаты поиска"
    subtitle = "пользователи, компьютеры и группы"

    def __init__(self, win):
        super().__init__(win)
        self.label = QLabel("")
        self.root.addWidget(self.label)
        split = QSplitter(Qt.Vertical)
        self.users = DataTable([Column("name", "Пользователь"), Column("sam", "Логин"), Column("mail", "Email"),
                                Column("department", "Отдел"), Column("dn", "DN")], "search_users", win.db)
        self.computers = DataTable([Column("name", "Компьютер"), Column("dns", "DNS-имя"), Column("os", "ОС"),
                                    Column("dn", "DN")], "search_computers", win.db)
        self.groups = DataTable([Column("name", "Группа"), Column("description", "Описание"), Column("dn", "DN")],
                                "search_groups", win.db)
        self.users.activated.connect(lambda r: r and win.open_user(r["dn"]))
        self.computers.activated.connect(lambda r: r and win.open_computer(r["dn"]))
        self.groups.activated.connect(lambda r: r and win.open_group(r["dn"]))
        for t in (self.users, self.computers, self.groups):
            split.addWidget(t)
        self.root.addWidget(split, 1)
        self._seq = 0

    def search(self, text: str):
        if not self.need_ctx():
            return
        self._seq += 1
        seq = self._seq
        ctx = self.ctx
        limit = 200

        def job(cancel, progress):
            gw, base = ctx.gateway, ctx.base_dn
            users = gw.search_list(base, And(Q.IS_USER, Q.user_text_filter(text)),
                                   ["displayName", "cn", "sAMAccountName", "mail", "department"], size_limit=limit, cancel=cancel)
            comps = gw.search_list(base, And(Q.IS_COMPUTER, Or(Substring("cn", any=(text,)), Substring("dNSHostName", any=(text,)))),
                                   ["cn", "dNSHostName", "operatingSystem"], size_limit=limit, cancel=cancel)
            groups = gw.search_list(base, And(Q.IS_GROUP, Or(Substring("cn", any=(text,)), Substring("description", any=(text,)))),
                                    ["cn", "description"], size_limit=limit, cancel=cancel)
            return users, comps, groups

        def done(res):
            if seq != self._seq:
                return
            users, comps, groups = res
            self.users.set_rows([{"name": e.str("displayName") or e.str("cn") or rdn_value(e.dn), "sam": e.str("sAMAccountName"),
                                  "mail": e.str("mail"), "department": e.str("department"), "dn": e.dn} for e in users])
            self.computers.set_rows([{"name": e.str("cn"), "dns": e.str("dNSHostName"), "os": e.str("operatingSystem"),
                                      "dn": e.dn} for e in comps])
            self.groups.set_rows([{"name": e.str("cn"), "description": e.str("description"), "dn": e.dn} for e in groups])
            more = " (показаны первые 200 в каждой категории)" if max(len(users), len(comps), len(groups)) >= limit else ""
            self.label.setText(f"Запрос «{text}»: пользователей {len(users)}, компьютеров {len(comps)}, групп {len(groups)}{more}")
        self.run(job, done, f"Глобальный поиск: {text}")

