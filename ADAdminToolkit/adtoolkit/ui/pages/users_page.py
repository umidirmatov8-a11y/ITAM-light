"""Users module: views, search, filters, saved filters, colour state, context menu, administration, export."""
from __future__ import annotations

from PySide6.QtWidgets import (QApplication, QComboBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMenu, QPushButton, QSpinBox, QToolButton, QWidget)

from ...services.bulk_service import BulkOperation
from ...services.user_service import UserQuery, UserService, UserView
from ..widgets.common import banner, set_banner
from ..widgets.table import Column, DataTable
from .base import BasePage


def user_state(u) -> str | None:
    if not u.enabled:
        return "muted"
    if u.locked:
        return "danger"
    if u.account_expired or u.pwd_expired:
        return "warning"
    return None


USER_TABLE_COLUMNS = [
    Column("name", "Имя", lambda u: u.name),
    Column("sam", "Логин", lambda u: u.sam),
    Column("state", "Состояние", lambda u: u.state.label),
    Column("department", "Отдел", lambda u: u.department),
    Column("title", "Должность", lambda u: u.title),
    Column("mail", "Email", lambda u: u.mail),
    Column("phone", "Телефон", lambda u: u.phone, visible=False),
    Column("manager", "Руководитель", lambda u: u.manager_name, visible=False),
    Column("ou", "OU", lambda u: u.ou),
    Column("last_logon", "Последний вход*", lambda u: u.last_logon_timestamp),
    Column("days", "Дней без входа*", lambda u: u.days_since_logon(), align_right=True),
    Column("pwd_last_set", "Пароль установлен", lambda u: "сменить при входе" if u.must_change_password else u.pwd_last_set),
    Column("pwd_expires", "Пароль истекает", lambda u: "никогда" if u.pwd_never_expires else u.pwd_expires),
    Column("pne", "PNE", lambda u: u.pwd_never_expires, visible=False),
    Column("cannot_change", "Запрет смены пароля", lambda u: u.cannot_change_password, visible=False),
    Column("account_expires", "Срок УЗ", lambda u: u.account_expires or "бессрочно", visible=False),
    Column("created", "Создана", lambda u: u.when_created),
    Column("changed", "Изменена", lambda u: u.when_changed, visible=False),
    Column("upn", "UPN", lambda u: u.upn, visible=False),
    Column("employee_id", "Таб. №", lambda u: u.employee_id, visible=False),
    Column("description", "Описание", lambda u: u.description, visible=False),
    Column("dn", "DN", lambda u: u.dn, visible=False),
]


