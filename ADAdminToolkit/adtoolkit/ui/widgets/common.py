"""Common UI helpers: notifications, confirmations (incl. typed confirmation), error dialog, export, banners."""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from ...core.errors import OperationCancelledError, ToolkitError, describe_exception
from ...ldap.adtypes import utcnow
from ...reports.exporters import ReportTable, export_csv, export_html, export_xlsx
from ...security.audit_log import windows_user
from ...security.masking import mask_text


def report_meta(table: ReportTable, info=None) -> ReportTable:
    table.generated_at = table.generated_at or utcnow()
    table.generated_by = table.generated_by or windows_user()
    if info is not None:
        table.domain = table.domain or info.domain_dns
        table.dc = table.dc or info.dc_host
    return table


class Toast(QLabel):
    def __init__(self, parent: QWidget, text: str, kind: str = "info", msecs: int = 4500):
        super().__init__(text, parent)
        self.setObjectName("Toast")
        self.setProperty("kind", kind)
        self.setWordWrap(True)
        self.setMaximumWidth(460)
        self.setMinimumWidth(280)
        self.adjustSize()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        QTimer.singleShot(msecs, self.close_toast)

    def mousePressEvent(self, event):  # noqa: N802 - Qt API
        self.close_toast()

    def close_toast(self):
        parent = self.parentWidget()
        self.hide()
        self.deleteLater()
        if parent is not None and hasattr(parent, "_relayout_toasts"):
            QTimer.singleShot(0, parent._relayout_toasts)


class ToastHost:
    """Mixin for the main window."""

    def _init_toasts(self):
        self._toasts: list[Toast] = []

    def toast(self, text: str, kind: str = "info", msecs: int = 4500):
        t = Toast(self, text, kind, msecs)
        self._toasts.append(t)
        t.show()
        t.raise_()
        self._relayout_toasts()

    def _relayout_toasts(self):
        alive = []
        for t in self._toasts:
            try:
                if t.isVisible():
                    alive.append(t)
            except RuntimeError:
                continue
        self._toasts = alive
        y = self.height() - 40
        for t in reversed(self._toasts):
            t.adjustSize()
            y -= t.height() + 8
            t.move(self.width() - t.width() - 24, max(60, y))


def show_error(parent: QWidget, exc: BaseException, title: str = "Ошибка") -> None:
    if isinstance(exc, OperationCancelledError):
        return
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(520)
    lay = QVBoxLayout(dlg)
    if isinstance(exc, ToolkitError):
        head = QLabel(f"<b>{_esc(exc.message)}</b>")
        lay.addWidget(_wrap(head))
        if exc.hint:
            lay.addWidget(_wrap(QLabel("Рекомендация: " + _esc(exc.hint))))
        details = exc.details or ""
    else:
        lay.addWidget(_wrap(QLabel("<b>Непредвиденная ошибка</b>")))
        details = describe_exception(exc)
    if details:
        box = QPlainTextEdit(mask_text(details))
        box.setReadOnly(True)
        box.setMaximumHeight(140)
        lay.addWidget(QLabel("Технические сведения:"))
        lay.addWidget(box)
    bb = QDialogButtonBox(QDialogButtonBox.Ok)
    copy_btn = bb.addButton("Копировать", QDialogButtonBox.ActionRole)
    copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(describe_exception(exc)))
    bb.accepted.connect(dlg.accept)
    lay.addWidget(bb)
    dlg.exec()


def _esc(text: str) -> str:
    import html
    return html.escape(str(text)).replace("\n", "<br>")


def _wrap(label: QLabel) -> QLabel:
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def confirm(parent: QWidget, title: str, text: str, *, details: str = "", danger: bool = False,
            ok_text: str = "Выполнить") -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    box.setText(text)
    if details:
        box.setInformativeText(details)
    ok = box.addButton(ok_text, QMessageBox.AcceptRole)
    cancel = box.addButton("Отмена", QMessageBox.RejectRole)
    box.setDefaultButton(cancel if danger else ok)
    box.exec()
    return box.clickedButton() is ok


