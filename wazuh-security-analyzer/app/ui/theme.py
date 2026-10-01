"""Dark SOC theme (Qt style sheet + palette)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from app.core.severity import SEVERITY_COLORS

BG = "#0d1117"
PANEL = "#151b23"
PANEL_ALT = "#1b2330"
BORDER = "#263241"
TEXT = "#e6edf3"
MUTED = "#8b98a8"
ACCENT = "#3fa9f5"
ACCENT_DARK = "#1f6fb2"
SIDEBAR = "#0a0e14"
SUCCESS = "#3fb950"
WARNING = "#d29922"

SEV = SEVERITY_COLORS

STYLE = f"""
* {{ font-family: "Segoe UI", "Inter", "Roboto", sans-serif; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QDialog, QWidget#page {{ background: {BG}; }}
QWidget {{ background: transparent; }}
QToolTip {{ background: {PANEL_ALT}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QFrame#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QLabel#brand {{ font-size: 13pt; font-weight: 700; color: {TEXT}; padding: 4px 8px; }}
QLabel#brandSub {{ color: {MUTED}; font-size: 8pt; padding: 0 8px 8px 8px; }}
QPushButton#navButton {{ text-align: left; padding: 9px 14px; border: none; border-radius: 6px; color: {MUTED};
    font-size: 10.5pt; background: transparent; }}
QPushButton#navButton:hover {{ background: {PANEL}; color: {TEXT}; }}
QPushButton#navButton:checked {{ background: {PANEL_ALT}; color: {TEXT}; border-left: 3px solid {ACCENT}; }}
QFrame#topbar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QLabel#pageTitle {{ font-size: 16pt; font-weight: 700; }}
QLabel#sectionTitle {{ font-size: 11pt; font-weight: 700; color: {TEXT}; padding: 2px 0; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#modeBadge {{ border-radius: 9px; padding: 2px 10px; font-weight: 700; font-size: 8.5pt; }}
QFrame#card, QFrame#statCard, QFrame#chartCard {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#statCard:hover {{ border: 1px solid {ACCENT}; }}
QFrame#dropZone {{ background: {PANEL}; border: 2px dashed {BORDER}; border-radius: 14px; }}
QFrame#dropZone[active="true"] {{ border: 2px dashed {ACCENT}; background: {PANEL_ALT}; }}
QPushButton {{ background: {PANEL_ALT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {MUTED}; border-color: {PANEL_ALT}; }}
QPushButton#primary {{ background: {ACCENT_DARK}; border: 1px solid {ACCENT}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT}; }}
QPushButton#danger {{ background: #5a1d27; border: 1px solid {SEV['critical']}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{ background: {BG}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 5px 8px; selection-background-color: {ACCENT_DARK}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit#globalSearch {{ min-width: 360px; padding: 6px 12px; border-radius: 15px; background: {BG}; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_DARK}; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {MUTED};
    background: {BG}; }}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QTableView, QTableWidget, QTreeWidget, QListWidget {{ background: {PANEL}; alternate-background-color: {PANEL_ALT};
    border: 1px solid {BORDER}; border-radius: 8px; gridline-color: {BORDER}; selection-background-color: #23415e;
    selection-color: {TEXT}; }}
QHeaderView::section {{ background: {PANEL_ALT}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px; font-weight: 600; }}
QTableCornerButton::section {{ background: {PANEL_ALT}; border: none; }}
QTextBrowser {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; background: {PANEL}; top: -1px; }}
QTabBar::tab {{ background: {BG}; color: {MUTED}; padding: 7px 16px; border: 1px solid {BORDER}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {PANEL}; color: {TEXT}; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 8px; margin-top: 14px; padding: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {MUTED}; }}
QProgressBar {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 6px; text-align: center; height: 16px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: {BG}; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSplitter::handle {{ background: {BG}; }}
QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QLabel#warning {{ background: #3b2a0d; border: 1px solid {WARNING}; border-radius: 6px; padding: 8px; color: #f0c674; }}
QScrollArea {{ border: none; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(PANEL))
    palette.setColor(QPalette.AlternateBase, QColor(PANEL_ALT))
    palette.setColor(QPalette.ToolTipBase, QColor(PANEL_ALT))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(PANEL_ALT))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(ACCENT_DARK))
    palette.setColor(QPalette.HighlightedText, QColor(TEXT))
    palette.setColor(QPalette.Link, QColor(ACCENT))
    palette.setColor(QPalette.PlaceholderText, QColor(MUTED))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


def severity_color(severity: str) -> str:
    return SEV.get((severity or "").lower(), MUTED)
