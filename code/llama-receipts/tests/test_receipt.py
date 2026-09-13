from pathlib import Path

from receipts import keys, receipt


def _key(tmp_path: Path):
    return keys.generate_key(tmp_path / "k.key")


def test_sign_and_verify_roundtrip(tmp_path):
    doc = {"a": 1, "b": [1, 2, 3], "text": "héllo"}
    receipt.sign_receipt(doc, _key(tmp_path))
    ok, reason = receipt.check_signature(doc)
    assert ok, reason


def test_tampered_body_fails(tmp_path):
    doc = {"tokens": [1, 2, 3]}
    receipt.sign_receipt(doc, _key(tmp_path))
    doc["tokens"][1] = 99
    ok, reason = receipt.check_signature(doc)
    assert not ok and "digest" in reason


def test_wrong_key_fails(tmp_path):
    doc = {"tokens": [1, 2, 3]}
    receipt.sign_receipt(doc, _key(tmp_path))
    other = keys.generate_key(tmp_path / "other.key")
    doc["signature"]["public_key"] = keys.public_hex(other)
    ok, reason = receipt.check_signature(doc)
    assert not ok and "invalid" in reason


def test_canonical_bytes_are_order_independent():
    a = receipt.canonical_bytes({"x": 1, "y": {"b": 2, "a": 1}})
    b = receipt.canonical_bytes({"y": {"a": 1, "b": 2}, "x": 1})
    assert a == b


def test_key_file_is_private(tmp_path):
    p = tmp_path / "k.key"
    keys.generate_key(p)
    assert (p.stat().st_mode & 0o777) == 0o600
    assert keys.load_key(p, create=False).public_key().public_bytes_raw()
