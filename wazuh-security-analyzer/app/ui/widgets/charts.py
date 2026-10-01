"""Lightweight QPainter charts (no extra dependencies, crisp on HiDPI)."""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from app.core.severity import SEVERITY_ORDER
from app.ui import theme


def _fmt(n: float) -> str:
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1000:.0f}k"
    return f"{n:,}"


class HBarChart(QWidget):
    """Horizontal bar chart. ``items`` = [(label, value, color|None, payload)]."""

    itemClicked = Signal(object)

    def __init__(self, parent=None, max_items: int = 10):
        super().__init__(parent)
        self.items: list[tuple[str, float, str | None, object]] = []
        self.max_items = max_items
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self._rows: list[tuple[QRectF, int]] = []

    def set_items(self, items) -> None:
        self.items = [(str(i[0]), float(i[1]), i[2] if len(i) > 2 else None, i[3] if len(i) > 3 else i[0])
                      for i in items][: self.max_items]
        self.setMinimumHeight(max(120, 26 * len(self.items) + 10))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._rows = []
        if not self.items:
            p.setPen(QColor(theme.MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "No data")
            return
        w, h = self.width(), self.height()
        label_w = min(220, int(w * 0.42))
        value_w = 56
        row_h = min(26, (h - 6) / len(self.items))
        vmax = max(v for _, v, _, _ in self.items) or 1
        font = QFont(self.font())
        font.setPointSizeF(8.8)
        p.setFont(font)
        fm = p.fontMetrics()
        for idx, (label, value, color, _payload) in enumerate(self.items):
            y = 3 + idx * row_h
            p.setPen(QColor(theme.TEXT))
            text = fm.elidedText(label, Qt.ElideRight, label_w - 8)
            p.drawText(QRectF(0, y, label_w - 8, row_h), Qt.AlignVCenter | Qt.AlignRight, text)
            bar_w = max(2.0, (w - label_w - value_w) * value / vmax)
            rect = QRectF(label_w, y + row_h * 0.22, bar_w, row_h * 0.56)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color or theme.ACCENT))
            p.drawRoundedRect(rect, 3, 3)
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(label_w + bar_w + 6, y, value_w, row_h), Qt.AlignVCenter | Qt.AlignLeft, _fmt(value))
            self._rows.append((QRectF(0, y, w, row_h), idx))

    def _row_at(self, pos) -> int | None:
        for rect, idx in self._rows:
            if rect.contains(QPointF(pos)):
                return idx
        return None

    def mouseMoveEvent(self, event) -> None:
        idx = self._row_at(event.position())
        if idx is not None:
            label, value, _, _ = self.items[idx]
            QToolTip.showText(event.globalPosition().toPoint(), f"{label}: {value:,.0f}", self)
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event) -> None:
        idx = self._row_at(event.position())
        if idx is not None:
            self.itemClicked.emit(self.items[idx][3])


class TimelineChart(QWidget):
    """Stacked column chart of events per time bucket and severity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: dict = {}
        self.setMinimumHeight(180)
        self.setMouseTracking(True)

    def set_data(self, data: dict) -> None:
        self.data = data or {}
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        series = self.data.get("series") or {}
        n = int(self.data.get("n") or 0)
        if not series or not n:
            p.setPen(QColor(theme.MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "No timestamped events")
            return
        w, h = self.width(), self.height()
        left, bottom, top = 46, 22, 8
        totals = [sum(series.get(s.value, [0] * n)[i] for s in SEVERITY_ORDER) for i in range(n)]
        vmax = max(totals) or 1
        plot_h = h - bottom - top
        bar_w = (w - left - 4) / n
        font = QFont(self.font())
        font.setPointSizeF(8)
        p.setFont(font)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        for frac in (0.0, 0.5, 1.0):
            y = top + plot_h * (1 - frac)
            p.drawLine(int(left), int(y), int(w), int(y))
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(0, y - 8, left - 6, 16), Qt.AlignRight | Qt.AlignVCenter, _fmt(vmax * frac))
            p.setPen(QPen(QColor(theme.BORDER), 1))
        order = list(reversed(SEVERITY_ORDER))  # informational at the bottom
        for i in range(n):
            y = top + plot_h
            for sev in order:
                value = (series.get(sev.value) or [0] * n)[i]
                if not value:
                    continue
                bh = plot_h * value / vmax
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.SEV[sev.value]))
                p.drawRect(QRectF(left + i * bar_w + 1, y - bh, max(bar_w - 2, 1), bh))
                y -= bh
        start, size = self.data.get("start") or 0, self.data.get("bucket") or 3600
        p.setPen(QColor(theme.MUTED))
        fmt = "%m-%d %H:%M" if size < 86400 else "%Y-%m-%d"
        for i in (0, n // 2, n - 1):
            ts = start + i * size
            label = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt)
            x = left + i * bar_w
            p.drawText(QRectF(x - 50, h - bottom + 4, 100, 16), Qt.AlignCenter, label)

    def mouseMoveEvent(self, event) -> None:
        series = self.data.get("series") or {}
        n = int(self.data.get("n") or 0)
        if not n:
            return
        left = 46
        bar_w = (self.width() - left - 4) / n
        i = int((event.position().x() - left) // bar_w) if bar_w else -1
        if 0 <= i < n:
            start, size = self.data.get("start") or 0, self.data.get("bucket") or 3600
            label = datetime.fromtimestamp(start + i * size, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            parts = [f"{s.value}: {(series.get(s.value) or [0] * n)[i]:,}" for s in SEVERITY_ORDER
                     if (series.get(s.value) or [0] * n)[i]]
            QToolTip.showText(event.globalPosition().toPoint(), label + "\n" + "\n".join(parts or ["no events"]), self)


class DonutChart(QWidget):
    """Severity distribution donut."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values: dict[str, int] = {}
        self.setMinimumSize(170, 170)

    def set_values(self, values: dict[str, int]) -> None:
        self.values = values or {}
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        total = sum(self.values.values())
        side = min(self.width(), self.height()) - 10
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        if not total:
            p.setPen(QPen(QColor(theme.BORDER), 14))
            p.drawEllipse(rect.adjusted(10, 10, -10, -10))
            return
        angle = 90 * 16
        pen_w = max(12, side * 0.13)
        inner = rect.adjusted(pen_w / 2 + 2, pen_w / 2 + 2, -pen_w / 2 - 2, -pen_w / 2 - 2)
        for sev in SEVERITY_ORDER:
            value = self.values.get(sev.value, 0)
            if not value:
                continue
            span = -int(360 * 16 * value / total)
            if span == 0:
                span = -16
            p.setPen(QPen(QColor(theme.SEV[sev.value]), pen_w, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(inner, angle, span)
            angle += span
        p.setPen(QColor(theme.TEXT))
        font = QFont(self.font())
        font.setPointSizeF(14)
        font.setBold(True)
        p.setFont(font)
        p.drawText(rect, Qt.AlignCenter, _fmt(total) + "\n")
        font.setPointSizeF(8)
        font.setBold(False)
        p.setFont(font)
        p.setPen(QColor(theme.MUTED))
        p.drawText(rect, Qt.AlignCenter, "\n\nevents")
