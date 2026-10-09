"""Groups module: search by name/type/scope, members panel, privileged warnings, analysis and changes."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from ...services.group_service import GroupQuery, GroupService
from ..dialogs.group_dialogs import MEMBER_COLUMNS
from ..widgets.common import banner, report_meta, set_banner
from ..widgets.table import Column, DataTable
from .base import BasePage

GROUP_TABLE_COLUMNS = [
    Column("name", "Имя", lambda g: ("⚠ " if g.privileged else "") + g.name),
    Column("sam", "sAMAccountName", lambda g: g.sam, visible=False),
    Column("scope", "Область", lambda g: g.scope),
    Column("category", "Тип", lambda g: g.category),
    Column("members", "Прямых участников", lambda g: len(g.members), align_right=True),
    Column("privileged", "Привилегии", lambda g: g.privileged_reason),
    Column("description", "Описание", lambda g: g.description),
    Column("ou", "OU", lambda g: g.ou),
    Column("created", "Создана", lambda g: g.when_created, visible=False),
    Column("dn", "DN", lambda g: g.dn, visible=False),
]


class GroupsPage(BasePage):
    title = "Группы"
    subtitle = "состав, вложенность, привилегированные группы"

    def __init__(self, win):
        super().__init__(win)
        row = QHBoxLayout()
        self.text = QLineEdit()
        self.text.setPlaceholderText("Название группы или описание")
        self.text.returnPressed.connect(self.refresh)
        self.scope = QComboBox()
        for label, val in [("Любая область", ""), ("Глобальная", "global"), ("Локальная в домене", "domainlocal"),
                           ("Универсальная", "universal"), ("Встроенная (Builtin)", "builtin")]:
            self.scope.addItem(label, val)
        self.category = QComboBox()
        for label, val in [("Любой тип", ""), ("Безопасности", "security"), ("Распространения", "distribution")]:
            self.category.addItem(label, val)
        self.only_priv = QCheckBox("Только привилегированные")
        self.search_btn = QPushButton("Найти")
        self.search_btn.setProperty("primary", True)
        self.search_btn.clicked.connect(self.refresh)
        for w in (self.text, self.scope, self.category, self.only_priv, self.search_btn):
            row.addWidget(w, 2 if w is self.text else 0)
        self.root.addLayout(row)
        acts = QHBoxLayout()
        for text, fn in [("Карточка группы", self._open), ("Создать группу…", self._create),
                         ("Пустые группы", self._empty), ("Состав привилегированных групп", self._privileged),
                         ("Сравнить две группы", self._compare), ("Без стандартных групп", self._missing_standard)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            acts.addWidget(b)
        acts.addStretch(1)
        self.root.addLayout(acts)
        self.notes = banner()
        self.root.addWidget(self.notes)
        split = QSplitter(Qt.Vertical)
        self.table = DataTable(GROUP_TABLE_COLUMNS, "groups", win.db, export_cb=self._export)
        self.table.set_state_fn(lambda g: "danger" if g.privileged and "Привилегированная" in g.privileged_reason
                                else ("warning" if g.privileged else None))
        self.table.activated.connect(lambda g: g and self.win.open_group(g.dn))
        self.table.selection_changed.connect(self._selection)
        self.table.menu_builder = self._menu
        split.addWidget(self.table)
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        mh = QHBoxLayout()
        self.members_title = QLabel("Участники выбранной группы")
        self.members_title.setStyleSheet("font-weight: 600;")
        self.transitive = QCheckBox("С учётом вложенности")
        self.transitive.toggled.connect(self._selection)
        add = QPushButton("Добавить участника…")
        add.clicked.connect(self._add_member)
        rem = QPushButton("Удалить участника")
        rem.clicked.connect(self._remove_member)
        mh.addWidget(self.members_title)
        mh.addStretch(1)
        mh.addWidget(self.transitive)
        mh.addWidget(add)
        mh.addWidget(rem)
        bl.addLayout(mh)
        self.members = DataTable(MEMBER_COLUMNS, "groups_members", win.db, export_cb=self._export_members)
        self.members.set_state_fn(lambda r: "muted" if r.enabled is False else None)
        self.members.activated.connect(self._open_member)
        bl.addWidget(self.members, 1)
        split.addWidget(bottom)
        split.setSizes([420, 300])
        self.root.addWidget(split, 1)
        self.last_result = None
        self._members_seq = 0

    def initial_load(self):
        self.refresh()

    def show_view(self, key):
        self.refresh()

    def refresh(self):
        if not self.need_ctx():
            return
        q = GroupQuery(text=self.text.text(), scope=self.scope.currentData(), category=self.category.currentData(),
                       only_privileged=self.only_priv.isChecked(), limit=self.win.settings.search_result_limit)
        ctx = self.ctx

        def done(res):
            self.last_result = res
            self.table.set_rows(res.items)
            set_banner(self.notes, res.notes)
        self.run(lambda c, p: GroupService(ctx).search(q, c, p), done, "Поиск групп")

    def on_disconnected(self):
        super().on_disconnected()
        self.table.set_rows([])
        self.members.set_rows([])

    def _selection(self):
        g = self.table.current_row()
        if g is None or self.ctx is None:
            return
        self._members_seq += 1
        seq = self._members_seq
        ctx = self.ctx
        transitive = self.transitive.isChecked()
        self.members_title.setText(f"Участники: {g.name}" + ("  ⚠ привилегированная" if g.privileged else ""))

        def job(cancel, progress):
            gs = GroupService(ctx)
            return gs.transitive_members(g.dn, cancel, progress) if transitive else gs.direct_members(g.dn, cancel)

        def done(rows):
            if seq == self._members_seq:
                self.members.set_rows(rows)
        self.run(job, done, f"Участники группы {g.name}")

    def _open(self):
        g = self.table.current_row()
        if g:
            self.win.open_group(g.dn)

    def _open_member(self, r):
        if r is None:
            return
        {"user": self.win.open_user, "group": self.win.open_group, "computer": self.win.open_computer}.get(
            r.object_type, lambda dn: None)(r.dn)

    def _create(self):
        if not self.need_ctx() or not self.win.actions._write_allowed():
            return
        from ..dialogs.group_dialogs import CreateGroupDialog
        if CreateGroupDialog(self.win).exec():
            self.refresh()

    def _add_member(self):
        g = self.table.current_row()
        if g is None:
            self.win.toast("Выберите группу", "info")
            return
        from ..dialogs.pickers import ObjectPickerDialog
        dlg = ObjectPickerDialog(self.win, ("user", "group", "computer"), "Новые участники", multi=True)
        if not dlg.exec() or not dlg.result_dns:
            return
        kinds = {r["kind"] for r in dlg.table.selected_rows()}
        if len(kinds) > 1:
            self.win.toast("Выберите объекты одного типа", "warning")
            return
        self.win.actions.add_to_group(dlg.result_dns, self._selection, group_dn=g.dn, kind=kinds.pop())

    def _remove_member(self):
        g = self.table.current_row()
        rows = self.members.selected_rows()
        if g is None or not rows:
            self.win.toast("Выберите группу и участника", "info")
            return
        if self.transitive.isChecked() and any(r.depth > 0 for r in rows):
            self.win.toast("Косвенных участников нельзя удалить из этой группы — удалите их из вложенной группы", "warning")
            return
        kinds = {r.object_type for r in rows}
        if len(kinds) > 1:
            self.win.toast("Выберите участников одного типа", "warning")
            return
        self.win.actions.remove_from_group(g.dn, [r.dn for r in rows], self._selection, kind=kinds.pop())

    def _empty(self):
        if not self.need_ctx():
            return
        ctx = self.ctx

        def done(items):
            self.table.set_rows(items)
            set_banner(self.notes, [f"Пустые группы: {len(items)}. Учтено членство через основную группу (primaryGroupID). "
                                    "Пустая группа может использоваться в ACL/GPO — проверьте перед удалением."])
        self.run(lambda c, p: GroupService(ctx).empty_groups(c, p), done, "Поиск пустых групп")

    def _privileged(self):
        if not self.need_ctx():
            return
        from ...services.report_service import ReportService

        def done(tables):
            self.win.pages["reports"].show_tables(tables)
            self.win.navigate("reports")
        ctx = self.ctx
        self.run(lambda c, p: ReportService(ctx).build("privileged", {}, c, p), done, "Состав привилегированных групп")

    def _compare(self):
        rows = self.table.selected_rows()
        if len(rows) != 2:
            self.win.toast("Выделите ровно две группы (Ctrl+клик)", "info")
            return
        self.win.pages["tools"].compare_groups(rows[0].dn, rows[1].dn)

    def _missing_standard(self):
        if not self.need_ctx():
            return
        names = self.win.settings.standard_groups
        if not names:
            self.win.toast("Сначала задайте стандартные группы организации в Настройках", "warning", 6000)
            self.win.navigate("settings")
            return
        ctx = self.ctx

        def done(rows):
            from ...reports.exporters import ReportTable
            t = report_meta(ReportTable("Пользователи без членства в стандартных группах",
                                        [("name", "Имя"), ("sam", "Логин"), ("department", "Отдел"),
                                         ("missing", "Нет в группах"), ("dn", "DN")], rows,
                                        {"Стандартные группы": ", ".join(names)},
                                        ["Учитывается вложенное членство и основная группа."]), ctx.gateway.info)
            self.win.pages["reports"].show_tables([t])
            self.win.navigate("reports")
        self.run(lambda c, p: GroupService(ctx).users_missing_standard_groups(names, c), done,
                 "Проверка стандартных групп")

    def _menu(self, menu: QMenu, rows):
        g = rows[0]
        menu.addAction("Открыть карточку", lambda: self.win.open_group(g.dn))
        menu.addAction("Копировать имя", lambda: QApplication.clipboard().setText("\n".join(r.name for r in rows)))
        menu.addAction("Копировать DN", lambda: QApplication.clipboard().setText("\n".join(r.dn for r in rows)))
        if len(rows) == 2:
            menu.addAction("Сравнить состав", self._compare)

    def _export(self):
        res = self.last_result
        rep = self.table.to_report("Группы", criteria=res.criteria if res else {}, limitations=res.notes if res else [],
                                   info=self.ctx.gateway.info if self.ctx else None)
        self.export(rep, "groups")

    def _export_members(self):
        g = self.table.current_row()
        rep = self.members.to_report(f"Состав группы {g.name if g else ''}" + (" (с вложенностью)" if self.transitive.isChecked() else ""),
                                     criteria={"Группа": g.dn if g else ""}, info=self.ctx.gateway.info if self.ctx else None)
        self.export(rep, "group_members")

