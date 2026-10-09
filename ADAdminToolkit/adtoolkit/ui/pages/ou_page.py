"""OU structure: tree with object counts, contents, empty OUs, move with target validation, snapshots."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QPushButton, QSplitter,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ...reports.exporters import ReportTable
from ...services.common import TYPE_LABELS
from ...services.ou_service import OUService
from ..widgets.common import TypedConfirmDialog, banner, report_meta, set_banner
from ..widgets.table import Column, DataTable
from .base import BasePage

ICONS = {"domain": "🌐", "organizationalUnit": "📁", "container": "🗂", "builtinDomain": "🗂"}


class OUPage(BasePage):
    title = "Структура OU"
    subtitle = "подразделения, количество объектов, перемещение"

    def __init__(self, win):
        super().__init__(win)
        acts = QHBoxLayout()
        for text, fn in [("Обновить", self.refresh), ("Пустые OU", self._empty), ("Создать OU…", self._create),
                         ("Удалить пустое OU…", self._delete), ("Переместить выбранные объекты…", self._move),
                         ("Экспорт структуры…", self._export_structure), ("Сохранить снимок…", self._snapshot)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            acts.addWidget(b)
        acts.addStretch(1)
        self.root.addLayout(acts)
        self.notes = banner()
        self.root.addWidget(self.notes)
        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Подразделение", "Польз.", "Комп.", "Групп", "Всего (вложенно)"])
        self.tree.setColumnWidth(0, 300)
        self.tree.itemSelectionChanged.connect(self._load_objects)
        split.addWidget(self.tree)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.ou_label = QLabel("Выберите OU")
        self.ou_label.setWordWrap(True)
        self.ou_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.subtree = QCheckBox("Включая вложенные OU")
        self.subtree.toggled.connect(self._load_objects)
        top.addWidget(self.ou_label, 1)
        top.addWidget(self.subtree)
        rl.addLayout(top)
        self.objects = DataTable([Column("name", "Имя"), Column("type", "Тип", lambda r: TYPE_LABELS.get(r["type"], r["type"])),
                                  Column("sam", "Логин"), Column("enabled", "Включён"), Column("description", "Описание"),
                                  Column("created", "Создан"), Column("dn", "DN", visible=False)], "ou_objects", win.db,
                                 export_cb=self._export_objects)
        self.objects.set_state_fn(lambda r: "muted" if r["enabled"] is False else None)
        self.objects.activated.connect(self._open)
        rl.addWidget(self.objects, 1)
        split.addWidget(right)
        split.setSizes([480, 700])
        self.root.addWidget(split, 1)
        self.root_node = None

    def initial_load(self):
        self.refresh()

    def on_disconnected(self):
        super().on_disconnected()
        self.tree.clear()
        self.objects.set_rows([])

    def refresh(self):
        if not self.need_ctx():
            return
        ctx = self.ctx
        self.run(lambda c, p: OUService(ctx).tree(c, p), self._fill, "Структура OU")

    def _fill(self, root):
        self.root_node = root
        self.tree.clear()

        def add(node, parent):
            item = QTreeWidgetItem([f"{ICONS.get(node.kind, '📁')} {node.name}", str(node.direct_users),
                                    str(node.direct_computers), str(node.direct_groups), str(node.total_objects)])
            item.setData(0, Qt.UserRole, node.dn)
            item.setToolTip(0, node.dn + (f"\n{node.description}" if node.description else ""))
            for col in (1, 2, 3, 4):
                item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
            if node.kind == "organizationalUnit" and node.is_empty:
                item.setForeground(0, Qt.gray)
            (self.tree.addTopLevelItem(item) if parent is None else parent.addChild(item))
            for c in node.children:
                add(c, item)
            return item
        top = add(root, None)
        top.setExpanded(True)
        set_banner(self.notes, ["Количество объектов — пользователи, компьютеры, группы и контакты; системные контейнеры "
                                "(System, Program Data и т.п.) скрыты. Серым показаны пустые OU."])

    def _selected_ou(self) -> str:
        items = self.tree.selectedItems()
        return items[0].data(0, Qt.UserRole) if items else ""

    def _load_objects(self):
        dn = self._selected_ou()
        if not dn or self.ctx is None:
            return
        self.ou_label.setText(dn)
        ctx = self.ctx
        sub = self.subtree.isChecked()
        self.run(lambda c, p: OUService(ctx).objects_in(dn, sub, c), self.objects.set_rows, "Объекты OU")

    def _open(self, r):
        if not r:
            return
        {"user": self.win.open_user, "group": self.win.open_group, "computer": self.win.open_computer}.get(
            r["type"], lambda dn: None)(r["dn"])

    def _empty(self):
        if not self.need_ctx():
            return
        ctx = self.ctx

        def done(nodes):
            self.objects.set_rows([{"name": n.name, "type": "organizationalUnit", "sam": "", "enabled": None,
                                    "description": n.description, "created": None, "dn": n.dn} for n in nodes])
            self.ou_label.setText(f"Пустые OU: {len(nodes)} (без дочерних объектов любого класса)")
        self.run(lambda c, p: OUService(ctx).empty_ous(c, p), done, "Поиск пустых OU")

    def _create(self):
        parent = self._selected_ou()
        if not parent:
            self.win.toast("Выберите родительский контейнер в дереве", "info")
            return
        if not self.win.actions._write_allowed():
            return
        name, ok = QInputDialog.getText(self, "Создание OU", f"Имя нового OU в\n{parent}:")
        if not ok or not name.strip():
            return
        ctx = self.ctx
        self.run(lambda c, p: OUService(ctx).create_ou(parent, name.strip()),
                 lambda dn: (self.win.toast(f"Создано OU: {dn}", "success"), self.refresh()), "Создание OU")

    def _delete(self):
        dn = self._selected_ou()
        if not dn:
            self.win.toast("Выберите OU в дереве", "info")
            return
        if not self.win.actions._write_allowed():
            return
        from ...ldap.dn import rdn_value
        name = rdn_value(dn)
        if not TypedConfirmDialog.ask(self.win, "Удаление OU",
                                      f"Удалить OU «{name}»? Удаляются только пустые OU, не защищённые от случайного удаления.",
                                      name, details=dn):
            return
        ctx = self.ctx
        self.run(lambda c, p: OUService(ctx).delete_empty_ou(dn, confirmed_name=name),
                 lambda _: (self.win.toast(f"OU удалено: {dn}", "success"), self.refresh()), "Удаление OU")

    def _move(self):
        rows = [r for r in self.objects.selected_rows() if r["type"] in ("user", "computer")]
        if not rows:
            self.win.toast("Выберите пользователей или компьютеры в списке объектов OU", "info")
            return
        kinds = {r["type"] for r in rows}
        if len(kinds) > 1:
            self.win.toast("Перемещайте пользователей и компьютеры отдельно", "warning")
            return

        class _R:
            def __init__(self, d):
                self.dn, self.name = d["dn"], d["name"]
        self.win.actions.move([_R(r) for r in rows], kinds.pop(), self._load_objects)

    def _structure_table(self) -> ReportTable | None:
        if self.root_node is None:
            return None
        rows = []

        def walk(n, depth):
            rows.append({"path": "    " * depth + n.name, "kind": n.kind, "users": n.direct_users,
                         "computers": n.direct_computers, "groups": n.direct_groups, "other": n.direct_other,
                         "total": n.total_objects, "empty": n.kind == "organizationalUnit" and n.is_empty,
                         "description": n.description, "dn": n.dn})
            for c in n.children:
                walk(c, depth + 1)
        walk(self.root_node, 0)
        return report_meta(ReportTable("Структура OU", [("path", "Подразделение"), ("kind", "Тип"), ("users", "Польз."),
                                                        ("computers", "Комп."), ("groups", "Групп"), ("other", "Прочие"),
                                                        ("total", "Всего (вложенно)"), ("empty", "Пустое"),
                                                        ("description", "Описание"), ("dn", "DN")], rows),
                           self.ctx.gateway.info if self.ctx else None)

    def _export_structure(self):
        t = self._structure_table()
        if t is None:
            self.win.toast("Сначала загрузите структуру", "info")
            return
        self.export(t, "ou_structure")

    def _snapshot(self):
        if not self.need_ctx():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Снимок структуры OU", "ou_snapshot.json",
                                              "JSON-снимок (*.json);;CSV-снимок (*.csv)")
        if not path:
            return
        ctx = self.ctx

        def job(cancel, progress):
            svc = OUService(ctx)
            snap = svc.snapshot(cancel, progress)
            svc.save_snapshot(snap, path)
            return path
        self.run(job, lambda p: self.win.toast(f"Снимок сохранён: {p}. Сравнение — Инструменты → Сравнение OU.", "success", 7000),
                 "Снимок структуры OU")

    def _export_objects(self):
        rep = self.objects.to_report(f"Объекты OU {self.ou_label.text()}", info=self.ctx.gateway.info if self.ctx else None)
        self.export(rep, "ou_objects")
