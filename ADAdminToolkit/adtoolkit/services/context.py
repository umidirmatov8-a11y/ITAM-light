"""Service context: everything a service needs for one connected session."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.app_config import AppSettings
from ..core.errors import NotConnectedError
from ..ldap.gateway import DirectoryGateway
from ..security.audit_log import OperationJournal
from ..security.permissions import PermissionChecker, PrivilegedGroupRegistry


@dataclass
class ServiceContext:
    gateway: DirectoryGateway
    settings: AppSettings
    journal: OperationJournal
    privileged: PrivilegedGroupRegistry = field(init=False)
    permissions: PermissionChecker = field(init=False)

    def __post_init__(self):
        self.privileged = PrivilegedGroupRegistry(self.gateway, self.settings.extra_privileged_groups)
        self.permissions = PermissionChecker(self.gateway)
        info = self.gateway.info
        self.journal.set_context(ldap_identity=info.bound_identity, domain=info.domain_dns, dc=info.dc_host)

    @property
    def base_dn(self) -> str:
        if not self.gateway.connected:
            raise NotConnectedError()
        return self.gateway.info.base_dn

    @property
    def policy(self):
        return self.gateway.info.policy
