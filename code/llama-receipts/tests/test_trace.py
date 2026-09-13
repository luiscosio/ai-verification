import hashlib

import numpy as np

from receipts import trace
from receipts.receipt import canonical_bytes
from receipts.verify_trace import classify_input, expected_input, graph_start, graph_tokens


def test_derive_indices_is_deterministic_distinct_and_in_range():
    root = "ab" * 32
    a = trace.derive_indices(root, b"bind", 1000, 32)
    b = trace.derive_indices(root, b"bind", 1000, 32)
    assert a == b and a == sorted(a) and len(set(a)) == 32 and all(0 <= i < 1000 for i in a)
    assert trace.derive_indices(root, b"other", 1000, 32) != a
    assert trace.derive_indices(root, b"bind", 1000, 32, seed=b"v") != a
    assert trace.derive_indices(root, b"bind", 5, 32) == [0, 1, 2, 3, 4]
    assert trace.derive_indices(root, b"bind", 0, 4) == []


def _leaf(g, i, op, out_hash, srcs):
    return {"v": 1, "g": g, "i": i, "name": f"n{i}", "op": op, "op_name": op, "params": "",
            "out": {"type": "f32", "ne": [4, 1, 1, 1], "nb": [4, 16, 16, 16], "offset": 0,
                    "base": {"name": f"n{i}", "type": "f32", "ne": [4, 1, 1, 1], "nb": [4, 16, 16, 16], "nbytes": 16, "sha256": out_hash}},
            "srcs": srcs}


def test_openings_round_trip_and_path_check(tmp_path):
    tr = trace.Tracer(weight_hashes={})
    blobs = [np.arange(4, dtype=np.float32).tobytes(), np.ones(4, dtype=np.float32).tobytes(), bytes(16)]
    for i, b in enumerate(blobs):
        leaf = _leaf(0, i, "ADD", hashlib.sha256(b).hexdigest(), [])
        tr.leaves.append(leaf)
        tr.leaf_bytes.append(canonical_bytes(leaf))
        tr.captured[i] = {"out": b, "srcs": []}
    root = tr.root()
    openings = trace.build_openings(tr, [0, 2])
    doc = trace.TraceDoc(root=root, n_graphs=1, leaves=tr.leaves, openings=openings, challenge={"k": 2, "indices": [0, 2]})
    path = tmp_path / "t.trace.json.gz"
    trace.save_trace(doc, path)
    back = trace.load_trace(path)
    assert back.root == root and len(back.leaves) == 3 and [o["index"] for o in back.openings] == [0, 2]
    for o in back.openings:
        assert trace.check_opening_path(None, back.leaves[o["index"]], o, root)
        out, srcs = trace.open_bytes(o)
        assert out == blobs[o["index"]] and srcs == []
    tampered = dict(back.leaves[0])
    tampered["name"] = "x"
    assert not trace.check_opening_path(None, tampered, back.openings[0], root)


def test_sidecar_path_and_expected_inputs():
    assert trace.sidecar_path("out/r1.json").name == "r1.trace.json.gz"
    rec = {"request": {"prompt_tokens": [5, 6, 7]}, "response": {"tokens": [8, 9]}}
    assert graph_tokens(rec, 0) == [5, 6, 7] and graph_tokens(rec, 1) == [8] and graph_tokens(rec, 2) == [9]
    assert graph_tokens(rec, 3) is None
    assert graph_start(rec, 0) == 0 and graph_start(rec, 2) == 4
    leaf = {"op": "GET_ROWS", "srcs": [{"kind": "weight"}, {"kind": "data"}]}
    assert classify_input(leaf, 1, {}) == "tokens"
    assert expected_input("tokens", rec, 0, leaf, {}) == np.array([5, 6, 7], dtype=np.int32).tobytes()
    assert expected_input("positions", rec, 2, leaf, {}) == np.array([4], dtype=np.int32).tobytes()
    rope = {"op": "ROPE", "srcs": [{"kind": "data"}, {"kind": "data"}]}
    assert classify_input(rope, 1, {}) == "positions"
    mask = expected_input("mask", rec, 0, {"op": "SOFT_MAX"}, {"ne": [8, 3], "type": "f32"})
    m = np.frombuffer(mask, dtype=np.float32).reshape(3, 8)
    assert m[0, 0] == 0.0 and np.isneginf(m[0, 1]) and m[2, 2] == 0.0 and np.isneginf(m[2, 3])
    setv = {"op": "SET_ROWS", "srcs": [{}, {}, {"base": {"name": "cache_v_l0", "ne": [4, 16]}}]}
    v = np.frombuffer(expected_input("v_cells", rec, 1, setv, {}), dtype=np.int64)
    assert list(v) == [3, 19, 35, 51]  # cell 3, dims 0..3, kv_size 16
