"""Dark and light corporate themes (Fusion style + stylesheet)."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

THEMES = {
    "dark": {
        "bg": "#14181f", "panel": "#1b212b", "panel2": "#222a36", "border": "#2e3846", "text": "#e3e8ef",
        "muted": "#8e9aab", "accent": "#3d8bfd", "accent_text": "#ffffff", "sidebar": "#10141a", "sel": "#2b4a78",
        "danger": "#ff6b6b", "warning": "#f0b429", "ok": "#3ecf8e", "info": "#6cb6ff", "input": "#11161d",
        "row_alt": "#1e2530", "danger_bg": "#3a1f24", "warning_bg": "#3a3320", "muted_row": "#7d8896",
    },
    "light": {
        "bg": "#f3f5f8", "panel": "#ffffff", "panel2": "#f7f9fb", "border": "#d5dbe3", "text": "#1b2430",
        "muted": "#5f6b7a", "accent": "#1f6feb", "accent_text": "#ffffff", "sidebar": "#1f2a37", "sel": "#cfe0fb",
        "danger": "#c62828", "warning": "#b26a00", "ok": "#1b7f4c", "info": "#1f6feb", "input": "#ffffff",
        "row_alt": "#f6f8fb", "danger_bg": "#fde8e8", "warning_bg": "#fff4dc", "muted_row": "#8a94a3",
    },
}

_current = {"name": "dark"}


def colors() -> dict:
    return THEMES[_current["name"]]


def current() -> str:
    return _current["name"]


def apply_theme(app: QApplication, name: str) -> None:
    name = name if name in THEMES else "dark"
    _current["name"] = name
    c = THEMES[name]
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(c["bg"]))
    pal.setColor(QPalette.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.Base, QColor(c["input"]))
    pal.setColor(QPalette.AlternateBase, QColor(c["row_alt"]))
    pal.setColor(QPalette.Text, QColor(c["text"]))
    pal.setColor(QPalette.Button, QColor(c["panel2"]))
    pal.setColor(QPalette.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.Highlight, QColor(c["sel"]))
    pal.setColor(QPalette.HighlightedText, QColor(c["text"] if name == "dark" else "#0b1220"))
    pal.setColor(QPalette.ToolTipBase, QColor(c["panel"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
    pal.setColor(QPalette.Link, QColor(c["accent"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(c["muted"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(c))


def stylesheet(c: dict) -> str:
    return f"""
    QWidget {{ font-size: 10pt; }}
    QMainWindow, QDialog {{ background: {c['bg']}; }}
    #Sidebar {{ background: {c['sidebar']}; border: none; color: #c9d3df; outline: 0; }}
    #Sidebar::item {{ padding: 9px 14px; border-left: 3px solid transparent; }}
    #Sidebar::item:selected {{ background: #23344d; color: #ffffff; border-left: 3px solid {c['accent']}; }}
    #Sidebar::item:hover:!selected {{ background: #1a2433; }}
    #AppTitle {{ color: #ffffff; font-size: 13pt; font-weight: 600; padding: 12px 14px 4px 14px; background: {c['sidebar']}; }}
    #AppSubtitle {{ color: #8796a8; padding: 0 14px 10px 14px; background: {c['sidebar']}; font-size: 9pt; }}
    #TopBar {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; }}
    #PageTitle {{ font-size: 15pt; font-weight: 600; }}
    #Muted, QLabel[muted="true"] {{ color: {c['muted']}; }}
    #Card {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 8px; }}
    #CardValue {{ font-size: 20pt; font-weight: 600; }}
    #CardTitle {{ color: {c['muted']}; }}
    #Banner {{ background: {c['warning_bg']}; border: 1px solid {c['warning']}; border-radius: 6px; padding: 6px 10px; }}
    #DangerBanner {{ background: {c['danger_bg']}; border: 1px solid {c['danger']}; border-radius: 6px; padding: 6px 10px; }}
    #Pill {{ border-radius: 10px; padding: 3px 10px; font-weight: 600; }}
    QGroupBox {{ border: 1px solid {c['border']}; border-radius: 6px; margin-top: 12px; padding: 8px 6px 6px 6px;
                 background: {c['panel']}; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {c['muted']}; }}
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
        background: {c['input']}; border: 1px solid {c['border']}; border-radius: 5px; padding: 4px 6px;
        selection-background-color: {c['sel']}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {c['accent']}; }}
    QPushButton {{ background: {c['panel2']}; border: 1px solid {c['border']}; border-radius: 5px; padding: 5px 12px; }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton[primary="true"] {{ background: {c['accent']}; color: {c['accent_text']}; border-color: {c['accent']}; font-weight: 600; }}
    QPushButton[danger="true"] {{ background: {c['danger']}; color: #ffffff; border-color: {c['danger']}; font-weight: 600; }}
    QPushButton:checked {{ background: {c['sel']}; }}
    QPushButton[small="true"] {{ padding: 2px 4px; }}
    QToolButton {{ border: 1px solid transparent; border-radius: 5px; padding: 4px 8px; }}
    QToolButton:hover {{ border-color: {c['border']}; background: {c['panel2']}; }}
    QTableView, QTreeView, QListView, QTreeWidget, QListWidget {{ background: {c['panel']}; alternate-background-color: {c['row_alt']};
        border: 1px solid {c['border']}; gridline-color: {c['border']}; selection-background-color: {c['sel']}; }}
    QHeaderView::section {{ background: {c['panel2']}; border: none; border-right: 1px solid {c['border']};
        border-bottom: 1px solid {c['border']}; padding: 5px 6px; font-weight: 600; }}
    QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 4px; background: {c['panel']}; }}
    QTabBar::tab {{ background: {c['panel2']}; border: 1px solid {c['border']}; padding: 6px 12px; margin-right: 2px;
        border-top-left-radius: 5px; border-top-right-radius: 5px; }}
    QTabBar::tab:selected {{ background: {c['panel']}; border-bottom-color: {c['panel']}; font-weight: 600; }}
    QStatusBar {{ background: {c['panel']}; border-top: 1px solid {c['border']}; }}
    QProgressBar {{ border: 1px solid {c['border']}; border-radius: 4px; text-align: center; background: {c['input']}; max-height: 14px; }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
    QToolTip {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; }}
    QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; }}
    QMenu::item:selected {{ background: {c['sel']}; }}
    #Toast {{ background: {c['panel']}; border: 1px solid {c['border']}; border-left: 5px solid {c['accent']};
        border-radius: 6px; padding: 10px 14px; }}
    #Toast[kind="error"] {{ border-left-color: {c['danger']}; }}
    #Toast[kind="success"] {{ border-left-color: {c['ok']}; }}
    #Toast[kind="warning"] {{ border-left-color: {c['warning']}; }}
    """
