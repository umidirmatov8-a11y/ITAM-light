"""Generic data table: sorting, quick filter, configurable/persisted columns, state colouring, copy and export."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
                               QTableView, QToolButton, QVBoxLayout, QWidget)

from ...reports.exporters import ReportTable, format_value
from .. import theme


@dataclass
class Column:
    key: str
    title: str
    getter: Callable[[Any], Any] | None = None
    width: int = 0
    visible: bool = True
    align_right: bool = False
    sort: Callable[[Any], Any] | None = None     # optional sort key (e.g. severity rank instead of label)

    def value(self, row) -> Any:
        if self.getter is not None:
            return self.getter(row)
        if isinstance(row, dict):
            return row.get(self.key)
        return getattr(row, self.key, None)


def display(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone().strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    return format_value(value)


def sort_key(value: Any):
    if value is None or value == "":
        return (0, "")
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, (int, float)):
        return (1, value)
    if isinstance(value, datetime):
        return (1, value.timestamp())
    return (2, str(value).casefold())


class RecordModel(QAbstractTableModel):
    def __init__(self, columns: list[Column], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.rows: list[Any] = []
        self.state_fn: Callable[[Any], str | None] | None = None
        self.tooltip_fn: Callable[[Any], str | None] | None = None

    def set_rows(self, rows: list[Any]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802 - Qt API
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < len(self.columns):
            return self.columns[section].title
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = self.columns[index.column()]
        if role == Qt.DisplayRole:
            return display(col.value(row))
        if role == Qt.UserRole:
            return sort_key(col.sort(row) if col.sort else col.value(row))
        if role == Qt.UserRole + 1:
            return row
        if role == Qt.TextAlignmentRole and col.align_right:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role in (Qt.ForegroundRole, Qt.BackgroundRole) and self.state_fn:
            state = self.state_fn(row)
            if not state:
                return None
            c = theme.colors()
            if role == Qt.ForegroundRole:
                color = {"danger": c["danger"], "warning": c["warning"], "muted": c["muted_row"], "ok": c["ok"],
                         "info": c["info"]}.get(state)
                return QBrush(QColor(color)) if color else None
            if state == "danger":
                return QBrush(QColor(c["danger_bg"]))
            return None
        if role == Qt.ToolTipRole:
            if self.tooltip_fn:
                tip = self.tooltip_fn(row)
                if tip:
                    return tip
            text = display(col.value(row))
            return text if len(text) > 40 else None
        return None


class FilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.setSortRole(Qt.UserRole)

    def set_text(self, text: str) -> None:
        self.text = text.casefold().strip()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):  # noqa: N802 - Qt API
        if not self.text:
            return True
        model = self.sourceModel()
        for c in range(model.columnCount()):
            v = model.data(model.index(source_row, c, source_parent), Qt.DisplayRole)
            if v and self.text in str(v).casefold():
                return True
        return False

    def lessThan(self, left, right):  # noqa: N802 - Qt API
        a, b = left.data(Qt.UserRole), right.data(Qt.UserRole)
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


class DataTable(QWidget):
    activated = Signal(object)          # row object (double click / Enter)
    selection_changed = Signal()

    def __init__(self, columns: list[Column], view_id: str = "", db=None, parent=None, *, show_toolbar: bool = True,
                 export_cb: Callable[[], None] | None = None, default_sort: int | None = None):
        super().__init__(parent)
        self.view_id = view_id
        self.db = db
        self.model = RecordModel(columns, self)
        self.proxy = FilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.menu_builder: Callable[[QMenu, list], None] | None = None
        self.export_cb = export_cb

        self.view = QTableView(self)
        self.view.setModel(self.proxy)
        self.view.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)   # keep source order until a click
        self.view.setSortingEnabled(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setAlternatingRowColors(True)
        self.view.setWordWrap(False)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(26)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().setSectionsMovable(True)
        self.view.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.horizontalHeader().customContextMenuRequested.connect(self._header_menu)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._context_menu)
        self.view.doubleClicked.connect(lambda idx: self.activated.emit(self._row_at(idx)))
        self.view.selectionModel().selectionChanged.connect(lambda *_: self.selection_changed.emit())
        copy = QAction("Копировать", self.view)
        copy.setShortcut(QKeySequence.Copy)
        copy.setShortcutContext(Qt.WidgetShortcut)
        copy.triggered.connect(self.copy_selection)
        self.view.addAction(copy)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        if show_toolbar:
            bar = QHBoxLayout()
            self.filter_edit = QLineEdit(self)
            self.filter_edit.setPlaceholderText("Быстрый фильтр по загруженным строкам…")
            self.filter_edit.setClearButtonEnabled(True)
            self._filter_timer = QTimer(self)
            self._filter_timer.setSingleShot(True)
            self._filter_timer.setInterval(200)
            self._filter_timer.timeout.connect(lambda: (self.proxy.set_text(self.filter_edit.text()), self._update_count()))
            self.filter_edit.textChanged.connect(lambda _: self._filter_timer.start())
            self.count_label = QLabel("", self)
            self.count_label.setObjectName("Muted")
            self.count_label.setMinimumWidth(110)
            cols_btn = QToolButton(self)
            cols_btn.setText("Столбцы ▾")
            cols_btn.setPopupMode(QToolButton.InstantPopup)
            self._cols_menu = QMenu(cols_btn)
            self._cols_menu.aboutToShow.connect(self._fill_columns_menu)
            cols_btn.setMenu(self._cols_menu)
            bar.addWidget(self.filter_edit, 1)
            bar.addWidget(self.count_label)
            bar.addWidget(cols_btn)
            if export_cb:
                exp = QToolButton(self)
                exp.setText("Экспорт…")
                exp.clicked.connect(export_cb)
                bar.addWidget(exp)
            layout.addLayout(bar)
        else:
            self.filter_edit = None
            self.count_label = None
        layout.addWidget(self.view, 1)
        self._restored = False
        self._autosized = False
        self._suspend_save = False
        self._apply_default_visibility()
        self._restore_state()
        if default_sort is not None:
            self.view.sortByColumn(default_sort, Qt.AscendingOrder)
        self.view.horizontalHeader().sectionResized.connect(lambda *_: self._schedule_save())
        self.view.horizontalHeader().sectionMoved.connect(lambda *_: self._schedule_save())
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(self.save_state)

    # ---------------------------------------------------------------------------------------------------------
    def set_rows(self, rows: list[Any]) -> None:
        self.model.set_rows(rows)
        if rows and not self._restored and not self._autosized:
            self.autosize()
            self._autosized = True
        self._update_count()

    def autosize(self) -> None:
        """Fit columns to header and content (capped), without triggering a state save."""
        header = self.view.horizontalHeader()
        self._suspend_save = True
        try:
            sample = min(self.model.rowCount(), 200)
            fm = self.view.fontMetrics()
            for i, col in enumerate(self.model.columns):
                if self.view.isColumnHidden(i):
                    continue
                width = fm.horizontalAdvance(col.title) + 34
                for r in range(sample):
                    text = self.model.data(self.model.index(r, i), Qt.DisplayRole) or ""
                    width = max(width, fm.horizontalAdvance(str(text)[:120]) + 16)
                self.view.setColumnWidth(i, min(width, 380))
            header.setStretchLastSection(True)
        finally:
            self._suspend_save = False

    def set_columns(self, columns: list[Column]) -> None:
        """Replace the column set (used for dynamic result sets, e.g. LDAP Explorer)."""
        self.model.beginResetModel()
        self.model.columns = list(columns)
        self.model.rows = []
        self.model.endResetModel()
        self._apply_default_visibility()
        self._autosized = False

    def rows(self) -> list[Any]:
        return list(self.model.rows)

    def visible_rows(self) -> list[Any]:
        return [self.proxy.index(r, 0).data(Qt.UserRole + 1) for r in range(self.proxy.rowCount())]

    def set_state_fn(self, fn) -> None:
        self.model.state_fn = fn

    def set_tooltip_fn(self, fn) -> None:
        self.model.tooltip_fn = fn

    def _row_at(self, proxy_index):
        if not proxy_index.isValid():
            return None
        return self.proxy.index(proxy_index.row(), 0).data(Qt.UserRole + 1)

    def selected_rows(self) -> list[Any]:
        rows = []
        for idx in self.view.selectionModel().selectedRows():
            r = self._row_at(idx)
            if r is not None:
                rows.append(r)
        return rows

    def current_row(self):
        sel = self.selected_rows()
        return sel[0] if sel else None

    def _update_count(self):
        if self.count_label is not None:
            total = self.model.rowCount()
            shown = self.proxy.rowCount()
            self.count_label.setText(f"{shown} из {total}" if shown != total else f"Строк: {total}")

    # ---------------------------------------------------------------------------------------------------------
    def _context_menu(self, pos):
        rows = self.selected_rows()
        menu = QMenu(self)
        if self.menu_builder and rows:
            self.menu_builder(menu, rows)
            menu.addSeparator()
        menu.addAction("Копировать выделенные строки", self.copy_selection)
        idx = self.view.indexAt(pos)
        if idx.isValid():
            cell = idx.data(Qt.DisplayRole)
            menu.addAction("Копировать значение ячейки", lambda: QApplication.clipboard().setText(str(cell or "")))
        if self.export_cb:
            menu.addAction("Экспорт…", self.export_cb)
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def copy_selection(self):
        rows = self.view.selectionModel().selectedRows()
        if not rows:
            return
        cols = [c for c in range(self.model.columnCount()) if not self.view.isColumnHidden(c)]
        lines = ["\t".join(self.model.columns[c].title for c in cols)]
        for idx in sorted(rows, key=lambda i: i.row()):
            lines.append("\t".join(str(self.proxy.index(idx.row(), c).data(Qt.DisplayRole) or "") for c in cols))
        QApplication.clipboard().setText("\n".join(lines))

    def _header_menu(self, pos):
        menu = QMenu(self)
        self._fill_columns_menu(menu)
        menu.exec(self.view.horizontalHeader().mapToGlobal(pos))

    def _fill_columns_menu(self, menu: QMenu | None = None):
        menu = menu or self._cols_menu
        menu.clear()
        for i, col in enumerate(self.model.columns):
            act = menu.addAction(col.title)
            act.setCheckable(True)
            act.setChecked(not self.view.isColumnHidden(i))
            act.toggled.connect(lambda checked, i=i: (self.view.setColumnHidden(i, not checked), self._schedule_save()))
        menu.addSeparator()
        menu.addAction("Подобрать ширину", lambda: (self.autosize(), self._schedule_save()))
        menu.addAction("Сбросить настройку столбцов", self.reset_state)

    # ---------------------------------------------------------------------------------------------------------
    def _apply_default_visibility(self):
        for i, col in enumerate(self.model.columns):
            self.view.setColumnHidden(i, not col.visible)
            if col.width:
                self.view.setColumnWidth(i, col.width)

    def _schedule_save(self):
        if self.db and self.view_id and not self._suspend_save and hasattr(self, "_save_timer"):
            self._save_timer.start()

    def save_state(self):
        if not (self.db and self.view_id):
            return
        state = bytes(self.view.horizontalHeader().saveState())
        hidden = [self.model.columns[i].key for i in range(len(self.model.columns)) if self.view.isColumnHidden(i)]
        self.db.set_setting(f"table_state:{self.view_id}", {"header": base64.b64encode(state).decode("ascii"),
                                                            "hidden": hidden, "ncols": len(self.model.columns)})

    def _restore_state(self):
        if not (self.db and self.view_id):
            return
        data = self.db.get_setting(f"table_state:{self.view_id}")
        if not data or data.get("ncols") != len(self.model.columns):
            return
        try:
            self.view.horizontalHeader().restoreState(base64.b64decode(data["header"]))
        except Exception:  # noqa: BLE001 - corrupted state is ignored
            return
        hidden = set(data.get("hidden") or [])
        for i, col in enumerate(self.model.columns):
            self.view.setColumnHidden(i, col.key in hidden)
        self._restored = True
        self.view.horizontalHeader().setSortIndicatorShown(True)

    def reset_state(self):
        if self.db and self.view_id:
            self.db.set_setting(f"table_state:{self.view_id}", {})
        self._restored = False
        self._apply_default_visibility()
        self.autosize()

    # ---------------------------------------------------------------------------------------------------------
    def to_report(self, title: str, *, rows: list | None = None, criteria: dict | None = None,
                  limitations: list[str] | None = None, info=None, all_columns: bool = False) -> ReportTable:
        cols = [(c.key, c.title, c) for i, c in enumerate(self.model.columns) if all_columns or not self.view.isColumnHidden(i)]
        data = []
        for r in (rows if rows is not None else self.visible_rows()):
            data.append({key: col.value(r) for key, _, col in cols})
        from ..widgets.common import report_meta
        return report_meta(ReportTable(title=title, columns=[(k, t) for k, t, _ in cols], rows=data,
                                       criteria=dict(criteria or {}), limitations=list(limitations or [])), info)
