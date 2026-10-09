"""AD Admin Toolkit — entry point.

Usage:
    python main.py            # start the GUI (connection dialog opens)
    python main.py --demo     # test mode: in-memory demo directory, no domain controller is used
    python main.py --version  # print version and exit
    python main.py --selftest [--selftest-out=FILE]
                              # import all modules and run a short demo-directory self-test (used by build_exe.bat);
                              # the windowed EXE has no console, so the result is also written to FILE
"""
from __future__ import annotations

import sys


def _emit(text: str, out_path: str = "") -> None:
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    if sys.stdout is not None:
        try:
            print(text)
        except (OSError, ValueError):
            pass


def selftest() -> int:
    out_path = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--selftest-out=")), "")
    try:
        import ldap3  # noqa: F401
        import openpyxl  # noqa: F401

        import adtoolkit.ui.main_window  # noqa: F401 - verifies that the GUI modules are bundled
        from adtoolkit import __version__
        from adtoolkit.core.app_config import AppSettings
        from adtoolkit.ldap.demo_data import create_demo_gateway
        from adtoolkit.security.audit_log import OperationJournal
        from adtoolkit.services.audit_service import AuditService
        from adtoolkit.services.context import ServiceContext
        from adtoolkit.services.user_service import UserQuery, UserService, UserView
        from adtoolkit.storage.database import Database

        ctx = ServiceContext(create_demo_gateway(), AppSettings(), OperationJournal(Database(":memory:")))
        users = UserService(ctx).search(UserQuery(view=UserView.DISABLED))
        results = AuditService(ctx).run(["disabled_users", "privileged"])
        failed = [r.title for r in results if r.error]
        ok = bool(users.items) and not failed
        text = (f"AD Admin Toolkit {__version__}: self-test {'OK' if ok else 'FAILED'} — disabled users: "
                f"{len(users.items)}, audit checks: {len(results)}{'; failed: ' + ', '.join(failed) if failed else ''}")
    except Exception as exc:  # noqa: BLE001 - reported through the exit code
        ok, text = False, f"AD Admin Toolkit self-test FAILED: {type(exc).__name__}: {exc}"
    _emit(text, out_path)
    return 0 if ok else 1


def main() -> int:
    if "--version" in sys.argv:
        from adtoolkit import __version__
        _emit(__version__)
        return 0
    if "--selftest" in sys.argv:
        return selftest()
    from adtoolkit.ui.app import run
    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
