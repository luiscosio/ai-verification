"""Ed25519 signing for receipts."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

DEFAULT_KEY_PATH = Path.home() / ".config" / "llama-receipts" / "ed25519.key"


def generate_key(path: Path = DEFAULT_KEY_PATH) -> Ed25519PrivateKey:
    """Create a new private key at `path` (mode 0600) and return it."""
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = key.private_bytes_raw()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(raw.hex().encode())
    return key


def load_key(path: Path = DEFAULT_KEY_PATH, create: bool = True) -> Ed25519PrivateKey:
    if not path.exists():
        if not create:
            raise FileNotFoundError(path)
        return generate_key(path)
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(path.read_text().strip()))


def public_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes_raw().hex()


def sign(key: Ed25519PrivateKey, message: bytes) -> str:
    return key.sign(message).hex()


def verify(public_key_hex: str, signature_hex: str, message: bytes) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        pub.verify(bytes.fromhex(signature_hex), message)
        return True
    except (InvalidSignature, ValueError):
        return False