class UsersPage(BasePage):
    title = "Пользователи"
    subtitle = "просмотр, поиск и администрирование учётных записей"

    def __init__(self, win):
        super().__init__(win)
        filt = QWidget()
        g = QGridLayout(filt)
        g.setContentsMargins(0, 0, 0, 0)
        self.view = QComboBox()
        for v in UserView:
            self.view.addItem(v.label, v)
        self.text = QLineEdit()
        self.text.setPlaceholderText("ФИО, логин, email, должность, отдел, табельный номер или DN")
        self.text.returnPressed.connect(self.refresh)
        self.ou = QLineEdit()
        self.ou.setPlaceholderText("OU (весь домен, если пусто)")
        ou_btn = QPushButton("…")
        ou_btn.setFixedWidth(34)
        ou_btn.setProperty("small", True)
        ou_btn.clicked.connect(self._pick_ou)
        self.department = QLineEdit()
        self.department.setPlaceholderText("Отдел содержит…")
        self.title_f = QLineEdit()
        self.title_f.setPlaceholderText("Должность содержит…")
        self.days = QSpinBox()
        self.days.setRange(1, 3650)
        self.days.setSuffix(" дн.")
        self.days.setToolTip("Период неактивности / окно истечения / «создано за»")
        self.search_btn = QPushButton("Найти")
        self.search_btn.setProperty("primary", True)
        self.search_btn.setMinimumWidth(110)
        self.search_btn.clicked.connect(self.refresh)
        self.view.setMinimumWidth(260)
        self.days.setMinimumWidth(110)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Представление:"))
        r1.addWidget(self.view)
        r1.addWidget(self.text, 1)
        r1.addWidget(QLabel("Период:"))
        r1.addWidget(self.days)
        r1.addWidget(self.search_btn)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("OU:"))
        r2.addWidget(self.ou, 2)
        r2.addWidget(ou_btn)
        r2.addWidget(self.department, 1)
        r2.addWidget(self.title_f, 1)
        self.saved = QComboBox()
        self.saved.setMinimumWidth(180)
        self.saved.activated.connect(self._apply_saved)
        save_btn = QToolButton()
        save_btn.setText("Сохранить фильтр")
        save_btn.clicked.connect(self._save_filter)
        del_btn = QToolButton()
        del_btn.setText("Удалить")
        del_btn.clicked.connect(self._delete_filter)
        r2.addWidget(QLabel("Сохранённые:"))
        r2.addWidget(self.saved)
        r2.addWidget(save_btn)
        r2.addWidget(del_btn)
        g.addLayout(r1, 0, 0)
        g.addLayout(r2, 1, 0)
        self.root.addWidget(filt)
        self.view.currentIndexChanged.connect(self._view_changed)

        acts = QHBoxLayout()
        self.btns = {}
        for key, text in [("details", "Карточка"), ("enable", "Включить"), ("disable", "Отключить"), ("unlock", "Разблокировать"),
                          ("reset", "Сброс пароля"), ("move", "Переместить"), ("group", "В группу…"),
                          ("create", "Создать пользователя"), ("offboard", "Уволенные…"), ("bulk", "Массово…")]:
            b = QPushButton(text)
            self.btns[key] = b
            acts.addWidget(b)
        acts.addStretch(1)
        self.root.addLayout(acts)
        a = win.actions
        self.btns["details"].clicked.connect(self._open_current)
        self.btns["enable"].clicked.connect(lambda: a.set_user_enabled(self.table.selected_rows(), True, self.refresh))
        self.btns["disable"].clicked.connect(lambda: a.set_user_enabled(self.table.selected_rows(), False, self.refresh))
        self.btns["unlock"].clicked.connect(lambda: a.unlock(self.table.selected_rows(), self.refresh))
        self.btns["reset"].clicked.connect(lambda: a.reset_password(self.table.current_row(), self.refresh))
        self.btns["move"].clicked.connect(lambda: a.move(self.table.selected_rows(), "user", self.refresh))
        self.btns["group"].clicked.connect(lambda: a.add_to_group([r.dn for r in self.table.selected_rows()], self.refresh))
        self.btns["create"].clicked.connect(self._create)
        self.btns["offboard"].clicked.connect(self._offboard)
        self.btns["bulk"].clicked.connect(self._bulk_menu)

        self.notes = banner()
        self.root.addWidget(self.notes)
        self.table = DataTable(USER_TABLE_COLUMNS, "users", win.db, export_cb=self._export, default_sort=0)
        self.table.set_state_fn(user_state)
        self.table.set_tooltip_fn(lambda u: u.dn)
        self.table.activated.connect(lambda u: u and self.win.open_user(u.dn))
        self.table.menu_builder = self._menu
        self.root.addWidget(self.table, 1)
        legend = QLabel("Цвет: серый — отключена, красный — заблокирована, жёлтый — истёк срок УЗ/пароля. "
                        "* lastLogonTimestamp реплицируется с задержкой до ~14–19 дней.")
        legend.setObjectName("Muted")
        legend.setWordWrap(True)
        self.root.addWidget(legend)
        self.last_result = None
        self._view_changed()
        self._load_saved()

    # ---------------------------------------------------------------------------------------------------------
    def _view_changed(self):
        v = UserView(self.view.currentData())
        s = self.win.settings
        if v is UserView.STALE:
            self.days.setValue(s.stale_user_days)
            self.days.setEnabled(True)
        elif v in (UserView.PWD_EXPIRING, UserView.ACCOUNT_EXPIRING):
            self.days.setValue(s.password_expiring_days)
            self.days.setEnabled(True)
        elif v is UserView.RECENT:
            self.days.setValue(s.recent_days)
            self.days.setEnabled(True)
        else:
            self.days.setEnabled(False)

    def show_view(self, key: str):
        for i in range(self.view.count()):
            if self.view.itemData(i) == key:
                self.view.setCurrentIndex(i)
                break
        self.refresh()

    def query(self) -> UserQuery:
        v = UserView(self.view.currentData())
        d = self.days.value()
        s = self.win.settings
        return UserQuery(view=v, text=self.text.text(), ou_dn=self.ou.text().strip(), department=self.department.text(),
                         title=self.title_f.text(), stale_days=d if v is UserView.STALE else s.stale_user_days,
                         expiring_days=d if v in (UserView.PWD_EXPIRING, UserView.ACCOUNT_EXPIRING) else s.password_expiring_days,
                         recent_days=d if v is UserView.RECENT else s.recent_days,
                         required_attributes=s.required_user_attributes, limit=s.search_result_limit)

    def initial_load(self):
        self.refresh()

    def refresh(self):
        if not self.need_ctx():
            return
        q = self.query()
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
        self.run(lambda c, p: UserService(ctx).search(q, c, p), done, f"Пользователи: {q.view.label}", on_error=failed)

    def on_disconnected(self):
        super().on_disconnected()
        self.table.set_rows([])
        set_banner(self.notes, [])

    def _pick_ou(self):
        from ..dialogs.pickers import OUPickerDialog
        dn = OUPickerDialog.pick(self.win)
        if dn:
            self.ou.setText(dn)

    def _open_current(self):
        r = self.table.current_row()
        if r:
            self.win.open_user(r.dn)

    def _create(self):
        if not self.need_ctx() or not self.win.actions._write_allowed():
            return
        from ..dialogs.user_dialogs import CreateUserDialog
        if CreateUserDialog(self.win).exec():
            self.refresh()

    def _offboard(self):
        dns = [r.dn for r in self.table.selected_rows()]
        self.win.navigate("bulk")
        self.win.pages["bulk"].prefill_offboarding(dns)

    def _bulk_menu(self):
        rows = self.table.selected_rows() or self.table.visible_rows()
        if not rows:
            self.win.toast("Нет объектов для массовой операции", "info")
            return
        menu = QMenu(self)
        for op in BulkOperation:
            menu.addAction(op.label, lambda op=op: self.win.start_bulk(op, [r.dn for r in rows], "user"))
        menu.exec(self.btns["bulk"].mapToGlobal(self.btns["bulk"].rect().bottomLeft()))

    def _menu(self, menu: QMenu, rows: list):
        a = self.win.actions
        r = rows[0]
        menu.addAction("Открыть карточку", lambda: self.win.open_user(r.dn))
        menu.addSeparator()
        menu.addAction("Копировать DN", lambda: QApplication.clipboard().setText("\n".join(x.dn for x in rows)))
        menu.addAction("Копировать логин", lambda: QApplication.clipboard().setText("\n".join(x.sam for x in rows)))
        menu.addAction("Копировать UPN", lambda: QApplication.clipboard().setText("\n".join(x.upn for x in rows)))
        menu.addSeparator()
        menu.addAction("Включить", lambda: a.set_user_enabled(rows, True, self.refresh))
        menu.addAction("Отключить", lambda: a.set_user_enabled(rows, False, self.refresh))
        menu.addAction("Разблокировать", lambda: a.unlock(rows, self.refresh))
        if len(rows) == 1:
            menu.addAction("Сбросить пароль…", lambda: a.reset_password(r, self.refresh))
            menu.addAction("Сменить пароль при следующем входе", lambda: a.must_change(r, True, self.refresh))
            menu.addAction("Срок действия…", lambda: a.set_expiry(r, self.refresh))
            menu.addAction("Изменить атрибуты…", lambda: a.edit_user(r, self.refresh))
            menu.addAction("Создать по образцу (копировать)…", lambda: self._copy_user(r))
        menu.addAction("Переместить в OU…", lambda: a.move(rows, "user", self.refresh))
        menu.addAction("Добавить в группу…", lambda: a.add_to_group([x.dn for x in rows], self.refresh))
        menu.addSeparator()
        menu.addAction("Обработка увольнения…", lambda: (self.win.navigate("bulk"),
                                                          self.win.pages["bulk"].prefill_offboarding([x.dn for x in rows])))
        if len(rows) == 2:
            menu.addAction("Сравнить двух пользователей", lambda: self.win.pages["tools"].compare_users(rows[0].dn, rows[1].dn))

    def _copy_user(self, r):
        if not self.win.actions._write_allowed():
            return
        from ..dialogs.user_dialogs import CreateUserDialog
        if CreateUserDialog(self.win, copy_from_dn=r.dn).exec():
            self.refresh()

    def _export(self):
        res = self.last_result
        title = f"Пользователи — {UserView(self.view.currentData()).label}"
        rep = self.table.to_report(title, criteria=res.criteria if res else {}, limitations=res.notes if res else [],
                                   info=self.ctx.gateway.info if self.ctx else None)
        self.export(rep, "users")

    # saved filters ---------------------------------------------------------------------------------------------
    def _load_saved(self):
        self.saved.clear()
        self.saved.addItem("—", None)
        for f in self.db.saved_filters("users"):
            self.saved.addItem(f["name"], f)

    def _save_filter(self):
        name, ok = QInputDialog.getText(self, "Сохранить фильтр", "Имя фильтра:")
        if not ok or not name.strip():
            return
        self.db.save_filter("users", name.strip(), {"view": self.view.currentData(), "text": self.text.text(),
                                                     "ou": self.ou.text(), "department": self.department.text(),
                                                     "title": self.title_f.text(), "days": self.days.value()})
        self._load_saved()
        self.win.toast("Фильтр сохранён", "success")

    def _delete_filter(self):
        f = self.saved.currentData()
        if f:
            self.db.delete_filter("users", f["name"])
            self._load_saved()

    def _apply_saved(self):
        f = self.saved.currentData()
        if not f:
            return
        for i in range(self.view.count()):
            if self.view.itemData(i) == f.get("view"):
                self.view.setCurrentIndex(i)
        self.text.setText(f.get("text", ""))
        self.ou.setText(f.get("ou", ""))
        self.department.setText(f.get("department", ""))
        self.title_f.setText(f.get("title", ""))
        self.days.setValue(int(f.get("days") or self.days.value()))
        self.refresh()

