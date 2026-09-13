import numpy as np
from gguf import quants
from gguf.constants import GGMLQuantizationType

from receipts import qdot


def _random_blocks(rng, rows, nb, size, d_offsets):
    b = rng.integers(0, 256, size=(rows, nb, size), dtype=np.uint8)
    for off in d_offsets:  # keep the float16 scales finite and small
        vals = rng.uniform(0.001, 0.1, size=(rows, nb)).astype(np.float16).view(np.uint8).reshape(rows, nb, 2)
        b[:, :, off: off + 2] = vals
    return b.reshape(rows, nb * size)


def test_q4_k_and_q6_k_unpack_match_gguf_dequantize():
    rng = np.random.default_rng(0)
    q4 = _random_blocks(rng, 5, 3, qdot.Q4_K_BLOCK, [0, 2])
    ref = quants.dequantize(q4, GGMLQuantizationType.Q4_K)
    assert np.array_equal(qdot.dequantize(q4, "Q4_K"), ref)
    q6 = _random_blocks(rng, 4, 2, qdot.Q6_K_BLOCK, [208])
    ref6 = quants.dequantize(q6, GGMLQuantizationType.Q6_K)
    assert np.array_equal(qdot.dequantize(q6, "Q6_K"), ref6)


def test_quantize_q8_k_follows_ggml_conventions():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(3, 512)).astype(np.float32)
    x[1, 300] = 9.0  # a positive maximum still maps to -127 with a negative scale
    x[2, 256:] = 0.0  # an all-zero block
    d, q, bsums = qdot.quantize_q8_k(x)
    assert d.shape == (3, 2) and q.shape == (3, 2, 256) and bsums.shape == (3, 2, 16)
    assert q[1, 1, 44] == -127 and d[1, 1] < 0
    assert d[2, 1] == 0 and not q[2, 1].any()
    recon = d[..., None] * q.astype(np.float32)
    assert np.max(np.abs(recon - x.reshape(3, 2, 256))) <= np.max(np.abs(d)) / 2 + 1e-6
    assert np.array_equal(bsums, q.reshape(3, 2, 16, 16).astype(np.int32).sum(-1))


def test_mul_mat_q8k_tracks_the_float_product():
    rng = np.random.default_rng(2)
    blocks = _random_blocks(rng, 7, 2, qdot.Q4_K_BLOCK, [0, 2])
    acts = rng.normal(size=(3, 512)).astype(np.float32)
    w = quants.dequantize(blocks, GGMLQuantizationType.Q4_K).astype(np.float64)
    exact = acts.astype(np.float64) @ w.T
    got = qdot.mul_mat_q8k(blocks, "Q4_K", acts)
    assert got.shape == (3, 7)
    assert np.max(np.abs(got - exact)) / np.max(np.abs(exact)) < 2e-2  # 8-bit activation noise only
    blocks6 = _random_blocks(rng, 6, 2, qdot.Q6_K_BLOCK, [208])
    w6 = quants.dequantize(blocks6, GGMLQuantizationType.Q6_K).astype(np.float64)
    got6 = qdot.mul_mat_q8k(blocks6, "Q6_K", acts)
    assert np.max(np.abs(got6 - acts.astype(np.float64) @ w6.T)) / np.max(np.abs(acts @ w6.T)) < 2e-2
