"""Ed25519 signatures of module manifests.

The signed bytes are the canonical JSON of the manifest (sorted keys, no spaces, UTF-8), so the
signature does not depend on formatting of the .arcplugin file."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical(manifest: dict[str, Any]) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _b64(value: str, size: int | None = None) -> bytes:
    try:
        raw = base64.b64decode(value.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("invalid base64")
    if size is not None and len(raw) != size:
        raise ValueError(f"expected {size} bytes")
    return raw


def load_public_key(value: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_b64(value, 32))


def key_id(public_key_b64: str) -> str:
    return hashlib.sha256(_b64(public_key_b64, 32)).hexdigest()[:16]


def public_key_b64(private: Ed25519PrivateKey) -> str:
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def sign(manifest: dict[str, Any], private: Ed25519PrivateKey) -> dict[str, str]:
    public = public_key_b64(private)
    return {"key_id": key_id(public), "ed25519": base64.b64encode(private.sign(canonical(manifest))).decode("ascii")}


def verify(manifest: dict[str, Any], signature_b64: str, public_key: str) -> bool:
    try:
        load_public_key(public_key).verify(_b64(signature_b64, 64), canonical(manifest))
        return True
    except (InvalidSignature, ValueError):
        return False