class TypedConfirmDialog(QDialog):
    """Separate confirmation: the operator must type an exact phrase (privileged groups, bulk changes, OU deletion)."""

    def __init__(self, parent: QWidget, title: str, message: str, phrase: str, *, details: str = "",
                 checkbox: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.phrase = phrase
        lay = QVBoxLayout(self)
        banner = QLabel(message)
        banner.setObjectName("DangerBanner")
        banner.setWordWrap(True)
        lay.addWidget(banner)
        if details:
            d = QPlainTextEdit(details)
            d.setReadOnly(True)
            d.setMaximumHeight(160)
            lay.addWidget(d)
        lay.addWidget(QLabel(f"Для подтверждения введите: <b>{_esc(phrase)}</b>"))
        self.edit = QLineEdit()
        lay.addWidget(self.edit)
        self.check = None
        if checkbox:
            self.check = QCheckBox(checkbox)
            lay.addWidget(self.check)
        bb = QDialogButtonBox()
        self.ok = bb.addButton("Подтвердить", QDialogButtonBox.AcceptRole)
        self.ok.setProperty("danger", True)
        bb.addButton("Отмена", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.ok.setEnabled(False)
        self.edit.textChanged.connect(self._check)
        if self.check:
            self.check.toggled.connect(self._check)

    def _check(self):
        ok = self.edit.text().strip() == self.phrase
        if self.check is not None:
            ok = ok and self.check.isChecked()
        self.ok.setEnabled(ok)

    @staticmethod
    def ask(parent, title, message, phrase, **kw) -> bool:
        dlg = TypedConfirmDialog(parent, title, message, phrase, **kw)
        return dlg.exec() == QDialog.Accepted


def banner(text: str = "", danger: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("DangerBanner" if danger else "Banner")
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lbl.setVisible(bool(text))
    return lbl


def set_banner(lbl: QLabel, lines: list[str]) -> None:
    text = "\n".join(f"ⓘ {l}" for l in lines if l)
    lbl.setText(text)
    lbl.setVisible(bool(text))


def default_filename(base: str, ext: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in base)[:60].strip("_") or "report"
    return f"{safe}_{datetime.now():%Y%m%d_%H%M}.{ext}"


def ask_export_path(parent: QWidget, base_name: str, *, html: bool = False, last_dir: str = "") -> str | None:
    filters = "Excel (*.xlsx);;CSV — разделитель «;» (*.csv)"
    if html:
        filters += ";;HTML (*.html)"
    start = os.path.join(last_dir or os.path.expanduser("~"), default_filename(base_name, "xlsx"))
    path, selected = QFileDialog.getSaveFileName(parent, "Экспорт отчёта", start, filters)
    if not path:
        return None
    lower = path.lower()
    if not lower.endswith((".xlsx", ".csv", ".html", ".htm")):
        path += ".csv" if "csv" in selected.lower() else (".html" if "html" in selected.lower() else ".xlsx")
    return path


def write_report(tables: list[ReportTable], path: str, title: str = "", kpis=None) -> str:
    lower = path.lower()
    if lower.endswith(".xlsx"):
        export_xlsx(tables, path)
    elif lower.endswith((".html", ".htm")):
        export_html(tables, path, title=title or (tables[0].title if tables else "Отчёт"), kpis=kpis)
    else:
        if len(tables) == 1:
            export_csv(tables[0], path)
        else:
            stem, _ = os.path.splitext(path)
            for i, t in enumerate(tables, start=1):
                export_csv(t, f"{stem}_{i}.csv")
            path = f"{stem}_1..{len(tables)}.csv"
    return path


class PasswordField(QWidget):
    """Password line edit with show/hide toggle; the value is never logged."""

    def __init__(self, parent=None, placeholder: str = ""):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(self)
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.toggle = QPushButton("👁", self)
        self.toggle.setCheckable(True)
        self.toggle.setFixedWidth(34)
        self.toggle.setToolTip("Показать/скрыть")
        self.toggle.toggled.connect(lambda on: self.edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.toggle)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self.edit.setText(text)

    def clear(self) -> None:
        self.edit.clear()


def copy_secret(text: str, clear_after_s: int = 30) -> None:
    """Copy a secret to the clipboard and clear it after a delay (only if it still contains the same value)."""
    cb = QApplication.clipboard()
    cb.setText(text)
    if clear_after_s > 0:
        def clear():
            if cb.text() == text:
                cb.clear()
        QTimer.singleShot(clear_after_s * 1000, clear)
