import math
import struct

import numpy as np

from receipts import ops


def _hex_f32(*vals):
    return struct.pack("<" + "f" * len(vals), *vals).hex()


def test_tensor_from_bytes_contiguous_and_permuted_views():
    a = np.arange(24, dtype=np.float32).reshape(2, 3, 4)  # numpy (ne2, ne1, ne0)
    blob = a.tobytes()
    v = ops.tensor_from_bytes(blob, "f32", [4, 3, 2, 1], [4, 16, 48, 96])
    assert np.array_equal(v, a.reshape(1, 2, 3, 4))
    # permute ne0 <-> ne1 without moving data: ne=[3,4,2], nb=[16,4,48]
    p = ops.tensor_from_bytes(blob, "f32", [3, 4, 2, 1], [16, 4, 48, 96])
    assert np.array_equal(p[0], np.transpose(a, (0, 2, 1)))
    # offset into the base
    o = ops.tensor_from_bytes(blob, "f32", [4, 1, 1, 1], [4, 16, 48, 96], offset=48)
    assert np.array_equal(o.reshape(-1), a[1, 0])


def test_rms_norm_matches_definition():
    x = np.random.default_rng(0).normal(size=(1, 1, 3, 8))
    eps = 1e-6
    ref = x / np.sqrt(np.mean(x * x, axis=-1, keepdims=True) + eps)
    assert np.allclose(ops.op_rms_norm(x, _hex_f32(eps)), ref)


def test_soft_max_with_causal_mask_and_scale():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(1, 2, 3, 5))  # H=2, n=3, n_kv=5
    mask = np.full((1, 1, 3, 5), -np.inf)
    for t in range(3):
        mask[0, 0, t, : t + 1] = 0.0
    y = ops.op_soft_max(x, mask, _hex_f32(0.5, 0.0))
    assert np.allclose(y.sum(-1), 1.0)
    assert np.all(y[0, :, 0, 1:] == 0.0)  # first token attends only to itself
    z = x[0, 1, 2] * 0.5
    z = z[:3] - z[:3].max()
    assert np.allclose(y[0, 1, 2, :3], np.exp(z) / np.exp(z).sum())


def test_rope_neox_rotates_pairs_by_position_angle():
    D, H, n = 8, 1, 2
    x = np.random.default_rng(2).normal(size=(1, n, H, D))
    pos = np.array([0, 3], dtype=np.int32)
    params = struct.pack("<5i", 0, D, 2, 0, 4096) + struct.pack("<6f", 10000.0, 1.0, 0.0, 1.0, 32.0, 1.0)
    y = ops.op_rope(x, pos, params.hex())
    assert np.allclose(y[0, 0], x[0, 0])  # position 0 is the identity
    half = D // 2
    inv = 10000.0 ** (-np.arange(half) * 2.0 / D)
    th = 3 * inv
    x0, x1 = x[0, 1, 0, :half], x[0, 1, 0, half:]
    assert np.allclose(y[0, 1, 0, :half], x0 * np.cos(th) - x1 * np.sin(th))
    assert np.allclose(y[0, 1, 0, half:], x0 * np.sin(th) + x1 * np.cos(th))


def test_mul_mat_broadcasts_kv_heads_like_ggml():
    rng = np.random.default_rng(3)
    a = rng.normal(size=(1, 2, 5, 4))  # 2 kv heads, M=5 cells, K=4
    b = rng.normal(size=(1, 6, 3, 4))  # 6 heads, N=3 tokens
    out = ops.op_mul_mat(a, b)
    assert out.shape == (1, 6, 3, 5)
    assert np.allclose(out[0, 4], b[0, 4] @ a[0, 1].T)  # head 4 uses kv head 4 // 3 = 1


def test_swiglu_and_set_rows_and_get_rows():
    g = np.array([[[[1.0, -2.0]]]])
    u = np.array([[[[3.0, 4.0]]]])
    y = ops.op_glu(g, u, struct.pack("<2i", 2, 0).hex())
    assert np.allclose(y, g / (1 + np.exp(-g)) * u)
    dst = np.zeros((1, 1, 4, 2), dtype=np.float16)
    src = np.array([[[[1.5, 2.5], [3.5, 4.5]]]], dtype=np.float32)
    idx = np.array([3, 1], dtype=np.int64)
    out = ops.op_set_rows(dst, src, idx)
    assert out.dtype == np.float16 and out[0, 0, 3, 0] == 1.5 and out[0, 0, 1, 1] == 4.5 and out[0, 0, 0].sum() == 0
    table = np.arange(12, dtype=np.float64).reshape(1, 1, 4, 3)
    rows = ops.op_get_rows(table, np.array([[2, 0]], dtype=np.int64))
    assert np.array_equal(rows[0, 0], table[0, 0, [2, 0]])


def test_execute_exact_op_and_tolerance_verdicts():
    leaf = {"op": "CONT", "op_name": "CONT", "params": "", "out": {"ne": [4, 1, 1, 1]}}
    src = np.arange(4, dtype=np.float32).reshape(1, 1, 1, 4)
    ok = ops.execute(leaf, src.copy(), [src], ops.Tolerances())
    assert ok.ok and ok.exact and ok.error == 0.0
    bad = ops.execute(leaf, src + np.float32(1e-3), [src], ops.Tolerances())
    assert not bad.ok
    leaf = {"op": "ADD", "op_name": "ADD", "params": "", "out": {"ne": [4, 1, 1, 1]}}
    res = ops.execute(leaf, (src + src).astype(np.float32), [src, src], ops.Tolerances())
    assert res.ok and res.error < 1e-7
    res = ops.execute(leaf, (src + src + np.float32(0.01)).astype(np.float32), [src, src], ops.Tolerances())
    assert not res.ok and res.error > 1e-3
    unsupported = ops.execute({"op": "IM2COL", "op_name": "IM2COL", "params": "", "out": {"ne": [1]}}, src, [src], ops.Tolerances())
    assert not unsupported.ok and math.isinf(unsupported.error)
