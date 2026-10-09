"""Administrator tools: password generator, DNS/LDAP checks, current user, membership check, comparisons, attribute
reference."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ...services import network_service as N
from ...services.attribute_reference import search_reference
from ...services.compare_service import CompareService
from ...services.group_service import GroupService
from ...services.ou_service import OUService
from ...services.password_service import PasswordOptions, entropy_bits, generate_password
from ...services.user_service import UserService
from ..widgets.common import copy_secret, report_meta, show_error
from ..widgets.table import Column, DataTable
from .base import BasePage

PROBE_COLUMNS = [Column("target", "Цель"), Column("check", "Проверка"), Column("status_text", "Результат"),
                 Column("message", "Подробности"), Column("duration_ms", "мс", align_right=True)]


def _dn_row(win, placeholder: str, kinds=("user",)):
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    btn = QPushButton("…")
    btn.setFixedWidth(34)
    btn.setProperty("small", True)

    def pick():
        from ..dialogs.pickers import ObjectPickerDialog
        dns = ObjectPickerDialog.pick(win, kinds, placeholder)
        if dns:
            edit.setText(dns[0])
    btn.clicked.connect(pick)
    row = QHBoxLayout()
    row.addWidget(edit, 1)
    row.addWidget(btn)
    w = QWidget()
    row.setContentsMargins(0, 0, 0, 0)
    w.setLayout(row)
    return edit, w


class ToolsPage(BasePage):
    title = "Инструменты"
    subtitle = "вспомогательные функции администратора"
    needs_connection = False

    def __init__(self, win):
        super().__init__(win)
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)
        self._password_tab()
        self._network_tab()
        self._whoami_tab()
        self._membership_tab()
        self._compare_users_tab()
        self._compare_groups_tab()
        self._compare_ou_tab()
        self._reference_tab()

    # ---------------------------------------------------------------------------------------------------------
    def _password_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.pw_len = QSpinBox()
        self.pw_len.setRange(8, 128)
        self.pw_len.setValue(16)
        self.pw_lower = QCheckBox("строчные a-z")
        self.pw_upper = QCheckBox("прописные A-Z")
        self.pw_digits = QCheckBox("цифры 0-9")
        self.pw_symbols = QCheckBox("спецсимволы")
        self.pw_ambig = QCheckBox("исключить похожие символы (Il1O0…)")
        for cb in (self.pw_lower, self.pw_upper, self.pw_digits, self.pw_symbols, self.pw_ambig):
            cb.setChecked(True)
        self.pw_symset = QLineEdit("!@#$%^&*()-_=+[]{}?")
        self.pw_count = QSpinBox()
        self.pw_count.setRange(1, 100)
        self.pw_count.setValue(5)
        form.addRow("Длина:", self.pw_len)
        form.addRow("Наборы:", self.pw_lower)
        form.addRow("", self.pw_upper)
        form.addRow("", self.pw_digits)
        form.addRow("", self.pw_symbols)
        form.addRow("Спецсимволы:", self.pw_symset)
        form.addRow("", self.pw_ambig)
        form.addRow("Количество:", self.pw_count)
        lay.addLayout(form)
        row = QHBoxLayout()
        gen = QPushButton("Сгенерировать")
        gen.setProperty("primary", True)
        gen.clicked.connect(self._gen_passwords)
        cp = QPushButton("Копировать первый (буфер очистится)")
        cp.clicked.connect(self._copy_first)
        row.addWidget(gen)
        row.addWidget(cp)
        row.addStretch(1)
        lay.addLayout(row)
        self.pw_entropy = QLabel("")
        lay.addWidget(self.pw_entropy)
        self.pw_out = QPlainTextEdit()
        self.pw_out.setReadOnly(True)
        self.pw_out.setStyleSheet("font-family: Consolas, monospace; font-size: 12pt;")
        lay.addWidget(self.pw_out, 1)
        note = QLabel("Пароли генерируются криптографически стойким ГСЧ (secrets) локально и нигде не сохраняются.")
        note.setObjectName("Muted")
        lay.addWidget(note)
        self.tabs.addTab(w, "Генератор паролей")

    def _pw_options(self) -> PasswordOptions:
        return PasswordOptions(length=self.pw_len.value(), lower=self.pw_lower.isChecked(), upper=self.pw_upper.isChecked(),
                               digits=self.pw_digits.isChecked(), symbols=self.pw_symbols.isChecked(),
                               exclude_ambiguous=self.pw_ambig.isChecked(), symbol_set=self.pw_symset.text())

    def _gen_passwords(self):
        try:
            opts = self._pw_options()
            pwds = [generate_password(opts) for _ in range(self.pw_count.value())]
        except ValueError as exc:
            show_error(self, exc)
            return
        self.pw_out.setPlainText("\n".join(pwds))
        bits = entropy_bits(opts)
        self.pw_entropy.setText(f"Энтропия ≈ {bits} бит " + ("(сильный)" if bits >= 80 else "(средний)" if bits >= 60 else "(слабый)"))

    def _copy_first(self):
        lines = self.pw_out.toPlainText().splitlines()
        if lines:
            copy_secret(lines[0], self.win.settings.clipboard_clear_s)
            self.win.toast(f"Скопировано; буфер очистится через {self.win.settings.clipboard_clear_s} с", "info")

    # ---------------------------------------------------------------------------------------------------------
    def _network_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.net_domain = QLineEdit()
        self.net_domain.setPlaceholderText("DNS-имя домена, например company.local")
        self.net_host = QLineEdit()
        self.net_host.setPlaceholderText("Контроллер домена или любой узел")
        self.net_ca = QLineEdit()
        self.net_ca.setPlaceholderText("необязательно: PEM-файл корневого ЦС")
        form.addRow("Домен:", self.net_domain)
        form.addRow("Узел / DC:", self.net_host)
        form.addRow("ЦС для TLS:", self.net_ca)
        lay.addLayout(form)
        row = QHBoxLayout()
        for text, fn in [("DNS-записи домена (SRV)", self._dns_checks), ("LDAP / LDAPS / StartTLS", self._ldap_checks),
                         ("Разрешение имени", self._resolve), ("Порты DC", self._dc_ports), ("Доступность узла", self._reach)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.net_table = DataTable(PROBE_COLUMNS, "net_checks", self.win.db, export_cb=self._export_net)
        self.net_table.set_state_fn(lambda r: {True: "ok", False: "danger"}.get(r.ok))
        lay.addWidget(self.net_table, 1)
        note = QLabel("Все проверки выполняются по-настоящему с тайм-аутом и показывают фактический результат с этого компьютера.")
        note.setObjectName("Muted")
        lay.addWidget(note)
        self.tabs.addTab(w, "DNS и LDAP")

    def _timeout(self) -> float:
        return float(self.win.settings.network_timeout_s)

    def _host(self) -> str | None:
        h = self.net_host.text().strip()
        if not h:
            self.win.toast("Укажите узел", "info")
            return None
        return h

    def _dns_checks(self):
        d = self.net_domain.text().strip()
        if not d:
            self.win.toast("Укажите DNS-имя домена", "info")
            return
        t = self._timeout()
        self.run(lambda c, p: N.domain_dns_checks(d, t, c, p), self.net_table.set_rows, "DNS-проверки домена")

    def _ldap_checks(self):
        h = self._host()
        if h:
            t, ca = self._timeout() + 2, self.net_ca.text().strip() or None
            self.run(lambda c, p: N.ldap_service_checks(h, t, ca, c, p), self.net_table.set_rows, "Проверка LDAP/LDAPS")

    def _resolve(self):
        h = self._host()
        if h:
            t = self._timeout()

            def job(c, p):
                r = [N.resolve(h, t)]
                for a in r[0].details.get("addresses", [])[:4]:
                    r.append(N.reverse_lookup(a, t))
                return r
            self.run(job, self.net_table.set_rows, "Разрешение имени")

    def _dc_ports(self):
        h = self._host()
        if h:
            t = self._timeout()
            self.run(lambda c, p: [N.tcp_check(h, port, t, label) for port, label in N.DC_PORTS], self.net_table.set_rows,
                     "Порты контроллера домена")

    def _reach(self):
        h = self._host()
        if h:
            t = self._timeout()
            self.run(lambda c, p: N.computer_reachability(h, t, c, p), self.net_table.set_rows, "Доступность узла")

    def _export_net(self):
        self.export(self.net_table.to_report("Результаты сетевых проверок", info=self.ctx.gateway.info if self.ctx else None),
                    "network_checks")

    # ---------------------------------------------------------------------------------------------------------
    def _whoami_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        b = QPushButton("Показать сведения о текущей учётной записи")
        b.clicked.connect(self._whoami)
        lay.addWidget(b, 0, Qt.AlignLeft)
        self.who = QPlainTextEdit()
        self.who.setReadOnly(True)
        lay.addWidget(self.who, 1)
        self.tabs.addTab(w, "Текущий пользователь")

    def _whoami(self):
        import getpass
        win_user = (os.environ.get("USERDOMAIN", "") + "\\" if os.environ.get("USERDOMAIN") else "") + getpass.getuser()
        lines = [f"Пользователь Windows: {win_user}", f"Компьютер: {os.environ.get('COMPUTERNAME', '')}"]
        if not self.connected():
            self.who.setPlainText("\n".join(lines + ["", "Нет подключения к AD."]))
            return
        ctx = self.ctx

        def job(c, p):
            s = ctx.permissions.rights_summary(ctx.privileged)
            details = []
            if s.user_dn:
                rec = UserService(ctx).get(s.user_dn)
                details = [f"Имя: {rec.name}", f"Логин: {rec.sam}", f"UPN: {rec.upn}", f"Email: {rec.mail}",
                           f"Отдел/должность: {rec.department} / {rec.title}", f"Пароль истекает: {rec.pwd_expires or 'никогда/—'}"]
            return s, details

        def done(res):
            s, details = res
            info = ctx.gateway.info
            out = lines + ["", f"LDAP-идентичность (WhoAmI): {s.identity}", f"DN: {s.user_dn or 'не определён'}"] + details + [
                "", f"Домен: {info.domain_dns}; DC: {info.dc_host}; канал: {info.security_label}",
                "", "Группы (tokenGroups, включая вложенные):"] + [f"  • {g}" for g in s.groups] + [
                "", "Привилегированные группы: " + (", ".join(s.privileged_groups) or "нет"),
                "Создание пользователей в CN=Users: " + {True: "да", False: "нет", None: "не определено"}[s.create_user_in_default],
                "", *s.notes]
            self.who.setPlainText("\n".join(out))
        self.run(job, done, "Сведения о текущем пользователе")

    # ---------------------------------------------------------------------------------------------------------
    def _membership_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.mem_user, uw = _dn_row(self.win, "Пользователь / компьютер / группа", ("user", "computer", "group"))
        self.mem_group, gw = _dn_row(self.win, "Группа", ("group",))
        form.addRow("Объект:", uw)
        form.addRow("Группа:", gw)
        lay.addLayout(form)
        row = QHBoxLayout()
        chk = QPushButton("Проверить членство")
        chk.clicked.connect(self._check_membership)
        allg = QPushButton("Все группы объекта (с путями)")
        allg.clicked.connect(self._all_groups)
        row.addWidget(chk)
        row.addWidget(allg)
        row.addStretch(1)
        lay.addLayout(row)
        self.mem_result = QLabel("")
        self.mem_result.setWordWrap(True)
        self.mem_result.setStyleSheet("font-size: 11pt; font-weight: 600;")
        lay.addWidget(self.mem_result)
        self.mem_table = DataTable([Column("name", "Группа"), Column("depth", "Уровень", align_right=True),
                                    Column("via", "Путь"), Column("dn", "DN")], "membership", self.win.db)
        lay.addWidget(self.mem_table, 1)
        self.tabs.addTab(w, "Проверка членства")

    def _check_membership(self):
        if not self.need_ctx():
            return
        u, g = self.mem_user.text().strip(), self.mem_group.text().strip()
        if not u or not g:
            self.win.toast("Укажите объект и группу", "info")
            return
        ctx = self.ctx
        self.run(lambda c, p: GroupService(ctx).is_member(u, g, True),
                 lambda r: self.mem_result.setText(("✔ Является членом: " if r[0] else "✖ Не является членом: ") + r[1]),
                 "Проверка членства")

    def _all_groups(self):
        if not self.need_ctx():
            return
        u = self.mem_user.text().strip()
        if not u:
            return
        ctx = self.ctx
        self.run(lambda c, p: UserService(ctx).group_paths(u, c),
                 lambda rows: self.mem_table.set_rows([{"name": r["name"] + (" (основная)" if r.get("primary") else ""),
                                                        "depth": r["depth"], "via": " → ".join(r["path"]) or "прямое",
                                                        "dn": r["dn"]} for r in rows]), "Группы объекта")

    # ---------------------------------------------------------------------------------------------------------
    def _compare_users_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.cu_a, aw = _dn_row(self.win, "Пользователь A")
        self.cu_b, bw = _dn_row(self.win, "Пользователь B")
        self.cu_trans = QCheckBox("Сравнивать группы с учётом вложенности")
        form.addRow("A:", aw)
        form.addRow("B:", bw)
        form.addRow("", self.cu_trans)
        lay.addLayout(form)
        b = QPushButton("Сравнить")
        b.clicked.connect(lambda: self.compare_users(self.cu_a.text().strip(), self.cu_b.text().strip()))
        lay.addWidget(b, 0, Qt.AlignLeft)
        t = QTabWidget()
        self.cu_attrs = DataTable([Column("attribute", "Атрибут"), Column("left", "A"), Column("right", "B"),
                                   Column("same", "Совпадает")], "cmp_users_attrs", self.win.db,
                                  export_cb=lambda: self._export_tbl(self.cu_attrs, "Сравнение пользователей — атрибуты"))
        self.cu_attrs.set_state_fn(lambda r: None if r["same"] else "warning")
        self.cu_groups = DataTable([Column("group", "Группа"), Column("where", "Где")], "cmp_users_groups", self.win.db,
                                   export_cb=lambda: self._export_tbl(self.cu_groups, "Сравнение пользователей — группы"))
        self.cu_groups.set_state_fn(lambda r: None if r["where"] == "у обоих" else "warning")
        t.addTab(self.cu_attrs, "Атрибуты")
        t.addTab(self.cu_groups, "Группы")
        lay.addWidget(t, 1)
        self.tabs.addTab(w, "Сравнение пользователей")

    def compare_users(self, a: str, b: str):
        self.win.navigate("tools")
        self.tabs.setCurrentIndex(4)
        self.cu_a.setText(a)
        self.cu_b.setText(b)
        if not self.need_ctx() or not a or not b:
            return
        ctx, trans = self.ctx, self.cu_trans.isChecked()

        def done(res):
            self.cu_attrs.set_rows(res.attributes)
            rows = [{"group": g, "where": "только у A"} for g in res.groups_only_left] + \
                   [{"group": g, "where": "только у B"} for g in res.groups_only_right] + \
                   [{"group": g, "where": "у обоих"} for g in res.groups_both]
            self.cu_groups.set_rows(rows)
        self.run(lambda c, p: CompareService(ctx).compare_users(a, b, transitive=trans, cancel=c), done,
                 "Сравнение пользователей")

    # ---------------------------------------------------------------------------------------------------------
    def _compare_groups_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.cg_a, aw = _dn_row(self.win, "Группа A", ("group",))
        self.cg_b, bw = _dn_row(self.win, "Группа B", ("group",))
        self.cg_trans = QCheckBox("С учётом вложенности")
        form.addRow("A:", aw)
        form.addRow("B:", bw)
        form.addRow("", self.cg_trans)
        lay.addLayout(form)
        b = QPushButton("Сравнить состав")
        b.clicked.connect(lambda: self.compare_groups(self.cg_a.text().strip(), self.cg_b.text().strip()))
        lay.addWidget(b, 0, Qt.AlignLeft)
        self.cg_table = DataTable([Column("name", "Участник"), Column("type", "Тип"), Column("where", "Где"),
                                   Column("dn", "DN")], "cmp_groups", self.win.db,
                                  export_cb=lambda: self._export_tbl(self.cg_table, "Сравнение состава групп"))
        self.cg_table.set_state_fn(lambda r: None if r["where"] == "в обеих" else "warning")
        lay.addWidget(self.cg_table, 1)
        self.tabs.addTab(w, "Сравнение групп")

    def compare_groups(self, a: str, b: str):
        self.win.navigate("tools")
        self.tabs.setCurrentIndex(5)
        self.cg_a.setText(a)
        self.cg_b.setText(b)
        if not self.need_ctx() or not a or not b:
            return
        ctx, trans = self.ctx, self.cg_trans.isChecked()

        def done(res):
            rows = [{"name": r.name, "type": r.object_type, "where": "только в A", "dn": r.dn} for r in res.only_left] + \
                   [{"name": r.name, "type": r.object_type, "where": "только в B", "dn": r.dn} for r in res.only_right] + \
                   [{"name": r.name, "type": r.object_type, "where": "в обеих", "dn": r.dn} for r in res.both]
            self.cg_table.set_rows(rows)
        self.run(lambda c, p: GroupService(ctx).compare(a, b, trans, c), done, "Сравнение групп")

    # ---------------------------------------------------------------------------------------------------------
    def _compare_ou_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        note = QLabel("Сравнение структуры OU «до/после» по сохранённым снимкам (Структура OU → «Сохранить снимок…»). "
                      "Можно сравнить снимок с текущим состоянием каталога.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)
        form = QFormLayout()
        self.ou_before = QLineEdit()
        self.ou_after = QLineEdit()
        self.ou_after.setPlaceholderText("пусто — текущее состояние каталога")
        for edit, label in ((self.ou_before, "До:"), (self.ou_after, "После:")):
            btn = QPushButton("…")
            btn.setFixedWidth(34)
            btn.setProperty("small", True)
            btn.clicked.connect(lambda _=False, e=edit: self._pick_snapshot(e))
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            row.addWidget(btn)
            rw = QWidget()
            row.setContentsMargins(0, 0, 0, 0)
            rw.setLayout(row)
            form.addRow(label, rw)
        lay.addLayout(form)
        b = QPushButton("Сравнить")
        b.clicked.connect(self._compare_ou)
        lay.addWidget(b, 0, Qt.AlignLeft)
        self.ou_diff = DataTable([Column("change", "Изменение"), Column("path", "OU"), Column("details", "Подробности")],
                                 "cmp_ou", self.win.db, export_cb=lambda: self._export_tbl(self.ou_diff, "Сравнение структуры OU"))
        self.ou_diff.set_state_fn(lambda r: {"Добавлено": "ok", "Удалено": "danger"}.get(r["change"], "warning"))
        lay.addWidget(self.ou_diff, 1)
        self.tabs.addTab(w, "Сравнение OU")

    def _pick_snapshot(self, edit):
        path, _ = QFileDialog.getOpenFileName(self, "Снимок OU", "", "Снимки (*.json *.csv)")
        if path:
            edit.setText(path)

    def _compare_ou(self):
        before, after = self.ou_before.text().strip(), self.ou_after.text().strip()
        if not before:
            self.win.toast("Укажите снимок «до»", "info")
            return
        if not after and not self.need_ctx():
            return
        ctx = self.ctx

        def job(c, p):
            b = OUService.load_snapshot(before)
            a = OUService.load_snapshot(after) if after else OUService(ctx).snapshot(c, p)
            return OUService.compare_snapshots(b, a), b, a

        def done(res):
            diff, b, a = res
            rows = [{"change": "Добавлено", "path": p, "details": ""} for p in diff.added] + \
                   [{"change": "Удалено", "path": p, "details": ""} for p in diff.removed] + \
                   [{"change": "Изменено", "path": d["path"],
                     "details": "; ".join(f"{k}: {v}" for k, v in d.items() if k != "path")} for d in diff.changed]
            self.ou_diff.set_rows(rows)
            self.win.toast(f"Снимки: {b.created_at} → {a.created_at}. Изменений: {len(rows)}", "info", 6000)
        self.run(job, done, "Сравнение структуры OU")

    # ---------------------------------------------------------------------------------------------------------
    def _reference_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.ref_search = QLineEdit()
        self.ref_search.setPlaceholderText("Поиск по имени или описанию атрибута…")
        lay.addWidget(self.ref_search)
        self.ref_table = DataTable([Column("name", "Атрибут"), Column("syntax", "Синтаксис"), Column("description", "Описание"),
                                    Column("replicated", "Репликация"), Column("notes", "Примечания")], "attr_ref", self.win.db)
        self.ref_table.set_rows(search_reference(""))
        self.ref_search.textChanged.connect(lambda t: self.ref_table.set_rows(search_reference(t)))
        lay.addWidget(self.ref_table, 1)
        self.tabs.addTab(w, "Справочник атрибутов")

    def _export_tbl(self, table, title):
        rep = report_meta(table.to_report(title), self.ctx.gateway.info if self.ctx else None)
        self.export(rep, "comparison")

