"""Verify a trace sidecar against a signed receipt, without running the model.

Checks, cheapest first:
1. the leaves hash to the root the receipt signed, and the leaf count and graph
   count match;
2. the openings are exactly the Fiat-Shamir sample the root and receipt imply;
3. the graph count fits the token sequence, every graph's token and position
   inputs hash to what the claimed prompt and response say, and the output-row
   selection is the full batch;
4. every data edge is consistent: each input's base hash equals the output hash
   of the leaf recorded as its producer, and the KV cache starts as zeros;
5. each decode graph's final logits hash equals the per-token logits hash in the
   receipt, so the trace and the sampler evidence describe the same run;
6. each opening sits in the tree, its bytes hash to the leaf, its weight inputs
   match the verifier's own GGUF commitment, and re-executing the op in numpy
   reproduces the output within the op's tolerance.

What this does not give: a cheat confined to one node is caught only if that
node is sampled, and the verifier still holds the weights.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np
from gguf import GGUFReader, quants

from receipts import RECEIPT_VERSION
from receipts.trace import TRACE_VERSION
from receipts import ops
from receipts.merkle import merkle_root
from receipts.model_commit import gguf_commitment
from receipts.receipt import canonical_bytes
from receipts.trace import (
    PRODUCER_INITIAL,
    PRODUCER_INPUT,
    TraceDoc,
    challenge_binding,
    check_opening_path,
    derive_indices,
    open_bytes,
    topology_sha256,
)

BIG_MATMUL_ROWS = 16384  # weights with more output rows than this are checked on a row sample
ROWS_CHECKED = 2048
HARD_INPUTS = ("tokens", "positions", "out_ids")
SOFT_INPUTS = ("k_cells", "v_cells", "mask")


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class WeightStore:
    """Rows of GGUF tensors as float32, dequantized on demand and cached whole."""

    def __init__(self, model_path: str | Path):
        self.reader = GGUFReader(str(model_path))
        self.tensors = {t.name: t for t in self.reader.tensors}
        self._full: dict[str, np.ndarray] = {}

    def has(self, name: str) -> bool:
        return name in self.tensors

    def ne(self, name: str) -> list[int]:
        return [int(x) for x in self.tensors[name].shape]

    def type_name(self, name: str) -> str:
        return self.tensors[name].tensor_type.name

    def rows(self, name: str, rows: np.ndarray | None = None) -> np.ndarray:
        """(R, ne0) float32, or (len(rows), ne0) for a row subset."""
        t = self.tensors[name]
        ne0 = int(t.shape[0])
        if t.tensor_type.name in ("F32", "F16", "BF16", "F64"):
            arr = np.asarray(t.data)
            if t.tensor_type.name == "BF16" and arr.dtype != np.float32:
                arr = (arr.view(np.uint16).astype(np.uint32) << 16).view(np.float32)
            full = arr.reshape(-1, ne0).astype(np.float32, copy=False)
            return full if rows is None else full[rows]
        blocks = np.asarray(t.data).reshape(-1, np.asarray(t.data).shape[-1])
        if rows is not None:
            return quants.dequantize(blocks[rows], t.tensor_type).reshape(-1, ne0).astype(np.float32)
        if name not in self._full:
            if len(self._full) >= 6:
                self._full.pop(next(iter(self._full)))
            self._full[name] = quants.dequantize(blocks, t.tensor_type).reshape(-1, ne0).astype(np.float32)
        return self._full[name]

    def blocks(self, name: str, rows: np.ndarray | None = None) -> np.ndarray | None:
        """Raw quantized rows (R, bytes_per_row) uint8, or None for float tensors."""
        t = self.tensors[name]
        if t.tensor_type.name in ("F32", "F16", "BF16", "F64"):
            return None
        data = np.asarray(t.data).reshape(-1, np.asarray(t.data).shape[-1])
        return data if rows is None else data[rows]

    def array4d(self, name: str, rows: np.ndarray | None = None) -> np.ndarray:
        ne = self.ne(name) + [1] * (4 - len(self.ne(name)))
        data = self.rows(name, rows)
        if rows is not None:
            return data.reshape(1, 1, len(rows), ne[0])
        return data.reshape(tuple(reversed(ne)))


# --- expected graph inputs -------------------------------------------------------------

def graph_tokens(rec: dict, g: int) -> list[int] | None:
    prompt = rec["request"]["prompt_tokens"]
    resp = rec["response"]["tokens"]
    if g == 0:
        return list(prompt)
    if 1 <= g <= len(resp):
        return [resp[g - 1]]
    return None


def graph_start(rec: dict, g: int) -> int:
    return 0 if g == 0 else len(rec["request"]["prompt_tokens"]) + (g - 1)


def expected_input(kind: str, rec: dict, g: int, leaf: dict, src: dict) -> bytes | None:
    toks = graph_tokens(rec, g)
    if toks is None:
        return None
    n, start = len(toks), graph_start(rec, g)
    if kind == "tokens":
        return np.asarray(toks, dtype=np.int32).tobytes()
    if kind == "positions":
        return np.arange(start, start + n, dtype=np.int32).tobytes()
    if kind == "out_ids":
        return np.arange(n, dtype=np.int32).tobytes()
    if kind == "k_cells":
        return np.arange(start, start + n, dtype=np.int64).tobytes()
    if kind == "v_cells":
        # transposed V cache: element (token t, dim e) lands at e * kv_size + cell(t)
        dst = leaf["srcs"][2]["base"]
        kv_size, n_embd_v = dst["ne"][1], dst["ne"][0]
        e = np.arange(n_embd_v, dtype=np.int64)
        cells = np.arange(start, start + n, dtype=np.int64)
        return (cells[:, None] + e[None, :] * kv_size).reshape(-1).tobytes()
    if kind == "mask":
        n_kv = src["ne"][0]
        rows = src["ne"][1]
        m = np.full((rows, n_kv), -np.inf, dtype=np.float32)
        for t in range(min(n, rows)):
            m[t, : start + t + 1] = 0.0
        if src["type"] == "f16":
            m = m.astype(np.float16)
        return m.tobytes()
    return None


def classify_input(leaf: dict, i: int, src: dict) -> str | None:
    op = leaf["op"]
    if op == "GET_ROWS" and i == 1:
        return "tokens" if leaf["srcs"][0].get("kind") == "weight" else "out_ids"
    if op == "ROPE" and i == 1:
        return "positions"
    if op == "SET_ROWS" and i == 1:
        return "v_cells" if leaf["srcs"][2]["base"]["name"].startswith("cache_v") else "k_cells"
    if op == "SOFT_MAX" and i == 1:
        return "mask"
    return None


# --- the verifier ----------------------------------------------------------------------

def verify_trace(rec: dict, tdoc: TraceDoc, model_path: str | Path, tol: ops.Tolerances | None = None,
                 challenge_seed: bytes = b"", commitment: dict | None = None,
                 expected_topology_sha256: str | None = None, min_openings: int = 32) -> dict:
    t0 = time.time()
    tol = tol or ops.Tolerances()
    checks: dict[str, dict] = {}
    hard_fail: list[str] = []

    def check(name: str, ok: bool, detail: str = "", hard: bool = True, **extra) -> None:
        checks[name] = {"ok": bool(ok), "detail": detail, **extra}
        if hard and not ok:
            hard_fail.append(f"{name}: {detail}" if detail else name)

    tr = rec.get("trace")
    if not tr:
        return {"verdict": "reject", "reason": "receipt carries no trace commitment", "checks": checks}
    versions = (rec.get("receipt_version"), tr.get("version"), tdoc.version)
    check("version", versions == (RECEIPT_VERSION, TRACE_VERSION, TRACE_VERSION),
          f"receipt {versions[0]}, trace {versions[1]} and {versions[2]}; this verifier reads receipt {RECEIPT_VERSION} with {TRACE_VERSION}")
    if hard_fail:
        return {"verdict": "reject", "reason": hard_fail[0], "checks": checks}
    leaves = tdoc.leaves
    leaf_bytes = [canonical_bytes(x) for x in leaves]
    root = merkle_root(leaf_bytes).hex()
    n_graphs = (max((x["g"] for x in leaves), default=-1) + 1) if leaves else 0
    check("root", root == tr["root"] == tdoc.root and len(leaves) == tr["n_leaves"] and n_graphs == tr["n_graphs"],
          f"recomputed {root[:16]} vs signed {tr['root'][:16]}; {len(leaves)} leaves, {n_graphs} graphs")
    topology = topology_sha256(leaves)
    check("topology", expected_topology_sha256 is not None and topology == tr.get("topology_sha256") == tdoc.topology_sha256 == expected_topology_sha256,
          "verifier topology policy missing" if expected_topology_sha256 is None else
          f"recomputed {topology[:16]} vs expected {expected_topology_sha256[:16]}")

    prompt = rec["request"]["prompt_tokens"]
    resp = rec["response"]["tokens"]
    token_commitment = _sha256(canonical_bytes({"prompt": prompt, "response": resp}))
    content_commitment = _sha256(canonical_bytes({"prompt_text": rec["request"]["prompt_text"], "response_text": rec["response"]["text"]}))
    check("content_commitments", token_commitment == rec["commitments"].get("tokens_sha256") and
          content_commitment == rec["commitments"].get("content_sha256"), "token and human-readable receipt content")

    # challenge
    k = int(tdoc.challenge.get("k", len(tdoc.openings)))
    seed = bytes.fromhex(tdoc.challenge.get("seed", "")) or challenge_seed
    expected_idx = derive_indices(tr["root"], challenge_binding(rec), len(leaves), k, seed)
    got_idx = sorted(o["index"] for o in tdoc.openings)
    required_openings = min(max(min_openings, 1), len(leaves))
    check("challenge", got_idx == expected_idx and len(got_idx) == min(k, len(leaves)) and len(got_idx) >= required_openings,
          f"{len(got_idx)} openings, expected {len(expected_idx)}, policy minimum {required_openings}"
          + ("" if got_idx == expected_idx else ", indices differ"))

    # structure: graphs versus tokens
    check("graph_count", len(resp) <= n_graphs <= len(resp) + 1,
          f"{n_graphs} graphs for {len(resp)} response tokens")
    graph_positions: dict[int, list[int]] = {}
    for leaf in leaves:
        graph_positions.setdefault(leaf["g"], []).append(leaf["i"])
    check("graph_order", sorted(graph_positions) == list(range(n_graphs)) and
          all(pos == list(range(len(pos))) for pos in graph_positions.values()), "graph and node indices are contiguous")

    # inputs, edges, zero state, logits binding: one pass over every leaf
    zero_hashes: dict[int, str] = {}
    edge_bad = 0
    edge_total = 0
    inputs = {kind: Counter() for kind in HARD_INPUTS + SOFT_INPUTS}
    unknown_inputs = 0
    last_matmul_by_graph: dict[int, dict] = {}
    for idx, leaf in enumerate(leaves):
        if leaf["op"] == "MUL_MAT":
            last_matmul_by_graph[leaf["g"]] = leaf
        for i, s in enumerate(leaf["srcs"]):
            if s.get("kind") != "data":
                continue
            p = s["producer"]
            if p >= 0:
                edge_total += 1
                if p >= idx or leaves[p]["out"]["base"]["sha256"] != s["base"]["sha256"] \
                        or leaves[p]["out"]["base"]["nbytes"] != s["base"]["nbytes"]:
                    edge_bad += 1
            elif p == PRODUCER_INITIAL:
                edge_total += 1
                nb = s["base"]["nbytes"]
                if nb not in zero_hashes:
                    zero_hashes[nb] = _sha256(bytes(nb))
                if not s["base"]["name"].startswith("cache_") or zero_hashes[nb] != s["base"]["sha256"]:
                    edge_bad += 1
            elif p == PRODUCER_INPUT:
                kind = classify_input(leaf, i, s)
                if kind is None:
                    unknown_inputs += 1
                    continue
                exp = expected_input(kind, rec, leaf["g"], leaf, s)
                if exp is None:
                    inputs[kind]["no_expectation"] += 1
                elif _sha256(exp) == s["base"]["sha256"]:
                    inputs[kind]["match"] += 1
                else:
                    inputs[kind]["mismatch"] += 1
    check("edges", edge_bad == 0, f"{edge_bad} of {edge_total} data edges inconsistent")
    for kind in HARD_INPUTS:
        c = inputs[kind]
        check(f"input_{kind}", c["mismatch"] == 0 and c["match"] > 0,
              f"{c['match']} match, {c['mismatch']} mismatch", hard=True)
    for kind in SOFT_INPUTS:
        c = inputs[kind]
        check(f"input_{kind}", c["mismatch"] == 0, f"{c['match']} match, {c['mismatch']} mismatch", hard=False)
    check("inputs_unclassified", unknown_inputs == 0, f"{unknown_inputs} inputs not classified")

    per_token = rec["response"]["per_token"]
    bound = 0
    bad = 0
    records_ok = len(per_token) == len(resp) and all(isinstance(row, dict) and isinstance(row.get("logits_sha256"), str) and row.get("token") == resp[i]
                                                     and row.get("position") == len(prompt) + i
                                                     for i, row in enumerate(per_token))
    check("per_token", records_ok, f"{len(per_token)} records for {len(resp)} response tokens")
    for g in range(len(resp)):
        if g >= len(per_token):
            bad += 1
            continue
        leaf = last_matmul_by_graph.get(g)
        if leaf is None or leaf["out"]["ne"][1] != 1:
            bad += 1
            continue
        bound += 1
        if leaf["out"]["base"]["sha256"] != per_token[g].get("logits_sha256"):
            bad += 1
    check("logits_binding", bad == 0 and bound == len(resp),
          f"{bound} graphs bound to {len(resp)} receipt logits hashes, {bad} failed")

    # openings
    t_open = time.time()
    commitment = commitment or gguf_commitment(model_path)
    commit_hash = {t["name"]: t for t in commitment["tensors"]}
    store = WeightStore(model_path)
    opening_reports = []
    ops_seen: Counter = Counter()
    worst: dict[str, float] = {}
    n_bad_open = 0
    for o in tdoc.openings:
        idx = o["index"]
        rep: dict = {"index": idx}
        if not 0 <= idx < len(leaves):
            rep["error"] = "index out of range"
            n_bad_open += 1
            opening_reports.append(rep)
            continue
        leaf = leaves[idx]
        rep.update({"g": leaf["g"], "name": leaf["name"], "op": leaf["op"]})
        ops_seen[leaf["op"]] += 1
        rep["path_ok"] = check_opening_path(None, leaf, o, tr["root"])
        out_blob, src_blobs = open_bytes(o)
        rep["out_hash_ok"] = _sha256(out_blob) == leaf["out"]["base"]["sha256"] and len(out_blob) == leaf["out"]["base"]["nbytes"]
        arrays: list[np.ndarray | None] = []
        rows: np.ndarray | None = None
        qweight: tuple[np.ndarray, str] | None = None
        weights_ok = True
        srcs_ok = True
        problem = ""
        try:
            out_arr = ops.tensor_from_bytes(out_blob, leaf["out"]["type"], leaf["out"]["ne"], leaf["out"]["nb"], leaf["out"]["offset"])
            for i, s in enumerate(leaf["srcs"]):
                if s["kind"] == "weight":
                    name = s["base"]["name"]
                    c = commit_hash.get(name)
                    c_shape = [int(x) for x in c["shape"]] if c else []
                    ne = s["base"]["ne"]
                    shape_ok = ne[: len(c_shape)] == c_shape and all(x == 1 for x in ne[len(c_shape):])
                    if c is None or c["sha256"] != s["sha256"] or c["type"].lower() != s["base"]["type"].lower() or not shape_ok:
                        weights_ok = False
                        problem = f"weight {name} does not match the model commitment"
                        arrays.append(None)
                        continue
                    if leaf["op"] == "MUL_MAT" and i == 0:
                        if s["base"]["ne"][1] > BIG_MATMUL_ROWS:
                            rng = np.random.default_rng(int.from_bytes(hashlib.sha256(bytes.fromhex(tr["root"]) + idx.to_bytes(8, "big")).digest()[:8], "big"))
                            rows = np.sort(rng.choice(s["base"]["ne"][1], size=min(ROWS_CHECKED, s["base"]["ne"][1]), replace=False))
                        arrays.append(store.array4d(name, rows))
                        raw = store.blocks(name, rows)
                        if raw is not None:
                            qweight = (raw, store.type_name(name))
                    elif leaf["op"] == "GET_ROWS" and i == 0:
                        ids_blob = src_blobs[1]
                        ids = np.frombuffer(ids_blob, dtype=np.int32) if leaf["srcs"][1]["type"] == "i32" else np.frombuffer(ids_blob, dtype=np.int64)
                        sel = store.array4d(name, ids.astype(np.int64))
                        arrays.append(sel)
                        rep["get_rows_remapped"] = True
                    else:
                        arrays.append(store.array4d(name))
                else:
                    blob = src_blobs[i]
                    if blob is None or _sha256(blob) != s["base"]["sha256"] or len(blob) != s["base"]["nbytes"]:
                        srcs_ok = False
                        problem = f"input {i} bytes do not hash to the leaf"
                        arrays.append(None)
                        continue
                    if leaf["op"] == "GET_ROWS" and i == 1 and rep.get("get_rows_remapped"):
                        n_ids = int(np.prod(s["ne"]))
                        arrays.append(np.arange(n_ids, dtype=np.int32).reshape(tuple(reversed(s["ne"]))))
                    else:
                        arrays.append(ops.tensor_from_bytes(blob, s["type"], s["ne"], s["nb"], s["offset"]))
        except ops.OpError as e:
            srcs_ok = False
            problem = str(e)
        rep["weights_ok"] = weights_ok
        rep["srcs_ok"] = srcs_ok
        if rep["path_ok"] and rep["out_hash_ok"] and weights_ok and srcs_ok and all(a is not None for a in arrays):
            t1 = time.time()
            res = ops.execute(leaf, out_arr, arrays, tol, rows=rows, qweight=qweight)
            rep["reexec"] = res.to_dict()
            rep["seconds"] = round(time.time() - t1, 3)
            if not math.isinf(res.error):
                worst[leaf["op"]] = max(worst.get(leaf["op"], 0.0), res.error)
            if not res.ok:
                n_bad_open += 1
        else:
            rep["error"] = problem or "opening failed integrity checks"
            n_bad_open += 1
        opening_reports.append(rep)
    check("openings", n_bad_open == 0, f"{len(tdoc.openings) - n_bad_open} of {len(tdoc.openings)} openings verified",
          ops=dict(ops_seen), worst_error=worst)

    verdict = "accept" if not hard_fail else "reject"
    return {
        "verdict": verdict,
        "reason": "trace verified" if verdict == "accept" else hard_fail[0],
        "checks": checks,
        "openings": opening_reports,
        "coverage": {"n_leaves": len(leaves), "n_graphs": n_graphs, "k": len(tdoc.openings), "ops": dict(ops_seen)},
        "seconds": {"total": round(time.time() - t0, 3), "openings": round(time.time() - t_open, 3)},
    }


def main(argv: list[str] | None = None) -> int:
    from receipts import receipt as receipt_mod
    from receipts.trace import load_trace, sidecar_path

    p = argparse.ArgumentParser(description="Verify a receipt's activation trace without running the model.")
    p.add_argument("receipt")
    p.add_argument("--trace", help="sidecar path (default: <receipt>.trace.json.gz)")
    p.add_argument("--model", required=True)
    p.add_argument("--expected-topology-sha256", required=True)
    p.add_argument("--min-openings", type=int, default=32)
    p.add_argument("--out")
    a = p.parse_args(argv)
    rec = receipt_mod.load(a.receipt)
    tdoc = load_trace(a.trace or sidecar_path(a.receipt))
    sig_ok, sig_reason = receipt_mod.check_signature(rec)
    res = verify_trace(rec, tdoc, a.model, expected_topology_sha256=a.expected_topology_sha256, min_openings=a.min_openings)
    if not sig_ok:
        res["verdict"], res["reason"] = "reject", f"signature: {sig_reason}"
    print(f"verdict: {res['verdict']} ({res['reason']})")
    for name, c in res.get("checks", {}).items():
        print(f"  {name:22s} {'ok ' if c['ok'] else 'BAD'} {c.get('detail', '')}")
    cov = res.get("coverage", {})
    print(f"  openings {cov.get('k')} of {cov.get('n_leaves')} leaves; ops {cov.get('ops')}; "
          f"worst error {res['checks'].get('openings', {}).get('worst_error')}; {res.get('seconds')}")
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))
    return 0 if res["verdict"] == "accept" else 1


if __name__ == "__main__":
    raise SystemExit(main())
