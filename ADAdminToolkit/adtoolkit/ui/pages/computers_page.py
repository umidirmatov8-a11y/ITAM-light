"""Computers module: views, OS classification, enable/disable, move, network checks, diagnostic lists, export."""
from __future__ import annotations

from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ...services import network_service as N
from ...services.computer_service import ComputerQuery, ComputerService, ComputerView
from ..widgets.common import banner, report_meta, set_banner
from ..widgets.table import Column, DataTable
from .base import BasePage

COMPUTER_TABLE_COLUMNS = [
    Column("name", "Имя", lambda c: c.name),
    Column("dns", "DNS-имя", lambda c: c.dns_host_name),
    Column("os", "ОС", lambda c: c.os),
    Column("os_version", "Версия", lambda c: c.os_version),
    Column("support", "Поддержка ОС", lambda c: {"supported": "да", "outdated": "устарела", "unknown": "?"}[c.os_support.value]),
    Column("enabled", "Включён", lambda c: c.enabled),
    Column("last", "Последняя активность*", lambda c: c.last_logon_timestamp),
    Column("days", "Дней без входа*", lambda c: c.days_since_logon(), align_right=True),
    Column("pwd", "Пароль сменён", lambda c: c.pwd_last_set, visible=False),
    Column("created", "Создан", lambda c: c.when_created),
    Column("ou", "OU", lambda c: c.ou),
    Column("description", "Описание", lambda c: c.description, visible=False),
    Column("dn", "DN", lambda c: c.dn, visible=False),
]


def computer_state(c) -> str | None:
    if not c.enabled:
        return "muted"
    if c.os_support.value == "outdated":
        return "warning"
    return None


class ReachabilityDialog(QDialog):
    def __init__(self, page, hosts: list[str]):
        super().__init__(page.win)
        self.page = page
        self.setWindowTitle(f"Проверка доступности: {len(hosts)} компьютеров")
        self.resize(820, 520)
        lay = QVBoxLayout(self)
        note = QLabel("Реальные сетевые проверки с тайм-аутом: DNS, ICMP, TCP 445 (SMB), TCP 3389 (RDP). Отсутствие ответа на "
                      "ping не означает, что компьютер выключен (ICMP часто блокируется брандмауэром).")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)
        self.table = DataTable([Column("host", "Узел"), Column("dns", "DNS"), Column("ping", "Ping"), Column("smb_445", "TCP 445"),
                                Column("rdp_3389", "TCP 3389"), Column("summary", "Итог")], "reachability", page.db,
                               export_cb=self._export)
        self.table.set_state_fn(lambda r: "ok" if r["summary"] == "Отвечает" else "danger")
        lay.addWidget(self.table, 1)
        timeout = float(page.win.settings.network_timeout_s)
        page.run(lambda c, p: N.batch_reachability(hosts, timeout, 16, c, p), self.table.set_rows,
                 "Проверка доступности компьютеров")

    def _export(self):
        rep = self.table.to_report("Список компьютеров для диагностики (доступность по сети)",
                                   criteria={"Проверки": "DNS, ICMP, TCP 445, TCP 3389"},
                                   limitations=["Результат отражает состояние на момент проверки с этой рабочей станции."])
        self.page.export(report_meta(rep, self.page.ctx.gateway.info if self.page.ctx else None), "computers_diagnostics")


