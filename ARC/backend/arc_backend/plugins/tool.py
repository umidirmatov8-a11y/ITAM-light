"""Command-line tool for module authors.

    python -m arc_backend.plugins.tool keygen  --out my-key.pem        # prints the public key
    python -m arc_backend.plugins.tool check   manifest.json            # validates without signing
    python -m arc_backend.plugins.tool sign    manifest.json --key my-key.pem --out my-module.arcplugin
    python -m arc_backend.plugins.tool verify  my-module.arcplugin --public-key <base64>

The private key never leaves the author's computer; users add only the public key in A.R.C.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from .manager import PluginError, parse_file
from .manifest import PluginManifest
from .signing import key_id, public_key_b64, sign, verify


def _out(text: str) -> None:
    sys.stdout.buffer.write(text.encode("utf-8") + b"\n")


def _manifest(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    try:
        PluginManifest.model_validate(data)
    except ValidationError as exc:
        raise SystemExit(f"manifest is invalid:\n{exc}")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arc-plugin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("keygen")
    p.add_argument("--out", required=True)
    p = sub.add_parser("check")
    p.add_argument("manifest")
    p = sub.add_parser("sign")
    p.add_argument("manifest")
    p.add_argument("--key", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("verify")
    p.add_argument("file")
    p.add_argument("--public-key", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "keygen":
        out = Path(args.out)
        if out.exists():
            raise SystemExit(f"{out} already exists")
        private = Ed25519PrivateKey.generate()
        out.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
        public = public_key_b64(private)
        _out(json.dumps({"public_key": public, "key_id": key_id(public), "private_key_file": str(out)}, indent=2))
        return 0
    if args.cmd == "check":
        manifest = _manifest(args.manifest)
        _out(f"OK: {manifest['id']} {manifest['version']}")
        return 0
    if args.cmd == "sign":
        manifest = _manifest(args.manifest)
        private = serialization.load_pem_private_key(Path(args.key).read_bytes(), password=None)
        if not isinstance(private, Ed25519PrivateKey):
            raise SystemExit("the key is not an Ed25519 private key")
        doc = {"manifest": manifest, "signature": sign(manifest, private)}
        Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        _out(f"signed {args.out} with key {doc['signature']['key_id']}")
        return 0
    try:
        raw, signature = parse_file(Path(args.file).read_bytes())
    except PluginError as exc:
        raise SystemExit(str(exc))
    if signature is None:
        _out("NOT SIGNED")
        return 1
    ok = signature["key_id"] == key_id(args.public_key) and verify(raw, signature["ed25519"], args.public_key)
    _out("SIGNATURE OK" if ok else "SIGNATURE INVALID")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
