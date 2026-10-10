"""Main window pages."""
from __future__ import annotations


def create_pages(win) -> dict:
    from .audit_page import AuditPage
    from .bulk_page import BulkPage
    from .computers_page import ComputersPage
    from .dashboard_page import DashboardPage
    from .events_page import EventsPage
    from .explorer_page import ExplorerPage
    from .groups_page import GroupsPage
    from .misc_pages import OperationLogPage, ReportsPage, SearchPage, SettingsPage
    from .ou_page import OUPage
    from .tools_page import ToolsPage
    from .users_page import UsersPage

    return {
        "dashboard": DashboardPage(win),
        "users": UsersPage(win),
        "computers": ComputersPage(win),
        "groups": GroupsPage(win),
        "ous": OUPage(win),
        "audit": AuditPage(win),
        "events": EventsPage(win),
        "bulk": BulkPage(win),
        "explorer": ExplorerPage(win),
        "tools": ToolsPage(win),
        "reports": ReportsPage(win),
        "oplog": OperationLogPage(win),
        "settings": SettingsPage(win),
        "search": SearchPage(win),
    }
