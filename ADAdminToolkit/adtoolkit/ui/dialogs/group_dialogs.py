"""Group dialogs: details (direct / transitive members, nested tree, parent groups), create group."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ...services.common import TYPE_LABELS
from ...services.group_service import GroupService
from ..widgets.common import banner, set_banner, show_error
from ..widgets.table import Column, DataTable

MEMBER_COLUMNS = [Column("name", "Имя"), Column("type", "Тип", lambda r: TYPE_LABELS.get(r.object_type, r.object_type)),
                  Column("sam", "Логин"), Column("enabled", "Включён"), Column("via", "Членство"), Column("dn", "DN")]


class GroupDetailsDialog(QDialog):
    def __init__(self, win, dn: str):
        super().__init__(win)
        self.win = win
        self.dn = dn
        self.setWindowTitle("Группа")
        self.resize(940, 640)
        lay = QVBoxLayout(self)
        self.header = QLabel("Загрузка…")
        self.header.setObjectName("PageTitle")
        lay.addWidget(self.header)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.info)
        self.warn = banner(danger=True)
        lay.addWidget(self.warn)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.direct = DataTable(MEMBER_COLUMNS, "group_members_direct", win.db,
                                export_cb=lambda: self._export(self.direct, "Прямые участники"))
        self.transitive = DataTable(MEMBER_COLUMNS, "group_members_all", win.db,
                                    export_cb=lambda: self._export(self.transitive, "Все участники (с вложенностью)"))
        for t in (self.direct, self.transitive):
            t.set_state_fn(lambda r: "muted" if r.enabled is False else None)
            t.activated.connect(self._open_member)
        self.tabs.addTab(self.direct, "Прямые участники")
        tw = QWidget()
        tl = QVBoxLayout(tw)
        load_t = QPushButton("Рассчитать косвенное членство (рекурсивно)")
        load_t.clicked.connect(self._load_transitive)
        tl.addWidget(load_t, 0, Qt.AlignLeft)
        tl.addWidget(self.transitive, 1)
        self.tabs.addTab(tw, "Все участники (вложенность)")
        nw = QWidget()
        nl = QVBoxLayout(nw)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Вложенные группы", "DN"])
        self.tree.setColumnWidth(0, 360)
        load_n = QPushButton("Построить дерево вложенных групп")
        load_n.clicked.connect(self._load_tree)
        nl.addWidget(load_n, 0, Qt.AlignLeft)
        nl.addWidget(self.tree, 1)
        self.tabs.addTab(nw, "Дерево вложенности")
        self.parents = DataTable([Column("name", "Группа"), Column("scope", "Область"), Column("category", "Тип"),
                                  Column("dn", "DN")], "group_parents", win.db, show_toolbar=False)
        self.tabs.addTab(self.parents, "Входит в группы")
        btns = QHBoxLayout()
        add = QPushButton("Добавить участника…")
        add.clicked.connect(self._add)
        rem = QPushButton("Удалить выбранного участника")
        rem.clicked.connect(self._remove)
        cp = QPushButton("Копировать DN")
        cp.clicked.connect(lambda: QApplication.clipboard().setText(self.dn))
        rf = QPushButton("Обновить")
        rf.clicked.connect(self.reload)
        for b in (add, rem, cp, rf):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)
        self.reload()

    def reload(self):
        ctx = self.win.ctx

        def job(cancel, progress):
            gs = GroupService(ctx)
            return gs.get(self.dn), gs.direct_members(self.dn, cancel), gs.parent_groups(self.dn)
        self.win.run_task(job, self._fill, title="Загрузка группы")

    def _fill(self, data):
        g, members, parents = data
        self.group = g
        self.setWindowTitle(f"Группа — {g.name}")
        self.header.setText(g.name)
        self.info.setText(f"{g.scope} · {g.category} · sAMAccountName: {g.sam} · SID: {g.sid}<br>{g.description}<br>{g.dn}")
        set_banner(self.warn, [f"ПРИВИЛЕГИРОВАННАЯ ГРУППА: {g.privileged_reason}. Изменение состава требует отдельного "
                               "подтверждения с вводом имени группы."] if g.privileged else [])
        self.direct.set_rows(members)
        self.parents.set_rows([{"name": p.name, "scope": p.scope, "category": p.category, "dn": p.dn} for p in parents])

    def _load_transitive(self):
        ctx = self.win.ctx
        self.win.run_task(lambda c, p: GroupService(ctx).transitive_members(self.dn, c, p), self.transitive.set_rows,
                          title="Расчёт косвенного членства")

    def _load_tree(self):
        ctx = self.win.ctx

        def fill(node):
            self.tree.clear()

            def add(n, parent):
                text = n["name"] + ("  ⟳ цикл" if n["cycle"] else "")
                item = QTreeWidgetItem([text, n["dn"]])
                (self.tree.addTopLevelItem(item) if parent is None else parent.addChild(item))
                for ch in n["children"]:
                    add(ch, item)
                item.setExpanded(True)
            add(node, None)
        self.win.run_task(lambda c, p: GroupService(ctx).nested_tree(self.dn, c), fill, title="Дерево вложенных групп")

    def _open_member(self, row):
        if row is None:
            return
        if row.object_type == "user":
            self.win.open_user(row.dn)
        elif row.object_type == "group":
            self.win.open_group(row.dn)
        elif row.object_type == "computer":
            self.win.open_computer(row.dn)

    def _add(self):
        from .pickers import ObjectPickerDialog
        kinds = ("user", "group", "computer")
        dlg = ObjectPickerDialog(self.win, kinds, "Новые участники", multi=True)
        if dlg.exec() != QDialog.Accepted or not dlg.result_dns:
            return
        picked = [r for r in dlg.table.selected_rows()]
        types = {r["kind"] for r in picked}
        if len(types) > 1:
            self.win.toast("Для массового добавления выберите объекты одного типа", "warning")
            return
        self.win.actions.add_to_group(dlg.result_dns, self.reload, group_dn=self.dn, kind=types.pop())

    def _remove(self):
        rows = self.direct.selected_rows()
        if not rows:
            self.win.toast("Выберите участника на вкладке «Прямые участники»", "info")
            return
        if any(r.via.startswith("основная") for r in rows):
            self.win.toast("Участники по основной группе (primaryGroupID) не удаляются из member", "warning")
            return
        types = {r.object_type for r in rows}
        if len(types) > 1:
            self.win.toast("Для массового удаления выберите участников одного типа", "warning")
            return
        self.win.actions.remove_from_group(self.dn, [r.dn for r in rows], self.reload, kind=types.pop())

    def _export(self, table, title):
        from ..widgets.common import ask_export_path, report_meta, write_report
        rep = report_meta(table.to_report(f"{title}: {getattr(self, 'group', None) and self.group.name}"),
                          self.win.ctx.gateway.info if self.win.ctx else None)
        path = ask_export_path(self, "group_members")
        if path:
            self.win.run_task(lambda c, p: write_report([rep], path), lambda p: self.win.toast(f"Экспортировано: {p}", "success"),
                              title="Экспорт")


class CreateGroupDialog(QDialog):
    def __init__(self, win, ou_dn: str = ""):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Создание группы")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.ou = QLineEdit(ou_dn or f"CN=Users,{win.ctx.base_dn}")
        pick = QPushButton("…")
        pick.setFixedWidth(34)
        pick.setProperty("small", True)
        pick.clicked.connect(self._pick)
        row = QHBoxLayout()
        row.addWidget(self.ou, 1)
        row.addWidget(pick)
        w = QWidget()
        row.setContentsMargins(0, 0, 0, 0)
        w.setLayout(row)
        self.name = QLineEdit()
        self.sam = QLineEdit()
        self.name.textChanged.connect(lambda t: self.sam.setText(t))
        self.scope = QComboBox()
        self.scope.addItem("Глобальная", "global")
        self.scope.addItem("Локальная в домене", "domainlocal")
        self.scope.addItem("Универсальная", "universal")
        self.security = QCheckBox("Группа безопасности (иначе — распространения)")
        self.security.setChecked(True)
        self.desc = QLineEdit()
        form.addRow("OU:", w)
        form.addRow("Имя (CN):", self.name)
        form.addRow("sAMAccountName:", self.sam)
        form.addRow("Область:", self.scope)
        form.addRow("", self.security)
        form.addRow("Описание:", self.desc)
        lay.addLayout(form)
        bb = QDialogButtonBox()
        ok = bb.addButton("Создать", QDialogButtonBox.AcceptRole)
        ok.setProperty("primary", True)
        bb.addButton("Отмена", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._create)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _pick(self):
        from .pickers import OUPickerDialog
        dn = OUPickerDialog.pick(self.win)
        if dn:
            self.ou.setText(dn)

    def _create(self):
        ctx = self.win.ctx
        args = dict(ou_dn=self.ou.text().strip(), name=self.name.text().strip(), sam=self.sam.text().strip(),
                    scope=self.scope.currentData(), security=self.security.isChecked(), description=self.desc.text())

        def done(dn):
            self.win.toast(f"Группа создана: {dn}", "success")
            self.accept()
        self.win.run_task(lambda c, p: GroupService(ctx).create_group(**args), done, title="Создание группы",
                          on_error=lambda e: show_error(self, e))
