"""Comparison of two users (attributes and groups)."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.cancel import CancelToken
from ..ldap.adtypes import display_value
from ..ldap.dn import normalize_dn, rdn_value
from .common import get_or_fail
from .context import ServiceContext

COMPARE_ATTRIBUTES = ["displayName", "sAMAccountName", "userPrincipalName", "title", "department", "company",
                      "physicalDeliveryOfficeName", "manager", "mail", "telephoneNumber", "description", "employeeID",
                      "userAccountControl", "accountExpires", "pwdLastSet", "lastLogonTimestamp", "whenCreated",
                      "primaryGroupID", "adminCount", "l", "st", "streetAddress"]


@dataclass
class UserComparison:
    left_dn: str
    right_dn: str
    attributes: list[dict] = field(default_factory=list)      # {attribute, left, right, same}
    groups_only_left: list[str] = field(default_factory=list)
    groups_only_right: list[str] = field(default_factory=list)
    groups_both: list[str] = field(default_factory=list)
    transitive: bool = False


class CompareService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.gw = ctx.gateway

    def compare_users(self, left_dn: str, right_dn: str, *, transitive: bool = False,
                      cancel: CancelToken | None = None) -> UserComparison:
        left = get_or_fail(self.gw, left_dn, COMPARE_ATTRIBUTES + ["memberOf"])
        right = get_or_fail(self.gw, right_dn, COMPARE_ATTRIBUTES + ["memberOf"])
        res = UserComparison(left_dn, right_dn, transitive=transitive)
        for a in COMPARE_ATTRIBUTES:
            lv = "; ".join(display_value(a, v) for v in left.values(a))
            rv = "; ".join(display_value(a, v) for v in right.values(a))
            res.attributes.append({"attribute": a, "left": lv, "right": rv, "same": lv == rv})
        if transitive:
            from .group_service import GroupService
            gs = GroupService(self.ctx)
            lg = {normalize_dn(g.dn): g.name for g in gs.transitive_groups_of(left_dn, cancel)}
            rg = {normalize_dn(g.dn): g.name for g in gs.transitive_groups_of(right_dn, cancel)}
        else:
            lg = {normalize_dn(g): rdn_value(g) for g in left.values("memberOf")}
            rg = {normalize_dn(g): rdn_value(g) for g in right.values("memberOf")}
        res.groups_only_left = sorted((lg[k] for k in lg if k not in rg), key=str.casefold)
        res.groups_only_right = sorted((rg[k] for k in rg if k not in lg), key=str.casefold)
        res.groups_both = sorted((lg[k] for k in lg if k in rg), key=str.casefold)
        return res