class ComputersPage(BasePage):
    title = "Компьютеры"
    subtitle = "учётные записи компьютеров (состояние сети проверяется отдельно)"

    def __init__(self, win):
        super().__init__(win)
        filt = QWidget()
        g = QGridLayout(filt)
        g.setContentsMargins(0, 0, 0, 0)
        self.view = QComboBox()
        for v in ComputerView:
            self.view.addItem(v.label, v)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Имя компьютера, DNS-имя или описание")
        self.text.returnPressed.connect(self.refresh)
        self.os = QLineEdit()
        self.os.setPlaceholderText("ОС содержит…")
        self.ou = QLineEdit()
        self.ou.setPlaceholderText("OU (весь домен, если пусто)")
        ou_btn = QPushButton("…")
        ou_btn.setFixedWidth(34)
        ou_btn.setProperty("small", True)
        ou_btn.clicked.connect(self._pick_ou)
        self.days = QSpinBox()
        self.days.setRange(1, 3650)
        self.days.setValue(win.settings.stale_computer_days)
        self.days.setSuffix(" дн.")
        self.search_btn = QPushButton("Найти")
        self.search_btn.setProperty("primary", True)
        self.search_btn.clicked.connect(self.refresh)
        g.addWidget(QLabel("Представление:"), 0, 0)
        g.addWidget(self.view, 0, 1)
        g.addWidget(self.text, 0, 2)
        g.addWidget(self.os, 0, 3)
        g.addWidget(self.search_btn, 0, 4)
        g.addWidget(QLabel("OU:"), 1, 0)
        row = QHBoxLayout()
        row.addWidget(self.ou, 1)
        row.addWidget(ou_btn)
        g.addLayout(row, 1, 1, 1, 2)
        g.addWidget(QLabel("Период неактивности:"), 1, 3)
        g.addWidget(self.days, 1, 4)
        self.root.addWidget(filt)
        acts = QHBoxLayout()
        a = win.actions
        for text, fn in [("Карточка", self._open_current),
                         ("Включить", lambda: a.set_computer_enabled(self.table.selected_rows(), True, self.refresh)),
                         ("Отключить", lambda: a.set_computer_enabled(self.table.selected_rows(), False, self.refresh)),
                         ("Переместить", lambda: a.move(self.table.selected_rows(), "computer", self.refresh)),
                         ("Проверить доступность", self._reachability),
                         ("Список для диагностики", self._diag_list)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            acts.addWidget(b)
        acts.addStretch(1)
        self.root.addLayout(acts)
        self.notes = banner()
        self.root.addWidget(self.notes)
        self.table = DataTable(COMPUTER_TABLE_COLUMNS, "computers", win.db, export_cb=self._export, default_sort=0)
        self.table.set_state_fn(computer_state)
        self.table.activated.connect(lambda c: c and self.win.open_computer(c.dn))
        self.table.menu_builder = self._menu
        self.root.addWidget(self.table, 1)
        legend = QLabel("* LDAP не показывает, включён ли компьютер сейчас: lastLogonTimestamp обновляется с задержкой. "
                        "Цвет: серый — отключён, жёлтый — устаревшая ОС.")
        legend.setObjectName("Muted")
        legend.setWordWrap(True)
        self.root.addWidget(legend)
        self.last_result = None

    def show_view(self, key: str):
        for i in range(self.view.count()):
            if self.view.itemData(i) == key:
                self.view.setCurrentIndex(i)
        self.refresh()

    def initial_load(self):
        self.refresh()

    def refresh(self):
        if not self.need_ctx():
            return
        q = ComputerQuery(view=ComputerView(self.view.currentData()), text=self.text.text(), ou_dn=self.ou.text().strip(),
                          os_text=self.os.text(), stale_days=self.days.value(), recent_days=self.win.settings.recent_days,
                          limit=self.win.settings.search_result_limit)
        ctx = self.ctx
        self.search_btn.setEnabled(False)

        def done(res):
            self.search_btn.setEnabled(True)
            self.last_result = res
            self.table.set_rows(res.items)
            set_banner(self.notes, res.notes + [f"Фильтр LDAP: {res.filter_text}"])

        def failed(exc):
            self.search_btn.setEnabled(True)
            from ..widgets.common import show_error
            show_error(self, exc)
        self.run(lambda c, p: ComputerService(ctx).search(q, c, p), done, f"Компьютеры: {q.view.label}", on_error=failed)

    def on_disconnected(self):
        super().on_disconnected()
        self.table.set_rows([])

    def _pick_ou(self):
        from ..dialogs.pickers import OUPickerDialog
        dn = OUPickerDialog.pick(self.win)
        if dn:
            self.ou.setText(dn)

    def _open_current(self):
        r = self.table.current_row()
        if r:
            self.win.open_computer(r.dn)

    def _hosts(self, rows):
        return [r.dns_host_name or r.name for r in rows]

    def _reachability(self):
        rows = self.table.selected_rows()
        if not rows:
            self.win.toast("Выберите компьютеры в таблице", "info")
            return
        if len(rows) > 500:
            self.win.toast("Не более 500 компьютеров за одну проверку", "warning")
            return
        ReachabilityDialog(self, self._hosts(rows)).show()

    def _diag_list(self):
        rows = self.table.selected_rows() or self.table.visible_rows()
        if not rows:
            return
        rep = self.table.to_report("Компьютеры для диагностики", rows=rows,
                                   criteria=self.last_result.criteria if self.last_result else {},
                                   limitations=(self.last_result.notes if self.last_result else []) +
                                   ["Список подготовлен по данным LDAP; сетевая доступность не проверялась."],
                                   info=self.ctx.gateway.info if self.ctx else None)
        self.export(rep, "computers_for_diagnostics")

    def _menu(self, menu: QMenu, rows: list):
        a = self.win.actions
        menu.addAction("Открыть карточку", lambda: self.win.open_computer(rows[0].dn))
        menu.addAction("Копировать имя", lambda: QApplication.clipboard().setText("\n".join(r.name for r in rows)))
        menu.addAction("Копировать DNS-имя", lambda: QApplication.clipboard().setText("\n".join(r.dns_host_name for r in rows)))
        menu.addAction("Копировать DN", lambda: QApplication.clipboard().setText("\n".join(r.dn for r in rows)))
        menu.addSeparator()
        menu.addAction("Проверить доступность", self._reachability)
        menu.addAction("Включить", lambda: a.set_computer_enabled(rows, True, self.refresh))
        menu.addAction("Отключить", lambda: a.set_computer_enabled(rows, False, self.refresh))
        menu.addAction("Переместить в OU…", lambda: a.move(rows, "computer", self.refresh))
        menu.addAction("Добавить в группу…", lambda: a.add_to_group([r.dn for r in rows], self.refresh, kind="computer"))

    def _export(self):
        res = self.last_result
        rep = self.table.to_report(f"Компьютеры — {ComputerView(self.view.currentData()).label}", criteria=res.criteria if res else {},
                                   limitations=res.notes if res else [], info=self.ctx.gateway.info if self.ctx else None)
        self.export(rep, "computers")
