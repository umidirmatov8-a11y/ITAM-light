"""Paged table model: rows are fetched from SQLite one page at a time (scales to millions)."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableView,
                               QVBoxLayout, QWidget)

from app.ui import theme

Column = tuple[str, str, Callable[[dict[str, Any]], Any] | None]  # (key, header, formatter)


class RowsModel(QAbstractTableModel):
    def __init__(self, columns: list[Column], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict[str, Any]] = []
        self.severity_key = "severity"

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section][1]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key, _, fmt = self.columns[index.column()]
        if role == Qt.DisplayRole:
            value = fmt(row) if fmt else row.get(key)
            if isinstance(value, float):
                return f"{value:.0f}" if key in ("risk_score", "max_risk") else f"{value:.2f}"
            if isinstance(value, int):
                return f"{value:,}"
            return "" if value is None else str(value)
        if role == Qt.ToolTipRole:
            value = fmt(row) if fmt else row.get(key)
            text = "" if value is None else str(value)
            return text if len(text) > 30 else None
        if role == Qt.ForegroundRole and key == self.severity_key:
            return QBrush(QColor(theme.severity_color(str(row.get(key, "")))))
        if role == Qt.FontRole and key == self.severity_key:
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.UserRole:
            return row
        return None

    def row(self, r: int) -> dict[str, Any] | None:
        return self.rows[r] if 0 <= r < len(self.rows) else None


class PagedTable(QWidget):
    """Table + pagination bar. ``fetch(offset, limit)`` returns rows, ``count()`` the total."""

    rowSelected = Signal(dict)
    rowActivated = Signal(dict)

    def __init__(self, columns: list[Column], page_size: int = 500, parent=None):
        super().__init__(parent)
        self.page_size = page_size
        self.page = 0
        self.total = 0
        self._fetch: Callable[[int, int], list[dict[str, Any]]] | None = None
        self._count: Callable[[], int] | None = None
        self.model = RowsModel(columns)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(26)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.view.setWordWrap(False)
        self.view.setShowGrid(False)
        self.view.selectionModel().currentRowChanged.connect(self._on_current)
        self.view.doubleClicked.connect(lambda idx: self.rowActivated.emit(self.model.row(idx.row()) or {}))
        self.prev_btn = QPushButton("◀ Prev")
        self.next_btn = QPushButton("Next ▶")
        self.info = QLabel("")
        self.info.setObjectName("muted")
        self.prev_btn.clicked.connect(lambda: self.go(self.page - 1))
        self.next_btn.clicked.connect(lambda: self.go(self.page + 1))
        bar = QHBoxLayout()
        bar.addWidget(self.info)
        bar.addStretch(1)
        bar.addWidget(self.prev_btn)
        bar.addWidget(self.next_btn)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view, 1)
        lay.addLayout(bar)

    def set_source(self, fetch: Callable[[int, int], list[dict[str, Any]]], count: Callable[[], int]) -> None:
        self._fetch = fetch
        self._count = count
        self.refresh()

    def clear(self) -> None:
        self._fetch = None
        self._count = None
        self.model.set_rows([])
        self.info.setText("")

    def refresh(self) -> None:
        if self._count is None:
            return
        self.total = self._count()
        self.go(0)

    def go(self, page: int) -> None:
        if self._fetch is None:
            return
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page = max(0, min(page, pages - 1))
        rows = self._fetch(self.page * self.page_size, self.page_size)
        self.model.set_rows(rows)
        start = self.page * self.page_size + (1 if rows else 0)
        self.info.setText(f"{start:,}–{self.page * self.page_size + len(rows):,} of {self.total:,}"
                          f"   ·   page {self.page + 1} / {pages}")
        self.prev_btn.setEnabled(self.page > 0)
        self.next_btn.setEnabled(self.page < pages - 1)
        if rows:
            self.view.selectRow(0)

    def set_widths(self, widths: list[int]) -> None:
        for i, w in enumerate(widths):
            self.view.setColumnWidth(i, w)

    def _on_current(self, current, _previous) -> None:
        row = self.model.row(current.row())
        if row is not None:
            self.rowSelected.emit(row)

    def current_row(self) -> dict[str, Any] | None:
        idx = self.view.currentIndex()
        return self.model.row(idx.row()) if idx.isValid() else None


class SimpleTable(PagedTable):
    """In-memory variant for small lists (incidents, IOC, CVE)."""

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        data = list(rows)
        self.set_source(lambda off, lim: data[off:off + lim], lambda: len(data))
