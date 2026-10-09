"""Dashboard: domain information and statistics with collection time and errors."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...ldap.adtypes import format_dt
from ...services.dashboard_service import DashboardService
from ...services.report_service import USER_COLUMNS, user_row
from ..widgets.common import banner, set_banner
from ..widgets.table import Column, DataTable
from .base import BasePage

CARD_ORDER = ["users_total", "users_enabled", "users_disabled", "users_locked", "users_pwd_expired", "users_pne",
              "users_stale", "users_recent", "computers_total", "computers_disabled", "computers_stale",
              "groups_security", "groups_total"]
CARD_TARGET = {"users_total": ("users", "all"), "users_enabled": ("users", "enabled"), "users_disabled": ("users", "disabled"),
               "users_locked": ("users", "locked"), "users_pwd_expired": ("users", "pwd_expired"),
               "users_pne": ("users", "pne"), "users_stale": ("users", "stale"), "users_recent": ("users", "recent"),
               "computers_total": ("computers", "all"), "computers_disabled": ("computers", "disabled"),
               "computers_stale": ("computers", "stale"), "groups_security": ("groups", None), "groups_total": ("groups", None)}


class Card(QFrame):
    def __init__(self, title: str, on_click=None):
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumWidth(170)
        self.on_click = on_click
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        self.value = QLabel("—")
        self.value.setObjectName("CardValue")
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        self.title.setWordWrap(True)
        self.note = QLabel("")
        self.note.setObjectName("Muted")
        self.note.setWordWrap(True)
        lay.addWidget(self.value)
        lay.addWidget(self.title)
        lay.addWidget(self.note)
        if on_click:
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip("Открыть список")

    def mousePressEvent(self, event):  # noqa: N802 - Qt API
        if self.on_click:
            self.on_click()

    def set_metric(self, m):
        from .. import theme
        c = theme.colors()
        if m.error:
            self.value.setText("ошибка")
            self.value.setStyleSheet(f"color: {c['danger']};")
            self.note.setText(m.error)
            return
        self.value.setText(("≈ " if not m.exact else "") + (str(m.value) if m.value is not None else "—"))
        color = {"danger": c["danger"], "warning": c["warning"]}.get(m.severity, "")
        self.value.setStyleSheet(f"color: {color};" if color and m.value else "")
        self.note.setText(m.note)


class DashboardPage(BasePage):
    title = "Главная"
    subtitle = "сводка по домену"

    def __init__(self, win):
        super().__init__(win)
        self.refresh_btn = QPushButton("Обновить статистику")
        self.refresh_btn.clicked.connect(self.refresh)
        self.header_actions.addWidget(self.refresh_btn)
        self.info = QLabel("Подключитесь к домену (кнопка «Подключиться…» вверху) или запустите демо-режим.")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.root.addWidget(self.info)
        self.updated = QLabel("")
        self.updated.setObjectName("Muted")
        self.root.addWidget(self.updated)
        self.errors = banner(danger=True)
        self.root.addWidget(self.errors)
        grid_w = QWidget()
        self.grid = QGridLayout(grid_w)
        self.grid.setSpacing(10)
        self.cards: dict[str, Card] = {}
        self.root.addWidget(grid_w)
        lbl = QLabel("Недавно созданные учётные записи")
        lbl.setStyleSheet("font-weight: 600;")
        self.root.addWidget(lbl)
        cols = [Column(k, t) for k, t in USER_COLUMNS]
        self.recent = DataTable(cols, "dashboard_recent", win.db)
        self.recent.activated.connect(lambda r: r and self.win.open_user(r["dn"]))
        self.root.addWidget(self.recent, 1)
        btn_row = QHBoxLayout()
        self.connect_big = QPushButton("Подключиться к домену…")
        self.connect_big.setProperty("primary", True)
        self.connect_big.clicked.connect(win.show_connect_dialog)
        btn_row.addWidget(self.connect_big)
        btn_row.addStretch(1)
        self.root.addLayout(btn_row)

    def _make_cards(self, stats):
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                w.deleteLater()
        self.cards.clear()
        for i, key in enumerate(k for k in CARD_ORDER if k in stats.metrics):
            m = stats.metrics[key]
            target = CARD_TARGET.get(key)
            card = Card(m.title, (lambda t=target: self._open(t)) if target else None)
            card.set_metric(m)
            self.cards[key] = card
            self.grid.addWidget(card, i // 5, i % 5)

    def _open(self, target):
        page, view = target
        self.win.navigate(page)
        if view is not None and hasattr(self.win.pages[page], "show_view"):
            self.win.pages[page].show_view(view)

    def on_connected(self):
        super().on_connected()
        self.connect_big.setVisible(False)
        info = self.ctx.gateway.info
        self.info.setText(
            f"<b>Домен:</b> {info.domain_dns} &nbsp; <b>NetBIOS:</b> {info.netbios_name or '—'} &nbsp; "
            f"<b>Base DN:</b> {info.base_dn}<br><b>Контроллер:</b> {info.dc_host} &nbsp; "
            f"<b>Уровень домена:</b> {info.level_text(info.domain_functionality)} &nbsp; "
            f"<b>Уровень леса:</b> {info.level_text(info.forest_functionality)}<br>"
            f"<b>Контроллеры домена:</b> {', '.join(info.domain_controllers) or '—'}<br>"
            f"<b>Учётная запись:</b> {info.bound_identity or '—'} &nbsp; <b>Подключено:</b> {format_dt(info.connected_at)} "
            f"&nbsp; <b>Канал:</b> {info.security_label}"
            + ("<br><b style='color:#f0b429'>ДЕМО-РЕЖИМ: вымышленный каталог в памяти, контроллер домена не используется.</b>"
               if info.is_demo else ""))

    def on_disconnected(self):
        super().on_disconnected()
        self.connect_big.setVisible(True)
        self.info.setText("Нет подключения.")
        self.recent.set_rows([])
        for c in self.cards.values():
            c.deleteLater()
        self.cards.clear()

    def initial_load(self):
        self.refresh()

    def refresh(self):
        if not self.need_ctx():
            return
        ctx = self.ctx
        self.refresh_btn.setEnabled(False)

        def done(stats):
            self.refresh_btn.setEnabled(True)
            self._make_cards(stats)
            self.updated.setText(f"Статистика обновлена: {format_dt(stats.collected_at)} · DC {stats.dc} · "
                                 f"сбор занял {stats.duration_s:.1f} с. Значения с «≈» приблизительные (см. примечания).")
            set_banner(self.errors, ["Ошибки сбора данных: " + "; ".join(stats.errors)] if stats.errors else [])
            self.recent.set_rows([user_row(u) for u in stats.recent_users])

        def failed(exc):
            self.refresh_btn.setEnabled(True)
            from ..widgets.common import show_error
            show_error(self, exc)
        self.run(lambda c, p: DashboardService(ctx).collect(c, p), done, "Сбор статистики домена", on_error=failed)
