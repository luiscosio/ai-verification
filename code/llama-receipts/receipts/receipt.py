"""Receipt document: canonical encoding, signing, and signature checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from receipts import keys


def canonical_bytes(obj: dict) -> bytes:
    """Deterministic JSON: sorted keys, no whitespace, no NaN."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def unsigned_view(receipt: dict) -> dict:
    return {k: v for k, v in receipt.items() if k != "signature"}


def receipt_digest(receipt: dict) -> str:
    return hashlib.sha256(canonical_bytes(unsigned_view(receipt))).hexdigest()


def sign_receipt(receipt: dict, key) -> dict:
    body = canonical_bytes(unsigned_view(receipt))
    receipt["signature"] = {
        "alg": "ed25519",
        "public_key": keys.public_hex(key),
        "sha256": hashlib.sha256(body).hexdigest(),
        "sig": keys.sign(key, body),
    }
    return receipt


def check_signature(receipt: dict) -> tuple[bool, str]:
    sig = receipt.get("signature")
    if not sig:
        return False, "no signature"
    body = canonical_bytes(unsigned_view(receipt))
    if hashlib.sha256(body).hexdigest() != sig.get("sha256"):
        return False, "receipt body does not match signed digest"
    if not keys.verify(sig.get("public_key", ""), sig.get("sig", ""), body):
        return False, "ed25519 signature invalid"
    return True, "ok"


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def save(receipt: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(receipt, indent=1, ensure_ascii=False))
