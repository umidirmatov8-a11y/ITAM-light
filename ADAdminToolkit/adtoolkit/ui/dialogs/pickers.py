"""Pickers: OU tree and directory object search (users / groups / computers)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout)

from ...ldap.dn import rdn_value
from ...ldap.filters import And, Equals, Or, Substring
from ...services import ad_queries as Q
from ...services.common import TYPE_LABELS, object_type_of
from ...services.ou_service import OUService
from ..widgets.table import Column, DataTable

KIND_ICONS = {"domain": "🌐", "organizationalUnit": "📁", "container": "🗂", "builtinDomain": "🗂"}


class OUPickerDialog(QDialog):
    def __init__(self, win, title: str = "Выбор OU / контейнера", *, object_class: str = ""):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(title)
        self.resize(560, 560)
        self.selected_dn = ""
        lay = QVBoxLayout(self)
        hint = QLabel("Выберите целевое подразделение. Права на создание объектов будут проверены перед операцией.")
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        lay.addWidget(hint)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Фильтр по имени…")
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Подразделение", "DN"])
        self.tree.setColumnWidth(0, 300)
        self.tree.itemSelectionChanged.connect(self._sel)
        self.tree.itemDoubleClicked.connect(lambda *_: self.accept() if self.selected_dn else None)
        lay.addWidget(self.tree, 1)
        self.dn_label = QLabel("")
        self.dn_label.setWordWrap(True)
        self.dn_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.dn_label)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.ok = bb.button(QDialogButtonBox.Ok)
        self.ok.setEnabled(False)
        lay.addWidget(bb)
        win.run_task(lambda c, p: OUService(win.ctx).tree(c, p, with_counts=False), self._fill, title="Загрузка структуры OU")

    def _fill(self, root):
        self.tree.clear()

        def add(node, parent):
            item = QTreeWidgetItem([f"{KIND_ICONS.get(node.kind, '📁')} {node.name}", node.dn])
            item.setData(0, Qt.UserRole, node.dn)
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for c in node.children:
                add(c, item)
            return item
        top = add(root, None)
        top.setExpanded(True)
        for i in range(top.childCount()):
            top.child(i).setExpanded(True)

    def _apply_filter(self, text):
        t = text.casefold().strip()

        def walk(item) -> bool:
            match = not t or t in item.text(0).casefold()
            child_match = False
            for i in range(item.childCount()):
                child_match = walk(item.child(i)) or child_match
            item.setHidden(not (match or child_match))
            if t and child_match:
                item.setExpanded(True)
            return match or child_match
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def _sel(self):
        items = self.tree.selectedItems()
        self.selected_dn = items[0].data(0, Qt.UserRole) if items else ""
        self.dn_label.setText(self.selected_dn)
        self.ok.setEnabled(bool(self.selected_dn))

    @staticmethod
    def pick(win, title: str = "Выбор OU / контейнера") -> str | None:
        if win.ctx is None:
            return None
        dlg = OUPickerDialog(win, title)
        if dlg.exec() == QDialog.Accepted and dlg.selected_dn:
            return dlg.selected_dn
        return None


class ObjectPickerDialog(QDialog):
    """Search and choose directory objects by name (debounced LDAP search in a worker thread)."""

    def __init__(self, win, kinds: tuple[str, ...] = ("user",), title: str = "Выбор объекта", multi: bool = False):
        super().__init__(win)
        self.win = win
        self.kinds = kinds
        self.multi = multi
        self.setWindowTitle(title)
        self.resize(760, 520)
        self.result_dns: list[str] = []
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.kind = QComboBox()
        labels = {"user": "Пользователи", "group": "Группы", "computer": "Компьютеры"}
        for k in kinds:
            self.kind.addItem(labels[k], k)
        if len(kinds) > 1:
            self.kind.addItem("Все типы", "*")
        self.text = QLineEdit()
        self.text.setPlaceholderText("Имя, логин, email или DN (от 2 символов)…")
        row.addWidget(self.kind)
        row.addWidget(self.text, 1)
        lay.addLayout(row)
        self.table = DataTable([Column("name", "Имя"), Column("type", "Тип"), Column("sam", "Логин"), Column("dn", "DN")],
                               show_toolbar=False)
        if not multi:
            self.table.view.setSelectionMode(self.table.view.SelectionMode.SingleSelection)
        self.table.activated.connect(lambda r: self.accept() if r else None)
        lay.addWidget(self.table, 1)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        lay.addWidget(self.status)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(win.settings.search_debounce_ms)
        self.timer.timeout.connect(self._search)
        self.text.textChanged.connect(lambda _: self.timer.start())
        self.kind.currentIndexChanged.connect(lambda _: self.timer.start())
        self._seq = 0

    def _search(self):
        text = self.text.text().strip()
        if len(text) < 2:
            return
        kind = self.kind.currentData()
        self._seq += 1
        seq = self._seq
        ctx = self.win.ctx

        def job(cancel, progress):
            gw = ctx.gateway
            if "=" in text and "," in text:
                e = gw.get(text, ["cn", "displayName", "sAMAccountName", "objectClass"])
                return [e] if e is not None else []
            types = {"user": Q.IS_USER, "group": Q.IS_GROUP, "computer": Q.IS_COMPUTER}
            tnode = Or(*[types[k] for k in self.kinds]) if kind == "*" else types[kind]
            flt = And(tnode, Or(Substring("cn", any=(text,)), Substring("sAMAccountName", any=(text,)),
                                Substring("displayName", any=(text,)), Equals("mail", text), Equals("userPrincipalName", text)))
            return gw.search_list(ctx.base_dn, flt, ["cn", "displayName", "sAMAccountName", "objectClass"], size_limit=200,
                                  cancel=cancel)

        def done(entries):
            if seq != self._seq:
                return
            rows = [{"name": e.str("displayName") or e.str("cn") or rdn_value(e.dn),
                     "type": TYPE_LABELS.get(object_type_of(e), ""), "sam": e.str("sAMAccountName"), "dn": e.dn,
                     "kind": object_type_of(e)} for e in entries if object_type_of(e) in self.kinds]
            self.table.set_rows(rows)
            self.status.setText(f"Найдено: {len(rows)}" + (" (показаны первые 200)" if len(entries) >= 200 else ""))
        self.win.run_task(job, done, title="Поиск объектов", on_error=lambda e: self.status.setText(str(e)))

    def accept(self):
        rows = self.table.selected_rows()
        if not rows:
            return
        self.result_dns = [r["dn"] for r in rows]
        super().accept()

    @staticmethod
    def pick(win, kinds=("user",), title="Выбор объекта", multi=False) -> list[str]:
        if win.ctx is None:
            return []
        dlg = ObjectPickerDialog(win, kinds, title, multi)
        if dlg.exec() == QDialog.Accepted:
            return dlg.result_dns
        return []
