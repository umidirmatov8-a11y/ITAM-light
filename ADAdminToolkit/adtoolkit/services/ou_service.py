"""Organizational units: tree with object counts, contents, empty OUs, move-target validation, snapshots/compare."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..core.cancel import NULL_PROGRESS, CancelToken, Progress
from ..core.errors import ConflictError, ConstraintViolationError, ProtectedObjectError, ValidationError
from ..ldap.adtypes import utcnow
from ..ldap.dn import canonical_name, first_rdn, is_descendant, normalize_dn, parent_dn, rdn_value
from ..ldap.filters import Equals, Or
from ..ldap.gateway import Scope
from ..models.records import OUNode
from . import ad_queries as Q
from .common import ensure_conflict_free, get_or_fail, object_type_of, require_dn
from .context import ServiceContext

CONTAINER_CLASSES = {"organizationalunit": "organizationalUnit", "container": "container",
                     "builtindomain": "builtinDomain", "domaindns": "domain"}
SKIP_CONTAINERS = {"cn=system", "cn=program data", "cn=foreignsecurityprincipals", "cn=managed service accounts",
                   "cn=lostandfound", "cn=ntds quotas", "cn=keys", "cn=tpm devices", "cn=infrastructure",
                   "cn=configuration", "cn=schema"}


@dataclass
class OUSnapshot:
    domain: str
    created_at: str
    base_dn: str
    ous: dict[str, dict] = field(default_factory=dict)   # canonical path -> {dn, users, computers, groups, other, total}


@dataclass
class SnapshotDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[dict] = field(default_factory=list)


class OUService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.gw = ctx.gateway

    # ---------------------------------------------------------------------------------------------------------
    def tree(self, cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS, *,
             include_containers: bool = True, with_counts: bool = True) -> OUNode:
        base = self.ctx.base_dn
        progress(None, "Чтение структуры OU…")
        flt = Q.IS_CONTAINER_LIKE if include_containers else Q.IS_OU
        nodes: dict[str, OUNode] = {}
        root = OUNode(dn=base, name=self.gw.info.domain_dns or base, kind="domain")
        nodes[normalize_dn(base)] = root
        containers = []
        for e in self.gw.search(base, flt, ["objectClass", "description", "ou", "cn"], cancel=cancel):
            nd = normalize_dn(e.dn)
            if nd == normalize_dn(base):
                continue
            first = first_rdn(e.dn).lower()
            if any(first == s or is_descendant(e.dn, f"{s},{base}") for s in SKIP_CONTAINERS):
                continue
            kind = next((CONTAINER_CLASSES[c] for c in e.object_classes if c in CONTAINER_CLASSES), "container")
            nodes[nd] = OUNode(dn=e.dn, name=rdn_value(e.dn), kind=kind, description=e.str("description"))
            containers.append(e.dn)
        for dn in sorted(containers, key=lambda d: len(d)):
            node = nodes[normalize_dn(dn)]
            parent = nodes.get(normalize_dn(parent_dn(dn)))
            if parent is None:
                continue  # parent was skipped (system container)
            parent.children.append(node)
        for n in nodes.values():
            n.children.sort(key=lambda c: (c.kind != "organizationalUnit", c.name.casefold()))
        if with_counts:
            self._count_objects(nodes, cancel, progress)
        progress(100, "Структура OU прочитана")
        return root

    def _count_objects(self, nodes: dict[str, OUNode], cancel, progress) -> None:
        progress(None, "Подсчёт объектов в OU…")
        flt = Or(Q.IS_USER, Q.IS_COMPUTER, Q.IS_GROUP, Equals("objectClass", "contact"))
        for e in self.gw.search(self.ctx.base_dn, flt, ["objectClass"], cancel=cancel):
            parent = nodes.get(normalize_dn(parent_dn(e.dn)))
            if parent is None:
                continue
            t = object_type_of(e)
            if t == "user":
                parent.direct_users += 1
            elif t == "computer":
                parent.direct_computers += 1
            elif t == "group":
                parent.direct_groups += 1
            else:
                parent.direct_other += 1
        # also count nested non-leaf objects that are not OUs/containers we track (e.g. printQueue) as "other"

        def total(node: OUNode) -> int:
            node.total_objects = node.direct_total + sum(total(c) for c in node.children)
            return node.total_objects
        root = nodes[normalize_dn(self.ctx.base_dn)]
        total(root)

    def objects_in(self, ou_dn: str, subtree: bool = False, cancel: CancelToken | None = None) -> list[dict]:
        ou_dn = require_dn(ou_dn, "OU")
        rows = []
        scope = Scope.SUBTREE if subtree else Scope.ONELEVEL
        for e in self.gw.search(ou_dn, Or(Q.IS_USER, Q.IS_COMPUTER, Q.IS_GROUP, Equals("objectClass", "contact"),
                                          Q.IS_CONTAINER_LIKE),
                                ["objectClass", "cn", "displayName", "sAMAccountName", "description", "userAccountControl",
                                 "whenCreated"], scope, cancel=cancel):
            if normalize_dn(e.dn) == normalize_dn(ou_dn):
                continue
            uac = e.int("userAccountControl")
            rows.append({"dn": e.dn, "name": e.str("displayName") or e.str("cn") or rdn_value(e.dn),
                         "type": object_type_of(e), "sam": e.str("sAMAccountName"), "description": e.str("description"),
                         "enabled": None if uac is None else not bool(uac & 2), "created": e.first("whenCreated")})
        return sorted(rows, key=lambda r: (r["type"] not in ("organizationalUnit", "container"), r["name"].casefold()))

    def empty_ous(self, cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> list[OUNode]:
        root = self.tree(cancel, progress)
        out = []
        for node in root.walk():
            if node.kind == "organizationalUnit" and node.is_empty:
                # make sure nothing else (printers, contacts, custom classes) lives there
                children = self.gw.search_list(node.dn, "(objectClass=*)", ["1.1"], Scope.ONELEVEL, size_limit=1)
                if not children:
                    out.append(node)
        return out

    def is_protected(self, dn: str) -> bool | None:
        """ProtectedFromAccidentalDeletion = DENY Delete/DeleteTree for Everyone in the DACL."""
        from ..ldap.security_descriptor import SD_FLAGS_DACL, SID_EVERYONE, parse_security_descriptor
        e = self.gw.get(dn, ["nTSecurityDescriptor"], sd_flags=SD_FLAGS_DACL)
        raw = e.first("nTSecurityDescriptor") if e else None
        if not raw:
            return None
        try:
            sd = parse_security_descriptor(raw)
        except ValueError:
            return None
        return any(a.is_deny and a.sid == SID_EVERYONE and a.mask & 0x10040 for a in sd.dacl)

    # ---------------------------------------------------------------------------------------------------------
    def validate_move_target(self, object_dn: str, target_dn: str, object_class: str) -> None:
        """Checks before any move: target exists, is a container, is not the current parent, name is free, rights."""
        object_dn, target_dn = require_dn(object_dn, "DN объекта"), require_dn(target_dn, "DN целевого OU")
        self.gw._guard_write()
        get_or_fail(self.gw, object_dn, ["objectClass"])
        target = self.gw.get(target_dn, ["objectClass"])
        if target is None:
            raise ValidationError(f"Целевой контейнер не существует: {target_dn}")
        if not any(c in CONTAINER_CLASSES for c in target.object_classes):
            raise ValidationError("Целевой объект не является OU или контейнером")
        if normalize_dn(parent_dn(object_dn)) == normalize_dn(target_dn):
            raise ValidationError("Объект уже находится в выбранном контейнере")
        if is_descendant(target_dn, object_dn, include_self=True):
            raise ValidationError("Нельзя переместить объект внутрь самого себя")
        ensure_conflict_free(self.gw, target_dn, first_rdn(object_dn))
        self.ctx.permissions.require_create(target_dn, object_class, "Перемещение объекта")

    def delete_empty_ou(self, ou_dn: str, *, confirmed_name: str) -> None:
        """Delete an OU only when it is empty and the user typed its exact name (separate confirmation)."""
        ou_dn = require_dn(ou_dn, "OU")
        with self.ctx.journal.track("ou.delete", ou_dn):
            self.gw._guard_write()
            e = get_or_fail(self.gw, ou_dn, ["objectClass"])
            if "organizationalunit" not in e.object_classes:
                raise ValidationError("Удалять через приложение можно только OU")
            if confirmed_name != rdn_value(ou_dn):
                raise ValidationError("Подтверждение не совпадает с именем OU")
            if self.gw.search_list(ou_dn, "(objectClass=*)", ["1.1"], Scope.ONELEVEL, size_limit=1):
                raise ConstraintViolationError("OU не пустое — удаление запрещено (массовое удаление не поддерживается)")
            if self.is_protected(ou_dn):
                raise ProtectedObjectError("OU защищено от случайного удаления",
                                           hint="Снимите флаг «Protect object from accidental deletion» в ADUC, если удаление необходимо.")
            self.gw.delete(ou_dn)

    def create_ou(self, parent: str, name: str, description: str = "") -> str:
        from ..ldap.dn import child_dn
        name = (name or "").strip()
        if not name:
            raise ValidationError("Не задано имя OU")
        dn = child_dn(require_dn(parent, "родительский контейнер"), "OU", name)
        with self.ctx.journal.track("ou.create", dn):
            self.gw._guard_write()
            if self.gw.get(dn, ["1.1"]) is not None:
                raise ConflictError("OU с таким именем уже существует")
            self.ctx.permissions.require_create(parent, "organizationalUnit", "Создание OU")
            self.gw.add(dn, ["top", "organizationalUnit"], {"ou": name, "description": description.strip() or None})
        return dn

    # ---------------------------------------------------------------------------------------------------------
    # Snapshots (export structure, compare before/after)
    # ---------------------------------------------------------------------------------------------------------
    def snapshot(self, cancel: CancelToken | None = None, progress: Progress = NULL_PROGRESS) -> OUSnapshot:
        root = self.tree(cancel, progress)
        snap = OUSnapshot(domain=self.gw.info.domain_dns, created_at=utcnow().isoformat(timespec="seconds"),
                          base_dn=self.ctx.base_dn)
        for n in root.walk():
            snap.ous[canonical_name(n.dn)] = {"dn": n.dn, "kind": n.kind, "users": n.direct_users,
                                              "computers": n.direct_computers, "groups": n.direct_groups,
                                              "other": n.direct_other, "total": n.total_objects}
        return snap

    @staticmethod
    def save_snapshot(snap: OUSnapshot, path: str | Path) -> None:
        path = Path(path)
        if path.suffix.lower() == ".csv":
            with path.open("w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(["# snapshot", snap.domain, snap.created_at, snap.base_dn])
                w.writerow(["path", "dn", "kind", "users", "computers", "groups", "other", "total"])
                for p, d in sorted(snap.ous.items()):
                    w.writerow([p, d["dn"], d["kind"], d["users"], d["computers"], d["groups"], d["other"], d["total"]])
        else:
            path.write_text(json.dumps({"format": "adtoolkit-ou-snapshot/1", "domain": snap.domain,
                                        "created_at": snap.created_at, "base_dn": snap.base_dn, "ous": snap.ous},
                                       ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def load_snapshot(path: str | Path) -> OUSnapshot:
        path = Path(path)
        try:
            if path.suffix.lower() == ".csv":
                with path.open(encoding="utf-8-sig", newline="") as fh:
                    rows = list(csv.reader(fh))
                if not rows or rows[0][:1] != ["# snapshot"]:
                    raise ValidationError("Файл не является снимком структуры OU (CSV)")
                head = rows[0]
                snap = OUSnapshot(domain=head[1], created_at=head[2], base_dn=head[3])
                for r in rows[2:]:
                    if len(r) >= 8:
                        snap.ous[r[0]] = {"dn": r[1], "kind": r[2], "users": int(r[3]), "computers": int(r[4]),
                                          "groups": int(r[5]), "other": int(r[6]), "total": int(r[7])}
                return snap
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, IndexError) as exc:
            raise ValidationError(f"Не удалось прочитать снимок: {path.name}", details=str(exc)) from None
        if data.get("format") != "adtoolkit-ou-snapshot/1":
            raise ValidationError("Файл не является снимком структуры OU AD Admin Toolkit")
        return OUSnapshot(domain=data["domain"], created_at=data["created_at"], base_dn=data["base_dn"], ous=data["ous"])

    @staticmethod
    def compare_snapshots(before: OUSnapshot, after: OUSnapshot) -> SnapshotDiff:
        diff = SnapshotDiff()
        diff.added = sorted(set(after.ous) - set(before.ous))
        diff.removed = sorted(set(before.ous) - set(after.ous))
        for path in sorted(set(before.ous) & set(after.ous)):
            b, a = before.ous[path], after.ous[path]
            changes = {k: (b.get(k), a.get(k)) for k in ("users", "computers", "groups", "other", "total") if b.get(k) != a.get(k)}
            if changes:
                diff.changed.append({"path": path, **{k: f"{v[0]} → {v[1]}" for k, v in changes.items()}})
        return diff


def snapshot_time(snap: OUSnapshot) -> datetime | None:
    try:
        return datetime.fromisoformat(snap.created_at)
    except ValueError:
        return None
