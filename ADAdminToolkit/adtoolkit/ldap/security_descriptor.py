"""Minimal parser of self-relative NT security descriptors (nTSecurityDescriptor).

Only what the toolkit needs is implemented: reading the DACL to detect the "User cannot change password" setting,
which in Active Directory is *not* stored in userAccountControl but expressed as DENY ACEs for the
"Change Password" extended right granted to Everyone / SELF.
"""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass

from .adtypes import sid_to_str

ACCESS_ALLOWED_ACE_TYPE = 0x00
ACCESS_DENIED_ACE_TYPE = 0x01
ACCESS_ALLOWED_OBJECT_ACE_TYPE = 0x05
ACCESS_DENIED_OBJECT_ACE_TYPE = 0x06

ACE_OBJECT_TYPE_PRESENT = 0x1
ACE_INHERITED_OBJECT_TYPE_PRESENT = 0x2
ADS_RIGHT_DS_CONTROL_ACCESS = 0x100

USER_CHANGE_PASSWORD_GUID = "ab721a53-1e2f-11d0-9819-00aa0040529b"
SID_EVERYONE = "S-1-1-0"
SID_SELF = "S-1-5-10"

# LDAP_SERVER_SD_FLAGS_OID value requesting only the DACL
SD_FLAGS_DACL = 0x04


@dataclass
class Ace:
    ace_type: int
    flags: int
    mask: int
    sid: str
    object_type: str | None = None
    inherited_object_type: str | None = None

    @property
    def is_deny(self) -> bool:
        return self.ace_type in (ACCESS_DENIED_ACE_TYPE, ACCESS_DENIED_OBJECT_ACE_TYPE)


@dataclass
class SecurityDescriptor:
    owner: str | None
    group: str | None
    dacl: list[Ace]


def _read_sid(data: bytes, offset: int) -> tuple[str, int]:
    count = data[offset + 1]
    length = 8 + 4 * count
    return sid_to_str(data[offset:offset + length]), length


def parse_security_descriptor(data: bytes) -> SecurityDescriptor:
    if not data or len(data) < 20:
        raise ValueError("Некорректный дескриптор безопасности")
    _rev, _sbz1, _control, off_owner, off_group, _off_sacl, off_dacl = struct.unpack_from("<BBHIIII", data, 0)
    owner = _read_sid(data, off_owner)[0] if off_owner else None
    group = _read_sid(data, off_group)[0] if off_group else None
    aces: list[Ace] = []
    if off_dacl:
        _acl_rev, _sbz, _acl_size, ace_count, _sbz2 = struct.unpack_from("<BBHHH", data, off_dacl)
        pos = off_dacl + 8
        for _ in range(ace_count):
            ace_type, ace_flags, ace_size = struct.unpack_from("<BBH", data, pos)
            body = pos + 4
            if ace_type in (ACCESS_ALLOWED_OBJECT_ACE_TYPE, ACCESS_DENIED_OBJECT_ACE_TYPE):
                mask, obj_flags = struct.unpack_from("<II", data, body)
                p = body + 8
                obj_type = inh_type = None
                if obj_flags & ACE_OBJECT_TYPE_PRESENT:
                    obj_type = str(uuid.UUID(bytes_le=bytes(data[p:p + 16])))
                    p += 16
                if obj_flags & ACE_INHERITED_OBJECT_TYPE_PRESENT:
                    inh_type = str(uuid.UUID(bytes_le=bytes(data[p:p + 16])))
                    p += 16
                sid, _ = _read_sid(data, p)
                aces.append(Ace(ace_type, ace_flags, mask, sid, obj_type, inh_type))
            elif ace_type in (ACCESS_ALLOWED_ACE_TYPE, ACCESS_DENIED_ACE_TYPE):
                (mask,) = struct.unpack_from("<I", data, body)
                sid, _ = _read_sid(data, body + 4)
                aces.append(Ace(ace_type, ace_flags, mask, sid))
            # other ACE types (audit, callback) are irrelevant for the DACL checks performed here
            if ace_size <= 0:
                break
            pos += ace_size
    return SecurityDescriptor(owner, group, aces)


def cannot_change_password(sd_bytes: bytes) -> tuple[bool, list[str]]:
    """Return (flag, trustees) — trustees for which 'Change Password' is explicitly denied."""
    sd = parse_security_descriptor(sd_bytes)
    who = []
    for ace in sd.dacl:
        if (ace.ace_type == ACCESS_DENIED_OBJECT_ACE_TYPE and ace.object_type == USER_CHANGE_PASSWORD_GUID
                and ace.mask & ADS_RIGHT_DS_CONTROL_ACCESS and ace.sid in (SID_EVERYONE, SID_SELF)):
            who.append("Все (Everyone)" if ace.sid == SID_EVERYONE else "SELF")
    return bool(who), who


def build_security_descriptor(aces: list[Ace], owner: str = "S-1-5-32-544") -> bytes:
    """Build a self-relative SD (used by the demo directory and tests)."""
    from .adtypes import str_to_sid

    ace_blobs = []
    for ace in aces:
        sid = str_to_sid(ace.sid)
        if ace.ace_type in (ACCESS_ALLOWED_OBJECT_ACE_TYPE, ACCESS_DENIED_OBJECT_ACE_TYPE):
            flags = 0
            extra = b""
            if ace.object_type:
                flags |= ACE_OBJECT_TYPE_PRESENT
                extra += uuid.UUID(ace.object_type).bytes_le
            if ace.inherited_object_type:
                flags |= ACE_INHERITED_OBJECT_TYPE_PRESENT
                extra += uuid.UUID(ace.inherited_object_type).bytes_le
            body = struct.pack("<II", ace.mask, flags) + extra + sid
        else:
            body = struct.pack("<I", ace.mask) + sid
        ace_blobs.append(struct.pack("<BBH", ace.ace_type, ace.flags, 4 + len(body)) + body)
    acl_body = b"".join(ace_blobs)
    acl = struct.pack("<BBHHH", 4, 0, 8 + len(acl_body), len(aces), 0) + acl_body
    owner_sid = str_to_sid(owner)
    header_len = 20
    off_owner = header_len
    off_dacl = off_owner + len(owner_sid)
    control = 0x8004  # SE_SELF_RELATIVE | SE_DACL_PRESENT
    header = struct.pack("<BBHIIII", 1, 0, control, off_owner, 0, 0, off_dacl)
    return header + owner_sid + acl


def deny_change_password_aces() -> list[Ace]:
    return [
        Ace(ACCESS_DENIED_OBJECT_ACE_TYPE, 0, ADS_RIGHT_DS_CONTROL_ACCESS, SID_EVERYONE, USER_CHANGE_PASSWORD_GUID),
        Ace(ACCESS_DENIED_OBJECT_ACE_TYPE, 0, ADS_RIGHT_DS_CONTROL_ACCESS, SID_SELF, USER_CHANGE_PASSWORD_GUID),
    ]
