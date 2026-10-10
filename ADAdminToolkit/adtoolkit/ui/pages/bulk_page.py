"""Bulk operations wizard and offboarding (employees who left)."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from ...ldap.dn import rdn_value
from ...services.bulk_service import (STATUS_ERROR, STATUS_LABELS, STATUS_READY, STATUS_SKIP, BulkOperation, BulkService,
                                      guess_identity_column, parse_csv)
from ...services.offboarding_service import DEFAULT_TEMPLATE, STEP_LABELS, OffboardingService
from ..widgets.common import TypedConfirmDialog, banner, confirm, set_banner, show_error
from ..widgets.table import Column, DataTable
from .base import BasePage

ITEM_COLUMNS = [
    Column("source", "Исходное значение", lambda i: i.source),
    Column("name", "Объект", lambda i: i.name),
    Column("sam", "Логин", lambda i: i.sam),
    Column("current", "Текущее состояние", lambda i: i.current),
    Column("planned", "Планируемое изменение", lambda i: i.planned),
    Column("status", "Предпроверка", lambda i: STATUS_LABELS.get(i.status, i.status)),
    Column("reason", "Причина пропуска/ошибки", lambda i: i.reason),
    Column("privileged", "Привилегии", lambda i: i.privileged),
    Column("result", "Результат", lambda i: i.result),
    Column("error", "Ошибка выполнения", lambda i: i.error),
    Column("dn", "DN", lambda i: i.dn, visible=False),
]


def item_state(i) -> str | None:
    if i.error or i.status == STATUS_ERROR:
        return "danger"
    if i.status == STATUS_SKIP:
        return "muted"
    if i.result.startswith("Выполнено"):
        return "ok"
    return None


class BulkWizard(QWidget):
    def __init__(self, page: "BulkPage"):
        super().__init__()
        self.page = page
        self.win = page.win
        self.plan = None
        self.csv_rows: list[dict] = []
        lay = QVBoxLayout(self)
        s1 = QGroupBox("1. Операция и список объектов")
        f1 = QFormLayout(s1)
        self.op = QComboBox()
        for op in BulkOperation:
            self.op.addItem(op.label, op)
        self.kind = QComboBox()
        self.kind.addItem("Пользователи", "user")
        self.kind.addItem("Компьютеры", "computer")
        self.kind.addItem("Группы (только для операций с группами)", "group")
        self.group = QLineEdit()
        self.group.setPlaceholderText("DN группы")
        gbtn = QPushButton("…")
        gbtn.setFixedWidth(34)
        gbtn.setProperty("small", True)
        gbtn.clicked.connect(self._pick_group)
        grow = QHBoxLayout()
        grow.addWidget(self.group, 1)
        grow.addWidget(gbtn)
        self.group_w = QWidget()
        grow.setContentsMargins(0, 0, 0, 0)
        self.group_w.setLayout(grow)
        self.ou = QLineEdit()
        self.ou.setPlaceholderText("DN целевого OU")
        obtn = QPushButton("…")
        obtn.setFixedWidth(34)
        obtn.setProperty("small", True)
        obtn.clicked.connect(self._pick_ou)
        orow = QHBoxLayout()
        orow.addWidget(self.ou, 1)
        orow.addWidget(obtn)
        self.ou_w = QWidget()
        orow.setContentsMargins(0, 0, 0, 0)
        self.ou_w.setLayout(orow)
        f1.addRow("Операция:", self.op)
        f1.addRow("Тип объектов:", self.kind)
        f1.addRow("Группа:", self.group_w)
        f1.addRow("Целевое OU:", self.ou_w)
        src = QHBoxLayout()
        imp = QPushButton("Импорт CSV…")
        imp.clicked.connect(self._import_csv)
        self.column = QComboBox()
        self.column.setMinimumWidth(180)
        self.column.currentIndexChanged.connect(self._use_column)
        src.addWidget(imp)
        src.addWidget(QLabel("Столбец идентификатора:"))
        src.addWidget(self.column)
        src.addStretch(1)
        f1.addRow("Источник:", src)
        self.ids = QPlainTextEdit()
        self.ids.setPlaceholderText("Идентификаторы по одному в строке: sAMAccountName, UPN, email, табельный номер или DN")
        self.ids.setMaximumHeight(110)
        f1.addRow("Объекты:", self.ids)
        self.csv_preview = DataTable([Column("row", "Предпросмотр CSV")], show_toolbar=False)
        self.csv_preview.setMaximumHeight(120)
        self.csv_preview.setVisible(False)
        f1.addRow("", self.csv_preview)
        self.plan_btn = QPushButton("2. Проверить и построить план")
        self.plan_btn.setProperty("primary", True)
        self.plan_btn.clicked.connect(self.build_plan)
        f1.addRow("", self.plan_btn)
        lay.addWidget(s1)
        self.counts = QLabel("")
        self.counts.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.counts)
        self.blocked = banner(danger=True)
        lay.addWidget(self.blocked)
        self.table = DataTable(ITEM_COLUMNS, "bulk_items", self.win.db, export_cb=self._export)
        self.table.set_state_fn(item_state)
        lay.addWidget(self.table, 1)
        s3 = QHBoxLayout()
        self.dry = QCheckBox("Dry Run — только моделирование, без изменений в AD")
        self.dry.setChecked(True)
        self.rate = QDoubleSpinBox()
        self.rate.setRange(0.2, 50)
        self.rate.setValue(self.win.settings.bulk_rate_per_second)
        self.rate.setSuffix(" опер./с")
        self.priv = QCheckBox("Разрешить привилегированные УЗ (если разрешено в настройках)")
        self.priv.setEnabled(self.win.settings.bulk_allow_privileged)
        self.exec_btn = QPushButton("3. Выполнить")
        self.exec_btn.setProperty("danger", True)
        self.exec_btn.setEnabled(False)
        self.exec_btn.clicked.connect(self.execute)
        s3.addWidget(self.dry)
        s3.addWidget(QLabel("Скорость:"))
        s3.addWidget(self.rate)
        s3.addWidget(self.priv)
        s3.addStretch(1)
        s3.addWidget(self.exec_btn)
        lay.addLayout(s3)
        self.op.currentIndexChanged.connect(self._op_changed)
        self._op_changed()

    def _op_changed(self):
        op = BulkOperation(self.op.currentData())
        self.group_w.setEnabled(op in (BulkOperation.ADD_TO_GROUP, BulkOperation.REMOVE_FROM_GROUP))
        self.ou_w.setEnabled(op is BulkOperation.MOVE_TO_OU)
        self.plan = None
        self.exec_btn.setEnabled(False)

    def _pick_group(self):
        from ..dialogs.pickers import ObjectPickerDialog
        dns = ObjectPickerDialog.pick(self.win, ("group",), "Группа")
        if dns:
            self.group.setText(dns[0])

    def _pick_ou(self):
        from ..dialogs.pickers import OUPickerDialog
        dn = OUPickerDialog.pick(self.win)
        if dn:
            self.ou.setText(dn)

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт CSV", "", "CSV (*.csv *.txt);;Все файлы (*)")
        if not path:
            return
        try:
            headers, rows = parse_csv(path)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self.csv_rows = rows
        self.column.blockSignals(True)
        self.column.clear()
        for h in headers:
            self.column.addItem(h)
        self.column.setCurrentText(guess_identity_column(headers))
        self.column.blockSignals(False)
        self.csv_preview.setVisible(True)
        self.csv_preview.set_rows([{"row": "; ".join(f"{k}={v}" for k, v in r.items())} for r in rows[:20]])
        self._use_column()
        self.win.toast(f"Загружено строк: {len(rows)}. Проверьте столбец идентификатора.", "info")

    def _use_column(self):
        col = self.column.currentText()
        if self.csv_rows and col:
            self.ids.setPlainText("\n".join(r.get(col, "") for r in self.csv_rows if r.get(col, "").strip()))

    def prefill(self, op: BulkOperation, dns: list[str], kind: str, params: dict):
        self.op.setCurrentIndex(list(BulkOperation).index(op))
        idx = self.kind.findData(kind)
        if idx >= 0:
            self.kind.setCurrentIndex(idx)
        self.group.setText(params.get("group_dn", ""))
        self.ou.setText(params.get("target_ou", ""))
        self.ids.setPlainText("\n".join(dns))
        self.csv_preview.setVisible(False)
        self.build_plan()

    def build_plan(self):
        if not self.page.need_ctx():
            return
        ids = [l.strip() for l in self.ids.toPlainText().splitlines() if l.strip()]
        if not ids:
            self.win.toast("Список объектов пуст", "info")
            return
        op, kind = BulkOperation(self.op.currentData()), self.kind.currentData()
        params = {}
        if op in (BulkOperation.ADD_TO_GROUP, BulkOperation.REMOVE_FROM_GROUP):
            if not self.group.text().strip():
                self.win.toast("Выберите группу", "warning")
                return
            params["group_dn"] = self.group.text().strip()
        if op is BulkOperation.MOVE_TO_OU:
            if not self.ou.text().strip():
                self.win.toast("Выберите целевое OU", "warning")
                return
            params["target_ou"] = self.ou.text().strip()
        if self.priv.isChecked():
            params["privileged_accounts_confirmed"] = True
        ctx = self.page.ctx
        self.exec_btn.setEnabled(False)

        def job(cancel, progress):
            bs = BulkService(ctx)
            items = bs.resolve(ids, kind, cancel, progress)
            return bs.plan(op, items, params, cancel=cancel, progress=progress)
        self.page.run(job, self._show_plan, "Предварительная проверка массовой операции")

    def _show_plan(self, plan, target_confirmed: bool = False):
        self.plan = plan
        c = plan.counts()
        self.counts.setText(f"Операция: {plan.operation.label} · будет изменено: {c[STATUS_READY]} · "
                            f"пропуск: {c[STATUS_SKIP]} · ошибки проверки: {c[STATUS_ERROR]}")
        set_banner(self.blocked, [plan.blocked_reason] if plan.blocked_reason else [])
        self.table.set_rows(plan.items)
        self.exec_btn.setEnabled(bool(plan.ready) and (not plan.blocked_reason or bool(plan.target_privileged)))
        self.exec_btn.setText("3. Выполнить (Dry Run)" if self.dry.isChecked() else "3. Выполнить")

    def execute(self):
        plan = self.plan
        if plan is None or not plan.ready:
            return
        dry = self.dry.isChecked() or not plan.operation.modifies
        ctx = self.page.ctx
        if not dry and ctx.gateway.read_only:
            self.win.toast("Включён режим «Только чтение». Для реального выполнения разрешите изменения или используйте Dry Run.",
                           "warning", 7000)
            return
        n = len(plan.ready)
        if plan.target_privileged and plan.blocked_reason:
            name = rdn_value(plan.params.get("group_dn", ""))
            if not TypedConfirmDialog.ask(self.win, "Привилегированная группа", plan.blocked_reason, name,
                                          checkbox="Я подтверждаю изменение состава привилегированной группы"):
                return
            plan.blocked_reason = ""
        if dry:
            if not confirm(self.win, "Dry Run", f"Смоделировать операцию для {n} объектов? Изменения в AD не выполняются."):
                return
        else:
            details = "\n".join(f"{i.name}: {i.planned}" for i in plan.ready[:200]) + ("\n…" if n > 200 else "")
            if not TypedConfirmDialog.ask(self.win, "Подтверждение массовой операции",
                                          f"{plan.operation.label}: будет изменено объектов — {n}. Пропущено: "
                                          f"{plan.counts()[STATUS_SKIP]}, ошибок проверки: {plan.counts()[STATUS_ERROR]}.",
                                          f"ВЫПОЛНИТЬ {n}", details=details):
                return
        rate = self.rate.value()
        self.exec_btn.setEnabled(False)

        def done(p):
            self.table.set_rows(p.items)
            rc = p.result_counts()
            self.counts.setText(("Dry Run завершён: " if p.dry_run else "Выполнено: ") +
                                ", ".join(f"{k}: {v}" for k, v in rc.items()) + f" · пакет {p.batch_id}")
            self.win.toast("Массовая операция завершена — выгрузите отчёт кнопкой «Экспорт…»", "success", 6000)
            self.exec_btn.setEnabled(p.dry_run)  # after a Dry Run the same plan may be executed for real

        def failed(exc):
            self.exec_btn.setEnabled(True)
            self.table.set_rows(plan.items)
            show_error(self.win, exc)
        self.page.run(lambda c, p: BulkService(ctx).execute(plan, dry_run=dry, rate_per_second=rate, cancel=c, progress=p),
                      done, "Массовая операция", on_error=failed)

    def _export(self):
        if self.plan is None or self.page.ctx is None:
            return
        self.page.export(BulkService(self.page.ctx).report(self.plan), "bulk_results")


class TemplateDialog(QDialog):
    def __init__(self, win, template: dict):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Шаблон обработки уволенных")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(template.get("name", ""))
        form.addRow("Название:", self.name)
        self.checks = {}
        for key in ("disable", "set_description", "remove_groups", "expire_now", "reset_password", "clear_manager", "hide_from_gal"):
            cb = QCheckBox(STEP_LABELS[key])
            cb.setChecked(bool(template.get(key)))
            self.checks[key] = cb
            form.addRow("", cb)
        self.desc = QLineEdit(template.get("description_text", "Уволен {date} {ticket}"))
        self.desc.setToolTip("{date} — текущая дата, {ticket} — номер заявки")
        self.keep = QLineEdit(", ".join(template.get("keep_groups") or []))
        self.keep.setPlaceholderText("Группы, которые не удалять (имена через запятую)")
        self.move = QLineEdit(template.get("move_to_ou", ""))
        self.move.setPlaceholderText("DN OU для уволенных (пусто — не перемещать)")
        form.addRow("Текст описания:", self.desc)
        form.addRow("Не удалять группы:", self.keep)
        form.addRow("Переместить в OU:", self.move)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def value(self) -> dict:
        t = {k: cb.isChecked() for k, cb in self.checks.items()}
        t.update(name=self.name.text().strip() or "Шаблон", description_text=self.desc.text(),
                 keep_groups=[x.strip() for x in self.keep.text().split(",") if x.strip()], move_to_ou=self.move.text().strip())
        return t


class OffboardingTab(QWidget):
    def __init__(self, page: "BulkPage"):
        super().__init__()
        self.page = page
        self.win = page.win
        self.rows = []
        self.executed = False
        lay = QVBoxLayout(self)
        note = QLabel("Процедура увольнения: сначала строится план (можно выгрузить как список для отключения без изменений в AD), "
                      "затем — Dry Run или выполнение с отдельным подтверждением. Привилегированные УЗ исключаются.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)
        row = QHBoxLayout()
        self.template = QComboBox()
        self._load_templates()
        edit = QPushButton("Изменить шаблон…")
        edit.clicked.connect(self._edit_template)
        new = QPushButton("Новый шаблон…")
        new.clicked.connect(lambda: self._edit_template(new=True))
        self.ticket = QLineEdit()
        self.ticket.setPlaceholderText("Номер заявки / приказа")
        row.addWidget(QLabel("Шаблон:"))
        row.addWidget(self.template, 1)
        row.addWidget(edit)
        row.addWidget(new)
        row.addWidget(self.ticket, 1)
        lay.addLayout(row)
        srow = QHBoxLayout()
        self.marker = QLineEdit("уволен")
        self.marker.setMaximumWidth(160)
        find = QPushButton("Найти включённые УЗ с маркером в описании")
        find.clicked.connect(self._find_marker)
        exp = QPushButton("Найти включённые УЗ с истёкшим сроком")
        exp.clicked.connect(self._find_expired)
        srow.addWidget(QLabel("Маркер:"))
        srow.addWidget(self.marker)
        srow.addWidget(find)
        srow.addWidget(exp)
        srow.addStretch(1)
        lay.addLayout(srow)
        self.ids = QPlainTextEdit()
        self.ids.setPlaceholderText("Сотрудники: логин, UPN, email, табельный номер или DN — по одному в строке")
        self.ids.setMaximumHeight(100)
        lay.addWidget(self.ids)
        brow = QHBoxLayout()
        plan = QPushButton("Подготовить план (без изменений)")
        plan.setProperty("primary", True)
        plan.clicked.connect(self._plan)
        self.dry = QCheckBox("Dry Run")
        self.dry.setChecked(True)
        self.exec_btn = QPushButton("Выполнить")
        self.exec_btn.setProperty("danger", True)
        self.exec_btn.setEnabled(False)
        self.exec_btn.clicked.connect(self._execute)
        export = QPushButton("Экспорт плана/результата…")
        export.clicked.connect(self._export)
        brow.addWidget(plan)
        brow.addStretch(1)
        brow.addWidget(self.dry)
        brow.addWidget(self.exec_btn)
        brow.addWidget(export)
        lay.addLayout(brow)
        self.table = DataTable([Column("name", "Сотрудник", lambda r: r.item.name or r.item.source),
                                Column("sam", "Логин", lambda r: r.item.sam), Column("current", "Состояние", lambda r: r.item.current),
                                Column("planned", "План", lambda r: r.item.planned),
                                Column("status", "Предпроверка", lambda r: STATUS_LABELS.get(r.item.status, r.item.status)),
                                Column("reason", "Причина", lambda r: r.item.reason),
                                Column("groups", "Групп к удалению", lambda r: len(r.groups_to_remove), align_right=True),
                                Column("result", "Результат", lambda r: r.item.result),
                                Column("error", "Ошибки", lambda r: r.item.error)], "offboarding", self.win.db)
        self.table.set_state_fn(lambda r: item_state(r.item))
        lay.addWidget(self.table, 1)

    def _load_templates(self):
        self.template.clear()
        items = self.win.db.templates("offboarding") or [dict(DEFAULT_TEMPLATE)]
        for t in items:
            self.template.addItem(t["name"], t)

    def _edit_template(self, new: bool = False):
        t = dict(DEFAULT_TEMPLATE) if new else dict(self.template.currentData() or DEFAULT_TEMPLATE)
        if new:
            t["name"] = "Новый шаблон"
        dlg = TemplateDialog(self.win, t)
        if dlg.exec():
            v = dlg.value()
            self.win.db.save_template("offboarding", v["name"], v)
            self._load_templates()
            self.template.setCurrentText(v["name"])
            self.win.toast("Шаблон сохранён", "success")

    def prefill(self, dns: list[str]):
        self.ids.setPlainText("\n".join(dns))
        if dns:
            self._plan()

    def _find_marker(self):
        if not self.page.need_ctx():
            return
        ctx, marker = self.page.ctx, self.marker.text()
        self.page.run(lambda c, p: OffboardingService(ctx).find_candidates(marker, c),
                      lambda dns: (self.ids.setPlainText("\n".join(dns)), self.win.toast(f"Найдено: {len(dns)}", "info")),
                      "Поиск уволенных")

    def _find_expired(self):
        if not self.page.need_ctx():
            return
        ctx = self.page.ctx
        self.page.run(lambda c, p: OffboardingService(ctx).expired_enabled_candidates(c),
                      lambda dns: (self.ids.setPlainText("\n".join(dns)), self.win.toast(f"Найдено: {len(dns)}", "info")),
                      "Поиск УЗ с истёкшим сроком")

    def _plan(self):
        if not self.page.need_ctx():
            return
        ids = [l.strip() for l in self.ids.toPlainText().splitlines() if l.strip()]
        if not ids:
            return
        ctx, template, ticket = self.page.ctx, self.template.currentData() or dict(DEFAULT_TEMPLATE), self.ticket.text()

        def done(rows):
            self.rows = rows
            self.executed = False
            self.table.set_rows(rows)
            self.exec_btn.setEnabled(any(r.item.status == STATUS_READY for r in rows))
        self.page.run(lambda c, p: OffboardingService(ctx).plan(ids, template, ticket, c, p), done, "План увольнения")

    def _execute(self):
        ready = [r for r in self.rows if r.item.status == STATUS_READY]
        if not ready:
            return
        dry = self.dry.isChecked()
        ctx = self.page.ctx
        if not dry and ctx.gateway.read_only:
            self.win.toast("Включён режим «Только чтение»", "warning")
            return
        n = len(ready)
        if dry:
            if not confirm(self.win, "Dry Run", f"Смоделировать обработку {n} сотрудников?"):
                return
        elif not TypedConfirmDialog.ask(self.win, "Обработка увольнения", f"Будут изменены учётные записи: {n}.",
                                        f"УВОЛИТЬ {n}", details="\n".join(f"{r.item.name}: {r.item.planned}" for r in ready[:200])):
            return
        template, ticket = self.template.currentData() or dict(DEFAULT_TEMPLATE), self.ticket.text()

        def done(rows):
            self.executed = True
            self.table.set_rows(rows)
            self.win.toast("Обработка завершена" + (" (Dry Run)" if dry else ""), "success")
        self.page.run(lambda c, p: OffboardingService(ctx).execute(self.rows, template, ticket, dry_run=dry, cancel=c, progress=p),
                      done, "Обработка увольнения")

    def _export(self):
        if not self.rows or self.page.ctx is None:
            return
        t = OffboardingService(self.page.ctx).report(self.rows, self.template.currentData() or DEFAULT_TEMPLATE,
                                                     self.ticket.text(), self.executed, self.dry.isChecked())
        self.page.export(t, "offboarding")


class BulkPage(BasePage):
    title = "Массовые операции"
    subtitle = "план → предпроверка → подтверждение → выполнение/Dry Run → отчёт"

    def __init__(self, win):
        super().__init__(win)
        self.tabs = QTabWidget()
        self.wizard = BulkWizard(self)
        self.offboarding = OffboardingTab(self)
        self.tabs.addTab(self.wizard, "Мастер массовых операций")
        self.tabs.addTab(self.offboarding, "Увольнение сотрудников")
        self.root.addWidget(self.tabs, 1)

    def prefill(self, op, dns, kind, params):
        self.tabs.setCurrentWidget(self.wizard)
        self.wizard.prefill(op, dns, kind, params)

    def prefill_offboarding(self, dns):
        self.tabs.setCurrentWidget(self.offboarding)
        self.offboarding.prefill(dns)

