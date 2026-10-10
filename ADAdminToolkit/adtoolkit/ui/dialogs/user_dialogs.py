"""User dialogs: details card, edit, reset password, account expiry, create (template / copy)."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QRadioButton, QTabWidget, QVBoxLayout, QWidget, QApplication)

from ...ldap.adtypes import display_value, format_dt, uac_flags_text
from ...ldap.dn import rdn_value
from ...services.password_service import (PasswordOptions, generate_password, policy_summary, validate_against_policy)
from ...services.user_service import EDITABLE_ATTRIBUTES, LASTLOGON_NOTE, NewUserSpec, UserService, make_sam
from ..widgets.common import PasswordField, banner, copy_secret, set_banner, show_error
from ..widgets.table import Column, DataTable


def _ro(text: str) -> QLabel:
    lbl = QLabel(text or "—")
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lbl.setWordWrap(True)
    return lbl


class UserDetailsDialog(QDialog):
    def __init__(self, win, dn: str):
        super().__init__(win)
        self.win = win
        self.dn = dn
        self.record = None
        self.setWindowTitle("Пользователь")
        self.resize(900, 640)
        lay = QVBoxLayout(self)
        self.header = QLabel("Загрузка…")
        self.header.setObjectName("PageTitle")
        lay.addWidget(self.header)
        self.state = QLabel("")
        lay.addWidget(self.state)
        self.warn = banner()
        lay.addWidget(self.warn)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.general = QWidget()
        self.general_form = QFormLayout(self.general)
        self.account = QWidget()
        self.account_form = QFormLayout(self.account)
        self.tabs.addTab(self.general, "Общие")
        self.tabs.addTab(self.account, "Учётная запись")
        # groups tab
        gw = QWidget()
        gl = QVBoxLayout(gw)
        self.groups = DataTable([Column("name", "Группа"), Column("depth", "Уровень", align_right=True),
                                 Column("via", "Как получено"), Column("dn", "DN")], "user_groups", win.db)
        gl.addWidget(self.groups, 1)
        gb = QHBoxLayout()
        self.btn_add_group = QPushButton("Добавить в группу…")
        self.btn_remove_group = QPushButton("Удалить из выбранной группы")
        gb.addWidget(self.btn_add_group)
        gb.addWidget(self.btn_remove_group)
        gb.addStretch(1)
        gl.addLayout(gb)
        self.tabs.addTab(gw, "Группы (прямые и косвенные)")
        # raw attributes
        aw = QWidget()
        al = QVBoxLayout(aw)
        self.attrs = DataTable([Column("name", "Атрибут"), Column("value", "Значение")], "user_attrs", win.db)
        al.addWidget(self.attrs)
        self.tabs.addTab(aw, "Все атрибуты")
        # precise logon
        lw = QWidget()
        ll = QVBoxLayout(lw)
        note = QLabel(LASTLOGON_NOTE)
        note.setWordWrap(True)
        note.setObjectName("Muted")
        ll.addWidget(note)
        self.logon_btn = QPushButton("Опросить все контроллеры домена (lastLogon)")
        self.logon_btn.clicked.connect(self._precise_logon)
        ll.addWidget(self.logon_btn, 0, Qt.AlignLeft)
        self.logon = DataTable([Column("dc", "Контроллер"), Column("last_logon", "lastLogon"), Column("error", "Ошибка")],
                               show_toolbar=False)
        ll.addWidget(self.logon, 1)
        self.tabs.addTab(lw, "Точный последний вход")

        # actions
        act = QGridLayout()
        self.buttons = {}
        specs = [("enable", "Включить"), ("disable", "Отключить"), ("unlock", "Разблокировать"),
                 ("reset", "Сбросить пароль…"), ("must", "Сменить пароль при входе"), ("expiry", "Срок действия…"),
                 ("edit", "Изменить атрибуты…"), ("move", "Переместить…"), ("copy_dn", "Копировать DN"),
                 ("copy_sam", "Копировать логин"), ("refresh", "Обновить")]
        for i, (key, text) in enumerate(specs):
            b = QPushButton(text)
            self.buttons[key] = b
            act.addWidget(b, i // 6, i % 6)
        lay.addLayout(act)
        a = win.actions
        rows = lambda: [self.record] if self.record else []  # noqa: E731
        self.buttons["enable"].clicked.connect(lambda: a.set_user_enabled(rows(), True, self.reload))
        self.buttons["disable"].clicked.connect(lambda: a.set_user_enabled(rows(), False, self.reload))
        self.buttons["unlock"].clicked.connect(lambda: a.unlock(rows(), self.reload))
        self.buttons["reset"].clicked.connect(lambda: a.reset_password(self.record, self.reload))
        self.buttons["must"].clicked.connect(lambda: a.must_change(self.record, True, self.reload))
        self.buttons["expiry"].clicked.connect(lambda: a.set_expiry(self.record, self.reload))
        self.buttons["edit"].clicked.connect(lambda: a.edit_user(self.record, self.reload))
        self.buttons["move"].clicked.connect(lambda: a.move(rows(), "user", self._moved))
        self.buttons["copy_dn"].clicked.connect(lambda: QApplication.clipboard().setText(self.dn))
        self.buttons["copy_sam"].clicked.connect(lambda: QApplication.clipboard().setText(self.record.sam if self.record else ""))
        self.buttons["refresh"].clicked.connect(self.reload)
        self.btn_add_group.clicked.connect(lambda: a.add_to_group([self.dn], self.reload))
        self.btn_remove_group.clicked.connect(self._remove_group)
        self.reload()

    def _moved(self):
        # after a move the DN changed: re-find by sAMAccountName
        sam = self.record.sam if self.record else ""
        found = UserService(self.win.ctx).find_by_identity(sam) if sam else []
        if found:
            self.dn = found[0].dn
        self.reload()

    def reload(self):
        ctx = self.win.ctx
        if ctx is None:
            return

        def job(cancel, progress):
            us = UserService(ctx)
            rec, who = us.get_with_sd(self.dn)
            groups = us.group_paths(self.dn, cancel)
            raw = us.raw_attributes(self.dn)
            reason = us.privileged_reason(self.dn)
            return rec, who, groups, raw, reason
        self.win.run_task(job, self._fill, title="Загрузка пользователя")

    def _fill(self, data):
        rec, who, groups, raw, reason = data
        self.record = rec
        self.setWindowTitle(f"Пользователь — {rec.name}")
        self.header.setText(f"{rec.name}  ({rec.sam})")
        colors = {"active": "ok", "disabled": "muted", "locked": "danger", "expired": "warning", "pwd_expired": "warning"}
        self.state.setText(f"Состояние: <b>{rec.state.label}</b>" + (f" · {reason}" if reason else ""))
        self.state.setProperty("state", colors.get(rec.state.value))
        warn = []
        if reason:
            warn.append("Привилегированная учётная запись: изменения требуют отдельного подтверждения. " + reason)
        if rec.pwd_never_expires:
            warn.append("Установлен флаг Password Never Expires")
        set_banner(self.warn, warn)
        for form in (self.general_form, self.account_form):
            while form.rowCount():
                form.removeRow(0)
        g = self.general_form
        for label, value in [("Отображаемое имя", rec.display_name), ("Имя", rec.given_name), ("Фамилия", rec.surname),
                             ("Логин (sAMAccountName)", rec.sam), ("UPN", rec.upn), ("Email", rec.mail),
                             ("Отдел", rec.department), ("Должность", rec.title), ("Организация", rec.company),
                             ("Руководитель", rec.manager_name), ("Телефон", rec.phone), ("Мобильный", rec.mobile),
                             ("Офис", rec.office), ("Табельный номер", rec.employee_id), ("Описание", rec.description),
                             ("OU", rec.ou), ("DN", rec.dn), ("SID", rec.sid)]:
            g.addRow(label + ":", _ro(value))
        a = self.account_form
        lock_text = "Да" if rec.locked else "Нет"
        if rec.lockout_time:
            lock_text += f" (lockoutTime {format_dt(rec.lockout_time)})"
        if not rec.locked_exact:
            lock_text += " — оценка"
        rows = [("Включена", "Да" if rec.enabled else "Нет"), ("Заблокирована", lock_text),
                ("Пароль установлен", "сменить при следующем входе" if rec.must_change_password else format_dt(rec.pwd_last_set)),
                ("Пароль истекает", "никогда (PNE)" if rec.pwd_never_expires else (format_dt(rec.pwd_expires) or "—")),
                ("Пароль истёк", "Да" if rec.pwd_expired else "Нет"),
                ("Запрет смены пароля (ACL)", {True: "Да (" + ", ".join(who) + ")", False: "Нет", None: "не определено (нет прав на чтение ACL)"}[rec.cannot_change_password]),
                ("Срок действия УЗ", format_dt(rec.account_expires) or "бессрочно"),
                ("Последний вход (lastLogonTimestamp)", format_dt(rec.last_logon_timestamp) or "нет данных (см. ограничения)"),
                ("Создана", format_dt(rec.when_created)), ("Изменена", format_dt(rec.when_changed)),
                ("Неверных паролей (на этом DC)", str(rec.bad_pwd_count if rec.bad_pwd_count is not None else "—")),
                ("adminCount", str(rec.admin_count)), ("userAccountControl", f"{rec.uac}: " + "; ".join(uac_flags_text(rec.uac)))]
        for label, value in rows:
            a.addRow(label + ":", _ro(value))
        self.groups.set_rows([{"name": g["name"] + (" (основная)" if g.get("primary") else "") + (" ⟳ цикл" if g.get("cycle") else ""),
                               "depth": g["depth"], "via": "прямое" if not g["path"] else "через " + " → ".join(g["path"]),
                               "dn": g["dn"], "direct": not g["path"]} for g in groups])
        self.groups.set_state_fn(lambda r: None if r["direct"] else "muted")
        self.attrs.set_rows(sorted(({"name": k, "value": "; ".join(display_value(k, v) for v in vals)}
                                    for k, vals in raw.items()), key=lambda r: r["name"].lower()))
        self.buttons["enable"].setEnabled(not rec.enabled)
        self.buttons["disable"].setEnabled(rec.enabled)
        self.buttons["unlock"].setEnabled(bool(rec.lockout_time))

    def _remove_group(self):
        r = self.groups.current_row()
        if not r:
            return
        if not r["direct"]:
            self.win.toast("Косвенное членство нельзя снять здесь — удалите вложенную группу или пользователя из неё.", "warning")
            return
        if "(основная)" in r["name"]:
            self.win.toast("Основная группа (primaryGroupID) не снимается удалением из группы.", "warning")
            return
        self.win.actions.remove_from_group(r["dn"], [self.dn], self.reload)

    def _precise_logon(self):
        ctx = self.win.ctx
        self.win.run_task(lambda c, p: UserService(ctx).precise_last_logon(self.dn, c, p),
                          lambda rows: self.logon.set_rows(rows), title="Опрос контроллеров домена")


class ResetPasswordDialog(QDialog):
    def __init__(self, win, record):
        super().__init__(win)
        self.win = win
        self.record = record
        self.setWindowTitle(f"Сброс пароля — {record.name}")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        policy = win.ctx.policy if win.ctx else None
        info = QLabel(policy_summary(policy))
        info.setWordWrap(True)
        info.setObjectName("Muted")
        lay.addWidget(info)
        form = QFormLayout()
        self.p1 = PasswordField(self, "Новый пароль")
        self.p2 = PasswordField(self, "Повторите пароль")
        form.addRow("Новый пароль:", self.p1)
        form.addRow("Подтверждение:", self.p2)
        lay.addLayout(form)
        gen = QHBoxLayout()
        b = QPushButton("Сгенерировать")
        b.clicked.connect(self._generate)
        self.copy_btn = QPushButton("Копировать (очистка буфера через 30 с)")
        self.copy_btn.clicked.connect(lambda: (copy_secret(self.p1.text(), win.settings.clipboard_clear_s),
                                               win.toast("Пароль скопирован; буфер будет очищен", "info")))
        gen.addWidget(b)
        gen.addWidget(self.copy_btn)
        gen.addStretch(1)
        lay.addLayout(gen)
        self.must = QCheckBox("Потребовать смену пароля при следующем входе")
        self.must.setChecked(True)
        self.unlock = QCheckBox("Разблокировать учётную запись")
        self.unlock.setChecked(bool(record.locked))
        lay.addWidget(self.must)
        lay.addWidget(self.unlock)
        self.problems = banner(danger=True)
        lay.addWidget(self.problems)
        note = QLabel("Пароль передаётся только по зашифрованному соединению и не сохраняется в журналах, настройках "
                      "и отчётах. История паролей и PSO проверяются контроллером домена.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)
        bb = QDialogButtonBox()
        self.ok = bb.addButton("Сбросить пароль", QDialogButtonBox.AcceptRole)
        self.ok.setProperty("primary", True)
        bb.addButton("Отмена", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.p1.edit.textChanged.connect(self._validate)
        self.p2.edit.textChanged.connect(self._validate)
        self._validate()

    def _generate(self):
        length = max(16, (self.win.ctx.policy.min_pwd_length if self.win.ctx else 0) + 4)
        pwd = generate_password(PasswordOptions(length=length))
        self.p1.setText(pwd)
        self.p2.setText(pwd)
        self.p1.toggle.setChecked(True)

    def _validate(self):
        problems = []
        pwd = self.p1.text()
        if pwd:
            problems = validate_against_policy(pwd, self.win.ctx.policy if self.win.ctx else None, self.record.sam,
                                               self.record.display_name)
            if self.p2.text() and pwd != self.p2.text():
                problems.append("Пароли не совпадают")
        set_banner(self.problems, problems)
        self.ok.setEnabled(bool(pwd) and pwd == self.p2.text() and not problems)

    def _accept(self):
        if self.ok.isEnabled():
            self.accept()

    def values(self) -> tuple[str, bool, bool]:
        return self.p1.text(), self.must.isChecked(), self.unlock.isChecked()

    def clear_secret(self):
        self.p1.clear()
        self.p2.clear()


class AccountExpiryDialog(QDialog):
    def __init__(self, win, record):
        super().__init__(win)
        self.setWindowTitle(f"Срок действия — {record.name}")
        lay = QVBoxLayout(self)
        self.never = QRadioButton("Бессрочно")
        self.until = QRadioButton("Действует по (включительно):")
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        if record.account_expires:
            d = record.account_expires.astimezone().date()
            self.date.setDate(QDate(d.year, d.month, d.day).addDays(-1))
            self.until.setChecked(True)
        else:
            self.date.setDate(QDate.currentDate().addMonths(3))
            self.never.setChecked(True)
        lay.addWidget(self.never)
        row = QHBoxLayout()
        row.addWidget(self.until)
        row.addWidget(self.date)
        lay.addLayout(row)
        hint = QLabel("Как в ADUC: учётная запись перестаёт действовать в начале следующего дня (локальное время).")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def value(self) -> date | None:
        if self.never.isChecked():
            return None
        q = self.date.date()
        return date(q.year(), q.month(), q.day())


class EditUserDialog(QDialog):
    def __init__(self, win, dn: str):
        super().__init__(win)
        self.win = win
        self.dn = dn
        self.setWindowTitle("Изменение атрибутов пользователя")
        self.resize(560, 620)
        lay = QVBoxLayout(self)
        note = QLabel("Изменяются только разрешённые атрибуты. Перед записью проверяются права "
                      "(allowedAttributesEffective); при одновременном изменении объекта другим администратором "
                      "операция будет отклонена как конфликт.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)
        form = QFormLayout()
        self.edits: dict[str, QLineEdit] = {}
        for attr, label in EDITABLE_ATTRIBUTES.items():
            e = QLineEdit()
            e.setEnabled(False)
            self.edits[attr] = e
            if attr == "manager":
                row = QHBoxLayout()
                row.addWidget(e, 1)
                pick = QPushButton("…")
                pick.setFixedWidth(34)
                pick.setProperty("small", True)
                pick.clicked.connect(self._pick_manager)
                row.addWidget(pick)
                w = QWidget()
                w.setLayout(row)
                row.setContentsMargins(0, 0, 0, 0)
                form.addRow(label + ":", w)
            else:
                form.addRow(label + ":", e)
        lay.addLayout(form)
        self.rights = QLabel("")
        self.rights.setObjectName("Muted")
        self.rights.setWordWrap(True)
        lay.addWidget(self.rights)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.original: dict[str, str] = {}
        ctx = win.ctx

        def job(cancel, progress):
            e = ctx.gateway.get(dn, list(EDITABLE_ATTRIBUTES) + ["allowedAttributesEffective"])
            return e
        win.run_task(job, self._fill, title="Чтение атрибутов")

    def _fill(self, e):
        if e is None:
            show_error(self, Exception("Объект не найден"))
            return
        allowed = {str(a).lower() for a in e.values("allowedAttributesEffective")}
        denied = []
        for attr, edit in self.edits.items():
            v = e.str(attr)
            self.original[attr] = v
            edit.setText(v)
            can = attr.lower() in allowed
            edit.setEnabled(can)
            if not can:
                denied.append(EDITABLE_ATTRIBUTES[attr])
        self.rights.setText("Нет прав на изменение: " + ", ".join(denied) if denied else "Права на запись всех атрибутов есть.")

    def _pick_manager(self):
        from .pickers import ObjectPickerDialog
        dns = ObjectPickerDialog.pick(self.win, ("user",), "Руководитель")
        if dns:
            self.edits["manager"].setText(dns[0])

    def changes(self) -> tuple[dict, dict]:
        new = {}
        for attr, edit in self.edits.items():
            if edit.isEnabled() and edit.text().strip() != (self.original.get(attr) or ""):
                new[attr] = edit.text().strip()
        return new, {k: self.original.get(k) for k in new}


class CreateUserDialog(QDialog):
    """Create a user from a template or by copying allowed attributes/groups of an existing user."""

    def __init__(self, win, copy_from_dn: str = ""):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Создание пользователя")
        self.resize(760, 720)
        self.groups: list[str] = []
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.template = QComboBox()
        self.template.addItem("— без шаблона —", None)
        for t in win.db.templates("user"):
            self.template.addItem(t["name"], t)
        top.addWidget(QLabel("Шаблон:"))
        top.addWidget(self.template, 1)
        save_t = QPushButton("Сохранить как шаблон…")
        save_t.clicked.connect(self._save_template)
        top.addWidget(save_t)
        copy_btn = QPushButton("Копировать из пользователя…")
        copy_btn.clicked.connect(self._copy_from)
        top.addWidget(copy_btn)
        lay.addLayout(top)
        form = QFormLayout()
        self.ou = QLineEdit()
        ou_btn = QPushButton("…")
        ou_btn.setFixedWidth(34)
        ou_btn.setProperty("small", True)
        ou_btn.clicked.connect(self._pick_ou)
        ou_row = QHBoxLayout()
        ou_row.addWidget(self.ou, 1)
        ou_row.addWidget(ou_btn)
        ou_w = QWidget()
        ou_row.setContentsMargins(0, 0, 0, 0)
        ou_w.setLayout(ou_row)
        self.given = QLineEdit()
        self.sn = QLineEdit()
        self.display = QLineEdit()
        self.sam = QLineEdit()
        self.sam.setMaxLength(20)
        self.upn = QLineEdit()
        self.pattern = QLineEdit("{g_lat}.{sn_lat}")
        self.pattern.setToolTip("Подстановки: {given} {sn} {g} {s} {given_lat} {sn_lat} {g_lat} {s_lat}")
        form.addRow("OU:", ou_w)
        form.addRow("Имя:", self.given)
        form.addRow("Фамилия:", self.sn)
        form.addRow("Отображаемое имя:", self.display)
        form.addRow("Шаблон логина:", self.pattern)
        form.addRow("Логин (sAMAccountName):", self.sam)
        form.addRow("UPN:", self.upn)
        lay.addLayout(form)
        attrs_box = QGroupBox("Атрибуты")
        af = QFormLayout(attrs_box)
        self.attr_edits: dict[str, QLineEdit] = {}
        for a in ["department", "title", "company", "physicalDeliveryOfficeName", "mail", "telephoneNumber", "employeeID",
                  "description", "l", "manager"]:
            e = QLineEdit()
            self.attr_edits[a] = e
            af.addRow(EDITABLE_ATTRIBUTES.get(a, a) + ":", e)
        lay.addWidget(attrs_box)
        pw_box = QGroupBox("Пароль и состояние")
        pf = QFormLayout(pw_box)
        self.password = PasswordField(self, "Начальный пароль")
        gen = QPushButton("Сгенерировать")
        gen.clicked.connect(self._gen)
        prow = QHBoxLayout()
        prow.addWidget(self.password, 1)
        prow.addWidget(gen)
        pw = QWidget()
        prow.setContentsMargins(0, 0, 0, 0)
        pw.setLayout(prow)
        pf.addRow("Пароль:", pw)
        self.must = QCheckBox("Сменить пароль при первом входе")
        self.must.setChecked(True)
        self.enabled = QCheckBox("Включить учётную запись после создания")
        self.enabled.setChecked(True)
        pf.addRow(self.must)
        pf.addRow(self.enabled)
        lay.addWidget(pw_box)
        gb = QGroupBox("Группы")
        gl = QVBoxLayout(gb)
        self.group_list = QListWidget()
        gl.addWidget(self.group_list)
        gbtn = QHBoxLayout()
        add_g = QPushButton("Добавить группу…")
        add_g.clicked.connect(self._add_group)
        rem_g = QPushButton("Убрать")
        rem_g.clicked.connect(self._remove_group)
        gbtn.addWidget(add_g)
        gbtn.addWidget(rem_g)
        gbtn.addStretch(1)
        gl.addLayout(gbtn)
        self.priv_ok = QCheckBox("Подтверждаю добавление в привилегированные группы (если есть в списке)")
        gl.addWidget(self.priv_ok)
        lay.addWidget(gb)
        self.problems = banner(danger=True)
        lay.addWidget(self.problems)
        bb = QDialogButtonBox()
        self.ok = bb.addButton("Создать", QDialogButtonBox.AcceptRole)
        self.ok.setProperty("primary", True)
        bb.addButton("Отмена", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._create)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for w in (self.given, self.sn, self.pattern):
            w.textChanged.connect(self._auto)
        self.template.currentIndexChanged.connect(self._apply_template)
        ctx = win.ctx
        self.ou.setText(f"CN=Users,{ctx.base_dn}")
        self.suffix = win.settings.upn_suffix or ctx.gateway.info.domain_dns
        if copy_from_dn:
            self._do_copy(copy_from_dn)

    def _auto(self):
        sam = make_sam(self.pattern.text() or "{g_lat}.{sn_lat}", self.given.text(), self.sn.text()) if (self.given.text() or self.sn.text()) else ""
        self.sam.setText(sam)
        self.upn.setText(f"{sam}@{self.suffix}" if sam else "")
        self.display.setText(f"{self.sn.text().strip()} {self.given.text().strip()}".strip())

    def _apply_template(self):
        t = self.template.currentData()
        if not t:
            return
        if t.get("ou_dn"):
            self.ou.setText(t["ou_dn"])
        if t.get("sam_pattern"):
            self.pattern.setText(t["sam_pattern"])
        if t.get("upn_suffix"):
            self.suffix = t["upn_suffix"]
        for k, v in (t.get("attributes") or {}).items():
            if k in self.attr_edits:
                self.attr_edits[k].setText(v)
        self.groups = list(t.get("groups") or [])
        self._refresh_groups()
        self.must.setChecked(bool(t.get("must_change", True)))
        self.enabled.setChecked(bool(t.get("enabled", True)))
        self._auto()

    def _save_template(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Шаблон", "Имя шаблона:")
        if not ok or not name.strip():
            return
        data = {"ou_dn": self.ou.text().strip(), "sam_pattern": self.pattern.text().strip(), "upn_suffix": self.suffix,
                "attributes": {k: e.text().strip() for k, e in self.attr_edits.items()
                               if e.text().strip() and k not in ("mail", "telephoneNumber", "employeeID")},
                "groups": list(self.groups), "must_change": self.must.isChecked(), "enabled": self.enabled.isChecked()}
        self.win.db.save_template("user", name.strip(), data)
        self.template.addItem(name.strip(), {"name": name.strip(), **data})
        self.win.toast("Шаблон сохранён (без пароля)", "success")

    def _copy_from(self):
        from .pickers import ObjectPickerDialog
        dns = ObjectPickerDialog.pick(self.win, ("user",), "Пользователь-образец")
        if dns:
            self._do_copy(dns[0])

    def _do_copy(self, dn):
        ctx = self.win.ctx

        def done(res):
            spec, notes = res
            self.ou.setText(spec.ou_dn)
            for k, v in spec.attributes.items():
                if k in self.attr_edits:
                    self.attr_edits[k].setText(v)
            self.groups = list(spec.groups)
            self._refresh_groups()
            if spec.upn and "@" in spec.upn:
                self.suffix = spec.upn.split("@", 1)[1]
            self._auto()
            self.win.toast("Скопировано из «" + rdn_value(dn) + "». " + " ".join(notes), "info", 8000)
        self.win.run_task(lambda c, p: UserService(ctx).spec_copy_from(dn, self.given.text(), self.sn.text()), done,
                          title="Копирование атрибутов")

    def _pick_ou(self):
        from .pickers import OUPickerDialog
        dn = OUPickerDialog.pick(self.win)
        if dn:
            self.ou.setText(dn)

    def _gen(self):
        policy = self.win.ctx.policy if self.win.ctx else None
        self.password.setText(generate_password(PasswordOptions(length=max(16, (policy.min_pwd_length if policy else 0) + 4))))
        self.password.toggle.setChecked(True)

    def _add_group(self):
        from .pickers import ObjectPickerDialog
        for dn in ObjectPickerDialog.pick(self.win, ("group",), "Группы", multi=True):
            if dn not in self.groups:
                self.groups.append(dn)
        self._refresh_groups()

    def _remove_group(self):
        row = self.group_list.currentRow()
        if 0 <= row < len(self.groups):
            del self.groups[row]
            self._refresh_groups()

    def _refresh_groups(self):
        self.group_list.clear()
        for g in self.groups:
            item = QListWidgetItem(rdn_value(g))
            item.setToolTip(g)
            self.group_list.addItem(item)

    def spec(self) -> NewUserSpec:
        return NewUserSpec(ou_dn=self.ou.text().strip(), given_name=self.given.text().strip(), surname=self.sn.text().strip(),
                           sam=self.sam.text().strip(), upn=self.upn.text().strip(), display_name=self.display.text().strip(),
                           password=self.password.text() or None, must_change=self.must.isChecked(),
                           enabled=self.enabled.isChecked(),
                           attributes={k: e.text().strip() for k, e in self.attr_edits.items() if e.text().strip()},
                           groups=list(self.groups), privileged_groups_confirmed=self.priv_ok.isChecked())

    def _create(self):
        ctx = self.win.ctx
        spec = self.spec()
        problems = UserService(ctx).validate_new_user(spec)
        if problems:
            set_banner(self.problems, problems)
            return
        set_banner(self.problems, [])
        self.ok.setEnabled(False)

        def done(res):
            self.password.clear()
            msg = f"Создан пользователь: {res.dn}" + ("" if res.enabled else " (отключён)")
            if res.warnings:
                show_error(self, Exception("Создано с предупреждениями:\n" + "\n".join(res.warnings)), "Предупреждения")
            self.win.toast(msg, "success", 7000)
            self.accept()

        def failed(exc):
            self.ok.setEnabled(True)
            show_error(self, exc)
        self.win.run_task(lambda c, p: UserService(ctx).create_user(spec), done, title="Создание пользователя",
                          on_error=failed)
