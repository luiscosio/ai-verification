"""Commit to a GGUF model: whole-file SHA-256 plus a Merkle root over tensors.

The Merkle root lets a later protocol open single tensors without shipping
the model. Results are cached by (path, size, mtime) because hashing a
multi-gigabyte file twice is slow.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from gguf import GGUFReader

from receipts.merkle import merkle_root
from receipts.receipt import canonical_bytes

CACHE_DIR = Path(".cache") / "model-commits"
META_KEYS = (
    "general.architecture",
    "general.name",
    "general.basename",
    "general.size_label",
    "general.file_type",
    "general.quantization_version",
)


def file_sha256(path: Path, chunk: int = 1 << 24) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def _field_value(field):
    """Read a scalar or string GGUF field across gguf-py versions."""
    if hasattr(field, "contents"):
        try:
            return field.contents()
        except Exception:  # noqa: BLE001 - fall through to the manual path
            pass
    part = field.parts[field.data[0]]
    if part.dtype == np.uint8:
        return bytes(part).decode("utf-8", "replace")
    return part.tolist()[0] if part.size == 1 else part.tolist()


def _file_type_name(file_type) -> str | None:
    """Map GGUF general.file_type (an int) to its name, e.g. 15 -> MOSTLY_Q4_K_M."""
    if file_type is None:
        return None
    try:
        from gguf import LlamaFileType

        return LlamaFileType(int(file_type)).name
    except (ImportError, ValueError):
        return str(file_type)


def _tensor_sha256(tensor) -> str:
    data = np.ascontiguousarray(tensor.data).view(np.uint8).ravel()
    return hashlib.sha256(data).hexdigest()


def _tensor_leaf(entry: dict) -> bytes:
    return canonical_bytes(entry)


def _cache_key(path: Path) -> Path:
    st = path.stat()
    tag = hashlib.sha256(f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:24]
    return CACHE_DIR / f"{tag}.json"


def gguf_commitment(path: str | Path, use_cache: bool = True) -> dict:
    """Describe and commit to the GGUF at `path`."""
    path = Path(path)
    cache = _cache_key(path)
    if use_cache and cache.exists():
        return json.loads(cache.read_text())

    reader = GGUFReader(str(path))
    meta = {}
    for key in META_KEYS:
        if key in reader.fields:
            value = _field_value(reader.fields[key])
            meta[key] = value.name if hasattr(value, "name") else value
    meta["file_type_name"] = _file_type_name(meta.get("general.file_type"))
    tensors = []
    for t in reader.tensors:
        tensors.append({
            "name": t.name,
            "type": t.tensor_type.name,
            "shape": [int(x) for x in t.shape],
            "n_bytes": int(t.n_bytes),
            "sha256": _tensor_sha256(t),
        })
    leaves = [_tensor_leaf(e) for e in tensors]
    out = {
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "file_sha256": file_sha256(path),
        "tensor_merkle_root": merkle_root(leaves).hex(),
        "n_tensors": len(tensors),
        "metadata": meta,
        "tensors": tensors,
    }
    if use_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out))
    return out


def summary(commit: dict) -> dict:
    """The part of a commitment that goes into a receipt (no tensor list)."""
    return {k: v for k, v in commit.items() if k != "tensors"}
