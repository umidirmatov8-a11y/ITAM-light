"""Single-object administrative actions with confirmation, privileged-object protection and background execution.

Multi-object changes are always routed through the bulk-operation wizard (plan → pre-check → separate confirmation).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QDialog

from ..core.errors import ProtectedObjectError
from ..ldap.dn import rdn_value
from ..services.bulk_service import BulkOperation
from ..services.computer_service import ComputerService
from ..services.group_service import GroupService
from ..services.user_service import UserService
from .widgets.common import TypedConfirmDialog, confirm, show_error


class Actions:
    def __init__(self, win):
        self.win = win

    @property
    def ctx(self):
        return self.win.ctx

    def _write_allowed(self) -> bool:
        if self.ctx is None:
            self.win.toast("Нет подключения", "warning")
            return False
        if self.ctx.gateway.read_only:
            self.win.toast("Включён режим «Только чтение». Переключите режим в верхней панели, чтобы вносить изменения.",
                           "warning", 6000)
            return False
        return True

    def _run_protected(self, title: str, fn: Callable[[bool], object], done: Callable[[object], None],
                       phrase_hint: str) -> None:
        """Run fn(confirmed=False); on ProtectedObjectError ask for typed confirmation and retry with confirmed=True."""
        def on_error(exc):
            if isinstance(exc, ProtectedObjectError):
                ok = TypedConfirmDialog.ask(self.win, "Привилегированный объект", exc.message, phrase_hint,
                                            details=exc.details or "",
                                            checkbox="Я понимаю последствия изменения привилегированного объекта")
                if ok:
                    self.win.run_task(lambda c, p: fn(True), done, title=title)
                return
            show_error(self.win, exc)
        self.win.run_task(lambda c, p: fn(False), done, title=title, on_error=on_error)

    # ---------------------------------------------------------------------------------------------------------
    def set_user_enabled(self, rows: list, enabled: bool, refresh: Callable | None = None) -> None:
        if not self._write_allowed() or not rows:
            return
        if len(rows) > 1:
            self.win.start_bulk(BulkOperation.ENABLE if enabled else BulkOperation.DISABLE, [r.dn for r in rows], "user")
            return
        r = rows[0]
        verb = "Включить" if enabled else "Отключить"
        if not confirm(self.win, f"{verb} учётную запись", f"{verb} учётную запись «{r.name}» ({r.sam})?",
                       details=r.dn, danger=not enabled):
            return
        us = UserService(self.ctx)

        def done(changed):
            self.win.toast(f"{verb}: {r.name} — выполнено" if changed else f"{r.name}: уже в требуемом состоянии",
                           "success" if changed else "info")
            refresh and refresh()
        self._run_protected(f"{verb}: {r.name}", lambda conf: us.set_enabled(r.dn, enabled, privileged_confirmed=conf),
                            done, r.sam or r.name)

    def unlock(self, rows: list, refresh: Callable | None = None) -> None:
        if not self._write_allowed() or not rows:
            return
        if len(rows) > 1:
            self.win.start_bulk(BulkOperation.UNLOCK, [r.dn for r in rows], "user")
            return
        r = rows[0]
        if not confirm(self.win, "Разблокировка", f"Разблокировать учётную запись «{r.name}»?",
                       details="Перед разблокировкой рекомендуется выяснить источник неверных паролей (событие 4740)."):
            return

        def done(changed):
            self.win.toast(f"{r.name}: разблокирована" if changed else f"{r.name}: не была заблокирована",
                           "success" if changed else "info")
            refresh and refresh()
        self.win.run_task(lambda c, p: UserService(self.ctx).unlock(r.dn), done, title=f"Разблокировка {r.name}")

    def reset_password(self, row, refresh: Callable | None = None) -> None:
        if not self._write_allowed() or row is None:
            return
        if not self.ctx.gateway.encrypted:
            self.win.toast("Сброс пароля возможен только по зашифрованному соединению (LDAPS/StartTLS)", "error", 7000)
            return
        from .dialogs.user_dialogs import ResetPasswordDialog
        dlg = ResetPasswordDialog(self.win, row)
        if dlg.exec() != QDialog.Accepted:
            return
        password, must_change, unlock = dlg.values()
        dlg.clear_secret()
        us = UserService(self.ctx)

        def done(_):
            self.win.toast(f"Пароль пользователя {row.name} сброшен" + (" (смена при входе)" if must_change else ""), "success")
            refresh and refresh()
        self._run_protected(f"Сброс пароля {row.name}",
                            lambda conf: us.reset_password(row.dn, password, must_change=must_change, unlock=unlock,
                                                           privileged_confirmed=conf), done, row.sam or row.name)

    def must_change(self, row, value: bool, refresh: Callable | None = None) -> None:
        if not self._write_allowed() or row is None:
            return
        text = "Потребовать смену пароля при следующем входе" if value else "Снять требование смены пароля"
        if not confirm(self.win, "Пароль", f"{text} для «{row.name}»?"):
            return
        self.win.run_task(lambda c, p: UserService(self.ctx).set_must_change(row.dn, value),
                          lambda _: (self.win.toast("Выполнено", "success"), refresh and refresh()), title=text)

    def set_expiry(self, row, refresh: Callable | None = None) -> None:
        if not self._write_allowed() or row is None:
            return
        from .dialogs.user_dialogs import AccountExpiryDialog
        dlg = AccountExpiryDialog(self.win, row)
        if dlg.exec() != QDialog.Accepted:
            return
        value = dlg.value()
        self.win.run_task(lambda c, p: UserService(self.ctx).set_account_expiry(row.dn, value),
                          lambda _: (self.win.toast("Срок действия изменён", "success"), refresh and refresh()),
                          title="Срок действия учётной записи")

    def edit_user(self, row, refresh: Callable | None = None) -> None:
        if not self._write_allowed() or row is None:
            return
        from .dialogs.user_dialogs import EditUserDialog
        dlg = EditUserDialog(self.win, row.dn)
        if dlg.exec() != QDialog.Accepted:
            return
        new, original = dlg.changes()
        if not new:
            self.win.toast("Изменений нет", "info")
            return

        def done(changed):
            self.win.toast("Изменены атрибуты: " + ", ".join(changed) if changed else "Изменений нет", "success")
            refresh and refresh()
        self.win.run_task(lambda c, p: UserService(self.ctx).update_attributes(row.dn, new, original), done,
                          title="Изменение атрибутов")

    def move(self, rows: list, kind: str, refresh: Callable | None = None) -> None:
        if not self._write_allowed() or not rows:
            return
        if len(rows) > 1:
            self.win.start_bulk(BulkOperation.MOVE_TO_OU, [r.dn for r in rows], kind)
            return
        from .dialogs.pickers import OUPickerDialog
        target = OUPickerDialog.pick(self.win, "Целевое OU для перемещения")
        if not target:
            return
        r = rows[0]
        name = getattr(r, "name", "") or rdn_value(r.dn)
        if not confirm(self.win, "Перемещение", f"Переместить «{name}»?", details=f"Из: {r.dn}\nВ: {target}"):
            return
        svc = ComputerService(self.ctx) if kind == "computer" else UserService(self.ctx)
        self.win.run_task(lambda c, p: svc.move(r.dn, target),
                          lambda new_dn: (self.win.toast(f"Перемещено: {new_dn}", "success"), refresh and refresh()),
                          title=f"Перемещение {name}")

    def set_computer_enabled(self, rows: list, enabled: bool, refresh: Callable | None = None) -> None:
        if not self._write_allowed() or not rows:
            return
        if len(rows) > 1:
            self.win.start_bulk(BulkOperation.ENABLE if enabled else BulkOperation.DISABLE, [r.dn for r in rows], "computer")
            return
        r = rows[0]
        verb = "Включить" if enabled else "Отключить"
        if not confirm(self.win, f"{verb} компьютер", f"{verb} учётную запись компьютера «{r.name}»?", details=r.dn,
                       danger=not enabled):
            return
        self.win.run_task(lambda c, p: ComputerService(self.ctx).set_enabled(r.dn, enabled),
                          lambda ch: (self.win.toast(f"{r.name}: выполнено" if ch else f"{r.name}: без изменений",
                                                     "success" if ch else "info"), refresh and refresh()),
                          title=f"{verb} {r.name}")

    def add_to_group(self, member_dns: list[str], refresh: Callable | None = None, group_dn: str | None = None,
                     kind: str = "user") -> None:
        if not self._write_allowed() or not member_dns:
            return
        if group_dn is None:
            from .dialogs.pickers import ObjectPickerDialog
            picked = ObjectPickerDialog.pick(self.win, ("group",), "Выберите группу")
            if not picked:
                return
            group_dn = picked[0]
        if len(member_dns) > 1:
            self.win.start_bulk(BulkOperation.ADD_TO_GROUP, member_dns, kind, {"group_dn": group_dn})
            return
        member = member_dns[0]
        if not confirm(self.win, "Добавление в группу", f"Добавить «{rdn_value(member)}» в группу «{rdn_value(group_dn)}»?"):
            return
        gs = GroupService(self.ctx)
        self._run_protected("Добавление в группу",
                            lambda conf: gs.add_member(group_dn, member, privileged_confirmed=conf),
                            lambda ch: (self.win.toast("Добавлено в группу" if ch else "Уже является членом группы",
                                                       "success" if ch else "info"), refresh and refresh()),
                            rdn_value(group_dn))

    def remove_from_group(self, group_dn: str, member_dns: list[str], refresh: Callable | None = None,
                          kind: str = "user") -> None:
        if not self._write_allowed() or not member_dns:
            return
        if len(member_dns) > 1:
            self.win.start_bulk(BulkOperation.REMOVE_FROM_GROUP, member_dns, kind, {"group_dn": group_dn})
            return
        member = member_dns[0]
        if not confirm(self.win, "Удаление из группы",
                       f"Удалить «{rdn_value(member)}» из группы «{rdn_value(group_dn)}»?", danger=True):
            return
        gs = GroupService(self.ctx)
        self._run_protected("Удаление из группы",
                            lambda conf: gs.remove_member(group_dn, member, privileged_confirmed=conf),
                            lambda ch: (self.win.toast("Удалено из группы" if ch else "Не является прямым членом",
                                                       "success" if ch else "info"), refresh and refresh()),
                            rdn_value(group_dn))
