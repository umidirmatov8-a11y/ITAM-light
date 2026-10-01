"""Small building blocks: cards, stat tiles, drop zone, section headers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from app.i18n import num, severity_label, tr
from app.ui import theme


def label(text: str = "", object_name: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if object_name:
        lbl.setObjectName(object_name)
    lbl.setWordWrap(wrap)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lbl


class Card(QFrame):
    def __init__(self, title: str = "", parent=None, object_name: str = "card"):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(14, 12, 14, 12)
        self.layout_.setSpacing(8)
        if title:
            self.title = label(tr(title), "sectionTitle")
            self.layout_.addWidget(self.title)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.layout_.addWidget(widget, stretch)
        return widget


class StatCard(QFrame):
    clicked = Signal()

    def __init__(self, title: str, value: str = "0", color: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(78)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self.color = color
        self.title = QLabel(tr(title).upper())
        self.title.setStyleSheet(f"color: {color or theme.MUTED}; font-size: 8.5pt; font-weight: 700; "
                                 "letter-spacing: 1px;")
        self.value = QLabel(value)
        self.value.setStyleSheet("font-size: 20pt; font-weight: 700;")
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        if color:
            self.setStyleSheet(f"QFrame#statCard {{ border-left: 4px solid {color}; }}")

    def set_value(self, value) -> None:
        self.value.setText(num(value) if isinstance(value, int) else str(value))

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class DropZone(QFrame):
    """Drag & drop area for files, folders and archives."""

    pathsSelected = Signal(list)
    demoRequested = Signal()

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setProperty("active", False)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10 if not compact else 6)
        icon = QLabel("⬇")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"font-size: {'40' if not compact else '22'}pt; color: {theme.ACCENT};")
        title = QLabel(tr("DROP WAZUH LOGS HERE"))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"font-size: {'18' if not compact else '12'}pt; font-weight: 800; letter-spacing: 2px;")
        sub = QLabel("JSON / JSONL / NDJSON / CSV / XML / LOG / TXT / CEF / ZIP / GZ  —  " + tr("files or folders"))
        sub.setAlignment(Qt.AlignCenter)
        sub.setObjectName("muted")
        buttons = QHBoxLayout()
        buttons.setAlignment(Qt.AlignCenter)
        self.btn_files = QPushButton(tr("Select Files"))
        self.btn_files.setObjectName("primary")
        self.btn_folder = QPushButton(tr("Select Folder"))
        self.btn_demo = QPushButton(tr("Load Demo Dataset"))
        for b in (self.btn_files, self.btn_folder, self.btn_demo):
            b.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(b)
        if not compact:
            lay.addWidget(icon)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addLayout(buttons)
        self.btn_files.clicked.connect(self._select_files)
        self.btn_folder.clicked.connect(self._select_folder)
        self.btn_demo.clicked.connect(self.demoRequested.emit)
        self.setMinimumHeight(240 if not compact else 130)

    def _select_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("Select Wazuh alert files"), str(Path.home()),
            tr("Logs and archives") + " (*.json *.jsonl *.ndjson *.log *.txt *.csv *.tsv *.xml *.cef *.zip *.gz);;"
            + tr("All files") + " (*)")
        if files:
            self.pathsSelected.emit(files)

    def _select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Select folder with logs"), str(Path.home()))
        if folder:
            self.pathsSelected.emit([folder])

    def _set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_active(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_active(False)

    def dropEvent(self, event) -> None:
        self._set_active(False)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.pathsSelected.emit(paths)
            event.acceptProposedAction()


def severity_badge_html(severity: str, text: str | None = None) -> str:
    color = theme.severity_color(severity)
    fg = "#ffffff" if severity in ("critical",) else "#0d1117"
    return (f'<span style="background-color:{color}; color:{fg}; font-weight:700; padding:1px 6px;">'
            f'&nbsp;{(text or severity_label(severity)).upper()}&nbsp;</span>')
