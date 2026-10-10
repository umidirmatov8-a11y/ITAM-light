"""LDAP Explorer (read-only): filter builder, raw filter editor with validation, results, attributes, history, favourites."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTabWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...core.errors import ValidationError
from ...ldap.adtypes import display_value
from ...ldap.filters import FilterSyntaxError, parse_filter
from ...services.attribute_reference import search_reference
from ...services.explorer_service import OBJECT_TYPES, OPERATORS, Condition, ExplorerService, build_filter, validate_attributes
from ..widgets.common import banner, show_error
from ..widgets.table import Column, DataTable
from .base import BasePage


class ExplorerPage(BasePage):
    title = "LDAP Explorer"
    subtitle = "только чтение · конструктор фильтров · сырые результаты"

    def __init__(self, win):
        super().__init__(win)
        ro = banner("Режим только для чтения: пользовательские запросы не могут изменять каталог. Значения в конструкторе "
                    "экранируются автоматически; введённый вручную фильтр проверяется синтаксически перед отправкой.")
        ro.setVisible(True)
        self.root.addWidget(ro)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        b = QGroupBox("Конструктор фильтра")
        bl = QVBoxLayout(b)
        top = QFormLayout()
        self.otype = QComboBox()
        for k in OBJECT_TYPES:
            self.otype.addItem(k)
        self.combine = QComboBox()
        self.combine.addItem("Все условия (AND)", "AND")
        self.combine.addItem("Любое условие (OR)", "OR")
        top.addRow("Тип объекта:", self.otype)
        top.addRow("Условия:", self.combine)
        bl.addLayout(top)
        self.conds = QTableWidget(0, 3)
        self.conds.setHorizontalHeaderLabels(["Атрибут", "Оператор", "Значение"])
        self.conds.horizontalHeader().setStretchLastSection(True)
        self.conds.setMinimumHeight(130)
        bl.addWidget(self.conds)
        crow = QHBoxLayout()
        add = QPushButton("+ условие")
        add.clicked.connect(lambda: self._add_cond())
        rem = QPushButton("− условие")
        rem.clicked.connect(lambda: self.conds.removeRow(self.conds.currentRow()) if self.conds.currentRow() >= 0 else None)
        gen = QPushButton("Сформировать фильтр ↓")
        gen.clicked.connect(self._generate)
        crow.addWidget(add)
        crow.addWidget(rem)
        crow.addStretch(1)
        crow.addWidget(gen)
        bl.addLayout(crow)
        ll.addWidget(b)
        q = QGroupBox("Запрос")
        ql = QFormLayout(q)
        self.examples = QComboBox()
        self.examples.addItem("— примеры —", "")
        for name, text in ExplorerService.examples().items():
            self.examples.addItem(name, text)
        self.examples.activated.connect(lambda _: self.examples.currentData() and self.filter.setPlainText(self.examples.currentData()))
        self.base = QLineEdit()
        self.base.setPlaceholderText("Base DN (пусто — корень домена)")
        bbtn = QPushButton("…")
        bbtn.setFixedWidth(34)
        bbtn.setProperty("small", True)
        bbtn.clicked.connect(self._pick_base)
        brow = QHBoxLayout()
        brow.addWidget(self.base, 1)
        brow.addWidget(bbtn)
        bw = QWidget()
        brow.setContentsMargins(0, 0, 0, 0)
        bw.setLayout(brow)
        self.scope = QComboBox()
        self.scope.addItem("Поддерево (subtree)", "subtree")
        self.scope.addItem("Один уровень (onelevel)", "onelevel")
        self.scope.addItem("Только объект (base)", "base")
        self.filter = QPlainTextEdit("(&(objectCategory=person)(objectClass=user))")
        self.filter.setMaximumHeight(80)
        self.filter_status = QLabel("")
        self.attrs = QLineEdit("cn, sAMAccountName, distinguishedName, objectClass, whenCreated")
        self.limit = QSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(1000)
        ql.addRow("Примеры:", self.examples)
        ql.addRow("Base DN:", bw)
        ql.addRow("Область:", self.scope)
        ql.addRow("Фильтр:", self.filter)
        ql.addRow("", self.filter_status)
        ql.addRow("Атрибуты:", self.attrs)
        ql.addRow("Лимит:", self.limit)
        run_row = QHBoxLayout()
        self.run_btn = QPushButton("Выполнить (чтение)")
        self.run_btn.setProperty("primary", True)
        self.run_btn.clicked.connect(self._run)
        fav = QPushButton("В избранное…")
        fav.clicked.connect(self._save_fav)
        run_row.addWidget(self.run_btn)
        run_row.addWidget(fav)
        ql.addRow("", run_row)
        ll.addWidget(q)
        lists = QTabWidget()
        self.favs = QListWidget()
        self.favs.itemDoubleClicked.connect(self._load_fav)
        fav_w = QWidget()
        fl = QVBoxLayout(fav_w)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.favs)
        dfav = QPushButton("Удалить из избранного")
        dfav.clicked.connect(self._del_fav)
        fl.addWidget(dfav)
        self.history = QListWidget()
        self.history.itemDoubleClicked.connect(self._load_hist)
        hist_w = QWidget()
        hl = QVBoxLayout(hist_w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.history)
        chist = QPushButton("Очистить историю")
        chist.clicked.connect(lambda: (self.db.clear_query_history(), self._load_lists()))
        hl.addWidget(chist)
        lists.addTab(fav_w, "Избранное")
        lists.addTab(hist_w, "История")
        ref_w = QWidget()
        rl = QVBoxLayout(ref_w)
        rl.setContentsMargins(0, 0, 0, 0)
        self.ref_search = QLineEdit()
        self.ref_search.setPlaceholderText("Поиск атрибута…")
        self.ref = DataTable([Column("name", "Атрибут"), Column("syntax", "Синтаксис"), Column("description", "Описание"),
                              Column("replicated", "Репликация"), Column("notes", "Примечания")], "attr_ref_small", win.db,
                             show_toolbar=False)
        self.ref_search.textChanged.connect(lambda t: self.ref.set_rows(search_reference(t)))
        self.ref.activated.connect(lambda a: a and self._append_attr(a.name))
        rl.addWidget(self.ref_search)
        rl.addWidget(self.ref)
        lists.addTab(ref_w, "Справочник")
        ll.addWidget(lists, 1)
        split.addWidget(left)
        right = QSplitter(Qt.Vertical)
        self.results = DataTable([Column("dn", "DN")], "explorer_results", None, export_cb=self._export)
        self.results.selection_changed.connect(self._show_entry)
        right.addWidget(self.results)
        self.entry_attrs = DataTable([Column("name", "Атрибут"), Column("value", "Значение")], "explorer_entry", win.db)
        right.addWidget(self.entry_attrs)
        right.setSizes([500, 300])
        split.addWidget(right)
        split.setSizes([520, 900])
        self.root.addWidget(split, 1)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.root.addWidget(self.status)
        self._validate_timer = QTimer(self)
        self._validate_timer.setSingleShot(True)
        self._validate_timer.setInterval(300)
        self._validate_timer.timeout.connect(self._validate)
        self.filter.textChanged.connect(self._validate_timer.start)
        self.last = None
        self._add_cond("sAMAccountName", "присутствует", "")
        self.ref.set_rows(search_reference(""))
        self._load_lists()
        self._validate()

    # ---------------------------------------------------------------------------------------------------------
    def _add_cond(self, attr: str = "", op: str = "равно", value: str = ""):
        r = self.conds.rowCount()
        self.conds.insertRow(r)
        self.conds.setItem(r, 0, QTableWidgetItem(attr))
        combo = QComboBox()
        for label in OPERATORS:
            combo.addItem(label, OPERATORS[label])
        combo.setCurrentText(op)
        self.conds.setCellWidget(r, 1, combo)
        self.conds.setItem(r, 2, QTableWidgetItem(value))

    def _generate(self):
        conds = []
        for r in range(self.conds.rowCount()):
            attr = (self.conds.item(r, 0).text() if self.conds.item(r, 0) else "").strip()
            if not attr:
                continue
            op = self.conds.cellWidget(r, 1).currentData()
            value = self.conds.item(r, 2).text() if self.conds.item(r, 2) else ""
            conds.append(Condition(attr, op, value))
        try:
            node = build_filter(self.otype.currentText(), conds, self.combine.currentData())
        except (ValidationError, ValueError) as exc:
            show_error(self, exc if isinstance(exc, ValidationError) else ValidationError(str(exc)))
            return
        self.filter.setPlainText(node.to_ldap())

    def _validate(self):
        text = self.filter.toPlainText().strip()
        try:
            node = parse_filter(text)
            self.filter_status.setText("✔ Синтаксис корректен: " + node.to_ldap()[:200])
            self.filter_status.setStyleSheet("color: #3ecf8e;")
            return True
        except FilterSyntaxError as exc:
            self.filter_status.setText(f"✖ {exc}")
            self.filter_status.setStyleSheet("color: #ff6b6b;")
            return False

    def _pick_base(self):
        from ..dialogs.pickers import OUPickerDialog
        dn = OUPickerDialog.pick(self.win)
        if dn:
            self.base.setText(dn)

    def _append_attr(self, name: str):
        cur = [a.strip() for a in self.attrs.text().split(",") if a.strip()]
        if name not in cur:
            cur.append(name)
        self.attrs.setText(", ".join(cur))

    def _run(self):
        if not self.need_ctx() or not self._validate():
            return
        try:
            attrs = validate_attributes(self.attrs.text())
        except ValidationError as exc:
            show_error(self, exc)
            return
        ctx, db = self.ctx, self.db
        base, scope, flt, limit = self.base.text().strip(), self.scope.currentData(), self.filter.toPlainText(), self.limit.value()
        self.run_btn.setEnabled(False)

        def done(res):
            self.run_btn.setEnabled(True)
            self.last = res
            names = [a for a in res.attributes if a not in ("*", "1.1")]
            if "*" in res.attributes:
                seen = []
                for e in res.entries[:200]:
                    for k in e.attributes.keys():
                        if k not in seen:
                            seen.append(k)
                names = seen
            cols = [Column("dn", "DN", lambda e: e.dn)] + [
                Column(n, n, lambda e, n=n: "; ".join(display_value(n, v) for v in e.values(n))) for n in names[:60]]
            self.results.set_columns(cols)
            self.results.set_rows(res.entries)
            self.status.setText(f"Найдено: {len(res.entries)} · страниц LDAP: {res.stats.pages} · "
                                f"{'РЕЗУЛЬТАТ ОГРАНИЧЕН ЛИМИТОМ' if res.stats.truncated else 'полный результат'} · "
                                f"фильтр: {res.filter_text} · base: {res.base_dn} · scope: {res.scope}")
            self._load_lists()

        def failed(exc):
            self.run_btn.setEnabled(True)
            self._load_lists()
            show_error(self, exc)
        self.run(lambda c, p: ExplorerService(ctx, db).run(base, scope, flt, attrs, limit, c), done, "LDAP-запрос",
                 on_error=failed)

    def _show_entry(self):
        e = self.results.current_row()
        if e is None or self.ctx is None:
            return
        ctx = self.ctx
        dn = e.dn

        def done(full):
            rows = [{"name": "distinguishedName", "value": full.dn},
                    {"name": "objectClass", "value": ", ".join(map(str, full.values("objectClass")))}]
            for k, vals in sorted(full.attributes.items(), key=lambda kv: kv[0].lower()):
                if k.lower() in ("objectclass",):
                    continue
                rows.append({"name": k, "value": "; ".join(display_value(k, v) for v in vals)})
            self.entry_attrs.set_rows(rows)
        self.run(lambda c, p: ExplorerService(ctx).object_attributes(dn), done, "Атрибуты объекта")

    def _export(self):
        if not self.last:
            return
        rep = self.results.to_report("Результаты LDAP-запроса", criteria={"Фильтр": self.last.filter_text,
                                                                          "Base DN": self.last.base_dn,
                                                                          "Область": self.last.scope},
                                     limitations=["Результат ограничен лимитом"] if self.last.stats.truncated else [],
                                     info=self.ctx.gateway.info if self.ctx else None)
        self.export(rep, "ldap_query")

    # favourites / history ----------------------------------------------------------------------------------
    def _load_lists(self):
        self.favs.clear()
        for q in self.db.saved_queries():
            item = QListWidgetItem(f"★ {q['name']}")
            item.setToolTip(q["filter"])
            item.setData(Qt.UserRole, q)
            self.favs.addItem(item)
        self.history.clear()
        for h in self.db.query_history(100):
            text = f"{h['ts'][:16]} · {h['result_count'] if h['result_count'] is not None else 'ошибка'} · {h['filter']}"
            item = QListWidgetItem(text)
            item.setToolTip(f"{h['base_dn']} ({h['scope']})\n{h['filter']}" + (f"\n{h['error']}" if h.get("error") else ""))
            item.setData(Qt.UserRole, h)
            self.history.addItem(item)

    def _apply(self, q: dict):
        self.base.setText(q.get("base_dn") or "")
        idx = self.scope.findData(q.get("scope"))
        if idx >= 0:
            self.scope.setCurrentIndex(idx)
        self.filter.setPlainText(q.get("filter", ""))
        self.attrs.setText(", ".join(q.get("attributes") or ["*"]))

    def _load_fav(self, item):
        self._apply(item.data(Qt.UserRole))

    def _load_hist(self, item):
        self._apply(item.data(Qt.UserRole))

    def _save_fav(self):
        if not self._validate():
            return
        name, ok = QInputDialog.getText(self, "Избранное", "Название запроса:")
        if ok and name.strip():
            try:
                attrs = validate_attributes(self.attrs.text())
            except ValidationError as exc:
                show_error(self, exc)
                return
            self.db.save_query(name.strip(), self.base.text().strip(), self.scope.currentData(),
                               parse_filter(self.filter.toPlainText()).to_ldap(), attrs)
            self._load_lists()

    def _del_fav(self):
        item = self.favs.currentItem()
        if item:
            self.db.delete_query(item.data(Qt.UserRole)["name"])
            self._load_lists()

