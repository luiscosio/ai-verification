"""Merkle-committed activation trace of a llama.cpp forward pass (rung 4).

The tracer sits on `cb_eval`. For every node that computes something (layout
ops are resolved to the tensor they view) it records a leaf:

    graph index, node index, name, op, op params,
    out:  type, shape, strides, offset into its base tensor, base {shape, nbytes, sha256}
    srcs: weight -> name plus the GGUF tensor hash from the model commitment
          data   -> same as out, plus `producer`: the leaf that last wrote the base
                    (-1: graph input such as tokens, positions or the mask;
                     -2: persistent state before its first write, i.e. the zeroed KV cache)

Leaves are hashed into one Merkle tree over the whole generation. The root goes
into the signed receipt. Openings for sampled leaves carry the raw bytes of the
output and of every data input, so a verifier can re-execute the op.

Design notes. Bytes are read at `ask` time for inputs and after compute for
outputs, which handles in-place ops such as SET_ROWS. A `last_write` map from
base data pointer to (hash, leaf) makes repeated reads of the KV cache free and
gives exact producer links; it is pruned to persistent tensors between graphs
because the allocator reuses compute memory. Graph inputs and the scheduler's
backend copies are always read and linked by hash equality.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from receipts import ggml
from receipts.merkle import merkle_proofs, merkle_root, verify_proof
from receipts.receipt import canonical_bytes

TRACE_VERSION = "trace/v2"
CHALLENGE_DOMAIN = b"llama-receipts/trace-challenge/v1/"
PRODUCER_INPUT = -1
PRODUCER_INITIAL = -2
PERSISTENT_PREFIXES = ("cache_",)


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def topology_sha256(leaves: list[dict]) -> str:
    """Digest graph structure while excluding runtime tensor contents."""
    def strip_hashes(value):
        if isinstance(value, dict):
            return {k: strip_hashes(v) for k, v in value.items() if k != "sha256"}
        if isinstance(value, list):
            return [strip_hashes(v) for v in value]
        return value

    return _sha256(canonical_bytes(strip_hashes(leaves)))


@dataclass
class _Write:
    sha256: str
    leaf: int
    nbytes: int


@dataclass
class TraceStats:
    graphs: int = 0
    nodes: int = 0
    layout_skipped: int = 0
    bytes_hashed: int = 0
    reads: int = 0
    cache_hits: int = 0
    unlinked_node_srcs: int = 0
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return {**self.__dict__, "seconds": round(self.seconds, 3)}


class Tracer:
    """Collects leaves through `cb_eval`. One instance per engine; call `reset()` per generation."""

    def __init__(self, weight_hashes: dict[str, str], capture: set[int] | None = None):
        self.weight_hashes = weight_hashes
        self.capture = capture
        self.reset()

    # --- lifecycle --------------------------------------------------------
    def reset(self, capture: set[int] | None = None) -> None:
        self.leaves: list[dict] = []
        self.leaf_bytes: list[bytes] = []
        self.captured: dict[int, dict] = {}
        self.errors: list[str] = []
        self.stats = TraceStats()
        self.enabled = True
        self.graph = -1
        self.node_in_graph = 0
        self._last_write: dict[int, _Write] = {}
        self._by_hash: dict[str, int] = {}
        self._pending: list[dict] | None = None
        self._pending_bytes: list[bytes | None] | None = None
        self._persistent_ptrs: set[int] = set()
        self._checked_layout = False
        if capture is not None:
            self.capture = capture

    def begin_graph(self) -> None:
        self.graph += 1
        self.node_in_graph = 0
        self.stats.graphs += 1
        # Compute memory is reused between graphs; only the KV cache carries state across.
        self._last_write = {k: v for k, v in self._last_write.items() if k in self._persistent_ptrs}
        self._by_hash = {}

    # --- callback ---------------------------------------------------------
    def callback(self, ptr: int, ask: bool) -> bool:
        if not self.enabled:
            return not ask  # decline to observe; never abort
        t0 = time.perf_counter()
        try:
            t = ggml.info(ptr)
            if t.is_layout:
                if ask:
                    self.stats.layout_skipped += 1
                return not ask
            if ask:
                self._pending, self._pending_bytes = self._collect_srcs(t)
                return True
            self._record(t)
            return True
        except Exception as e:  # noqa: BLE001 - never let an exception cross the C boundary
            self.errors.append(f"graph {self.graph} node {self.node_in_graph}: {e!r}")
            return True
        finally:
            self.stats.seconds += time.perf_counter() - t0

    # --- helpers ----------------------------------------------------------
    def _is_persistent(self, name: str) -> bool:
        return name.startswith(PERSISTENT_PREFIXES)

    def _capturing(self) -> bool:
        return self.capture is not None and len(self.leaves) in self.capture

    def _read(self, ptr: int, nbytes: int) -> bytes:
        self.stats.reads += 1
        self.stats.bytes_hashed += nbytes
        return ggml.read_bytes(ptr, nbytes)

    def _collect_srcs(self, t: ggml.TensorInfo) -> tuple[list[dict], list[bytes | None]]:
        capturing = self._capturing()
        entries: list[dict] = []
        blobs: list[bytes | None] = []
        for sp in t.srcs:
            s = ggml.info(sp)
            bp = ggml.base_of(sp)
            b = ggml.info(bp)
            offset = s.data - b.data
            common = {"name": s.name, "type": s.type, "ne": s.ne, "nb": s.nb, "offset": offset}
            base = {"name": b.name, "type": b.type, "ne": b.ne, "nb": b.nb, "nbytes": b.nbytes}
            persistent = self._is_persistent(b.name)
            if b.is_leaf and not persistent and b.name in self.weight_hashes:
                entries.append({"kind": "weight", **common, "sha256": self.weight_hashes[b.name], "base": base})
                blobs.append(None)
                continue
            blob = None
            lw = self._last_write.get(b.data)
            if lw is not None and lw.nbytes == b.nbytes and (persistent or not b.is_leaf):
                h, producer = lw.sha256, lw.leaf
                self.stats.cache_hits += 1
                if capturing:
                    blob = self._read(bp, b.nbytes)
            else:
                blob = self._read(bp, b.nbytes)
                h = _sha256(blob)
                if persistent:
                    producer = PRODUCER_INITIAL
                    self._persistent_ptrs.add(b.data)
                    self._last_write[b.data] = _Write(h, producer, b.nbytes)
                elif b.is_leaf:
                    producer = self._by_hash.get(h, PRODUCER_INPUT)
                else:
                    producer = self._by_hash.get(h, PRODUCER_INPUT)
                    self.stats.unlinked_node_srcs += 1
            entries.append({"kind": "data", **common, "base": {**base, "sha256": h}, "producer": producer})
            blobs.append(blob if capturing else None)
        return entries, blobs

    def _record(self, t: ggml.TensorInfo) -> None:
        if not self._checked_layout:
            ggml.check_layout(t.ptr)
            self._checked_layout = True
        bp = ggml.base_of(t.ptr)
        b = ggml.info(bp)
        blob = self._read(bp, b.nbytes)
        h = _sha256(blob)
        idx = len(self.leaves)
        leaf = {
            "v": 1,
            "g": self.graph,
            "i": self.node_in_graph,
            "name": t.name,
            "op": t.op,
            "op_name": t.op_name,
            "params": t.op_params.rstrip(b"\0").hex(),
            "out": {
                "type": t.type, "ne": t.ne, "nb": t.nb, "offset": t.data - b.data,
                "base": {"name": b.name, "type": b.type, "ne": b.ne, "nb": b.nb, "nbytes": b.nbytes, "sha256": h},
            },
            "srcs": self._pending or [],
        }
        self.leaves.append(leaf)
        self.leaf_bytes.append(canonical_bytes(leaf))
        self._last_write[b.data] = _Write(h, idx, b.nbytes)
        if self._is_persistent(b.name):
            self._persistent_ptrs.add(b.data)
        self._by_hash[h] = idx
        if self.capture is not None and idx in self.capture:
            self.captured[idx] = {"out": blob, "srcs": self._pending_bytes or []}
        self._pending, self._pending_bytes = None, None
        self.node_in_graph += 1
        self.stats.nodes += 1

    # --- results ----------------------------------------------------------
    def root(self) -> str:
        return merkle_root(self.leaf_bytes).hex()

    def summary(self) -> dict:
        """What goes into the signed receipt."""
        return {
            "version": TRACE_VERSION,
            "root": self.root(),
            "n_leaves": len(self.leaves),
            "n_graphs": self.graph + 1,
            "topology_sha256": topology_sha256(self.leaves),
            "leaf_hash": "sha256(0x00 || canonical_json(leaf))",
            "layout_ops_resolved": sorted(ggml.LAYOUT_OPS - {"NONE"}),
            "stats": self.stats.to_dict(),
        }


# --- challenge and openings -------------------------------------------------

def derive_indices(root_hex: str, binding: bytes, n_leaves: int, k: int, seed: bytes = b"") -> list[int]:
    """Fiat-Shamir sample of k distinct leaf indices from the committed root.

    `binding` ties the challenge to the receipt (token commitment and model hash);
    `seed` lets an interactive verifier supply its own randomness instead.
    """
    if n_leaves <= 0:
        return []
    k = min(k, n_leaves)
    out: list[int] = []
    seen: set[int] = set()
    counter = 0
    while len(out) < k:
        msg = CHALLENGE_DOMAIN + bytes.fromhex(root_hex) + binding + seed + counter.to_bytes(8, "big")
        idx = int.from_bytes(hashlib.sha256(msg).digest()[:8], "big") % n_leaves
        counter += 1
        if idx not in seen:
            seen.add(idx)
            out.append(idx)
    return sorted(out)


def challenge_binding(receipt: dict) -> bytes:
    return (bytes.fromhex(receipt["commitments"]["tokens_sha256"])
            + bytes.fromhex(receipt["commitments"]["content_sha256"])
            + bytes.fromhex(receipt["model"]["file_sha256"]))


def _enc(b: bytes | None) -> str | None:
    return None if b is None else base64.b64encode(zlib.compress(b, 6)).decode()


def _dec(s: str | None) -> bytes | None:
    return None if s is None else zlib.decompress(base64.b64decode(s))


def build_openings(tracer: Tracer, indices: list[int]) -> list[dict]:
    """Openings for `indices` from a tracer that captured them (pass two)."""
    out = []
    paths = merkle_proofs(tracer.leaf_bytes, indices)
    for idx in indices:
        cap = tracer.captured.get(idx)
        if cap is None:
            raise KeyError(f"leaf {idx} was not captured")
        path = [[side, sib.hex()] for side, sib in paths[idx]]
        out.append({"index": idx, "path": path, "out": _enc(cap["out"]), "srcs": [_enc(x) for x in cap["srcs"]]})
    return out


def open_bytes(opening: dict) -> tuple[bytes, list[bytes | None]]:
    return _dec(opening["out"]), [_dec(x) for x in opening["srcs"]]


def check_opening_path(leaves_bytes: list[bytes] | None, leaf: dict, opening: dict, root_hex: str) -> bool:
    path = [(side, bytes.fromhex(h)) for side, h in opening["path"]]
    return verify_proof(canonical_bytes(leaf), path, bytes.fromhex(root_hex))


@dataclass
class TraceDoc:
    """The sidecar next to a receipt: every leaf, plus openings for the challenge."""

    root: str
    n_graphs: int
    leaves: list[dict]
    openings: list[dict]
    challenge: dict
    topology_sha256: str = ""
    version: str = TRACE_VERSION
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"version": self.version, "root": self.root, "n_graphs": self.n_graphs, "topology_sha256": self.topology_sha256,
                "challenge": self.challenge,
                "stats": self.stats, "leaves": self.leaves, "openings": self.openings}

    @classmethod
    def from_dict(cls, d: dict) -> TraceDoc:
        return cls(root=d["root"], n_graphs=d["n_graphs"], leaves=d["leaves"], openings=d["openings"],
                   challenge=d["challenge"], topology_sha256=d.get("topology_sha256", ""),
                   version=d.get("version", TRACE_VERSION), stats=d.get("stats", {}))


def sidecar_path(receipt_path: str | Path) -> Path:
    p = Path(receipt_path)
    name = p.name[:-5] if p.name.endswith(".json") else p.name
    return p.with_name(name + ".trace.json.gz")


def save_trace(doc: TraceDoc, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(doc.to_dict(), f, separators=(",", ":"))


def load_trace(path: str | Path) -> TraceDoc:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return TraceDoc.from_dict(json.load(f))
