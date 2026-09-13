"""Integer-exact references for ggml's quantized dot products.

llama.cpp's CPU backend does not multiply a dequantized weight by a float
activation. It quantizes the activation row to Q8_K (blocks of 256 int8 values
with one float scale and sixteen group sums) and runs an integer dot product
against the weight's 4-bit or 6-bit values, applying the per-sub-block scales
afterwards. This module reproduces that arithmetic, following
`quantize_row_q8_K_ref` and `ggml_vec_dot_{q4,q6}_K_q8_K_generic` from ggml.
All integer sums are exact (they are done in float64, far below 2^53), so the
only difference from the kernel is the order of the final float accumulation.

This is also the arithmetic a proof system would need to constrain: integer
products and sums, with a handful of float scales per block.
"""

from __future__ import annotations

import numpy as np

QK_K = 256
Q4_K_BLOCK = 144
Q6_K_BLOCK = 210


def quantize_q8_k(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Quantize rows of float32 activations to Q8_K exactly as ggml does.

    Returns (d (N, nb) float32, q (N, nb, 256) int8, bsums (N, nb, 16) int32).
    The element with the largest magnitude maps to -127 and d = 1 / iscale, so
    d carries the sign; a zero block has d = 0 and all-zero quants.
    """
    x = np.ascontiguousarray(x, dtype=np.float32)
    n, k = x.shape
    if k % QK_K:
        raise ValueError(f"row length {k} is not a multiple of {QK_K}")
    nb = k // QK_K
    xb = x.reshape(n, nb, QK_K)
    idx = np.argmax(np.abs(xb), axis=-1)  # first occurrence, like the strict '>' in the C loop
    mx = np.take_along_axis(xb, idx[..., None], axis=-1)[..., 0]
    nz = mx != 0
    safe = np.where(nz, mx, np.float32(1.0))
    iscale = np.where(nz, np.float32(-127.0) / safe, np.float32(0.0)).astype(np.float32)
    v = np.rint(iscale[..., None] * xb)  # float32 product, round half to even, like nearest_int
    q = np.minimum(v, 127).astype(np.int8)
    d = np.where(nz, np.float32(1.0) / np.where(nz, iscale, np.float32(1.0)), np.float32(0.0)).astype(np.float32)
    bsums = q.reshape(n, nb, 16, 16).astype(np.int32).sum(-1)
    return d, q, bsums


def _scale_min_k4(scales: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unpack the twelve packed bytes of a Q4_K block into eight 6-bit scales and mins."""
    s = scales.reshape(-1, 3, 4)
    d, m, m_d = s[:, 0], s[:, 1], s[:, 2]
    sc = np.concatenate([d & 0x3F, (m_d & 0x0F) | ((d >> 2) & 0x30)], axis=-1)
    mn = np.concatenate([m & 0x3F, (m_d >> 4) | ((m >> 2) & 0x30)], axis=-1)
    return sc, mn


def unpack_q4_k(blocks: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(R, nb*144) uint8 -> d (R, nb), dmin (R, nb), scales (R, nb, 8), mins (R, nb, 8), q (R, nb, 256) in 0..15."""
    r = blocks.shape[0]
    nb = blocks.shape[1] // Q4_K_BLOCK
    b = np.ascontiguousarray(blocks).reshape(r * nb, Q4_K_BLOCK)
    d = b[:, 0:2].copy().view(np.float16)[:, 0].astype(np.float32).reshape(r, nb)
    dmin = b[:, 2:4].copy().view(np.float16)[:, 0].astype(np.float32).reshape(r, nb)
    sc, mn = _scale_min_k4(b[:, 4:16])
    qs = b[:, 16:144].reshape(r * nb, 4, 32)
    q = np.stack([qs & 0x0F, qs >> 4], axis=2).reshape(r, nb, QK_K)  # low nibbles of 32 bytes, then high
    return d, dmin, sc.reshape(r, nb, 8), mn.reshape(r, nb, 8), q


def unpack_q6_k(blocks: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(R, nb*210) uint8 -> d (R, nb), scales (R, nb, 16) int8, q (R, nb, 256) in -32..31."""
    r = blocks.shape[0]
    nb = blocks.shape[1] // Q6_K_BLOCK
    b = np.ascontiguousarray(blocks).reshape(r * nb, Q6_K_BLOCK)
    ql = b[:, 0:128].reshape(-1, 2, 2, 32)  # half, 32-byte group, lane
    qh = b[:, 128:192].reshape(-1, 2, 32)  # half, lane
    scales = b[:, 192:208].copy().view(np.int8).reshape(r, nb, 16)
    d = b[:, 208:210].copy().view(np.float16)[:, 0].astype(np.float32).reshape(r, nb)
    lo, hi = ql & 0x0F, ql >> 4
    q = np.empty((r * nb, 2, 4, 32), dtype=np.uint8)
    q[:, :, 0] = lo[:, :, 0] | (((qh >> 0) & 3) << 4)
    q[:, :, 1] = lo[:, :, 1] | (((qh >> 2) & 3) << 4)
    q[:, :, 2] = hi[:, :, 0] | (((qh >> 4) & 3) << 4)
    q[:, :, 3] = hi[:, :, 1] | (((qh >> 6) & 3) << 4)
    return d, scales, q.reshape(r, nb, QK_K).astype(np.int16) - 32


def dequantize(blocks: np.ndarray, qtype: str) -> np.ndarray:
    """Float32 weights from the unpacked integers, the way ggml's dequantize rows do. For tests."""
    qtype = qtype.upper()
    if qtype == "Q4_K":
        d, dmin, sc, mn, q = unpack_q4_k(blocks)
        r, nb = d.shape
        dl = (d[..., None] * sc.astype(np.float32))[..., :, None]
        ml = (dmin[..., None] * mn.astype(np.float32))[..., :, None]
        return (dl * q.reshape(r, nb, 8, 32).astype(np.float32) - ml).reshape(r, nb * QK_K)
    if qtype == "Q6_K":
        d, scales, q = unpack_q6_k(blocks)
        r, nb = d.shape
        dl = (d[..., None] * scales.astype(np.float32))[..., :, None]
        return (dl * q.reshape(r, nb, 16, 16).astype(np.float32)).reshape(r, nb * QK_K)
    raise ValueError(f"no integer reference for {qtype}")


SUPPORTED = ("Q4_K", "Q6_K")


def mul_mat_q8k(blocks: np.ndarray, qtype: str, acts: np.ndarray) -> np.ndarray:
    """ggml's CPU matmul: weight rows `blocks` (M, bytes) of `qtype` against float32 `acts` (N, K) -> (N, M) float64.

    The activation is quantized to Q8_K per row; every integer sum matches the
    kernel exactly and the per-block float scaling is applied in float64.
    """
    qtype = qtype.upper()
    d_a, q8, bsums = quantize_q8_k(acts)
    n, nb = d_a.shape
    if qtype == "Q4_K":
        d_w, dmin, sc, mn, q4 = unpack_q4_k(blocks)
        m = d_w.shape[0]
        if d_w.shape[1] != nb:
            raise ValueError("weight and activation block counts differ")
        w_int = (sc.astype(np.int32)[..., None] * q4.reshape(m, nb, 8, 32).astype(np.int32)).reshape(m, nb, QK_K)
        mins16 = np.repeat(mn.astype(np.int32), 2, axis=-1)  # mins[j // 2] for the sixteen group sums
        out = np.zeros((n, m), dtype=np.float64)
        for i in range(nb):
            s1 = q8[:, i].astype(np.float64) @ w_int[:, i].astype(np.float64).T
            s2 = bsums[:, i].astype(np.float64) @ mins16[:, i].astype(np.float64).T
            da = d_a[:, i, None].astype(np.float64)
            out += da * d_w[None, :, i].astype(np.float64) * s1 - da * dmin[None, :, i].astype(np.float64) * s2
        return out
    if qtype == "Q6_K":
        d_w, scales, q6 = unpack_q6_k(blocks)
        m = d_w.shape[0]
        if d_w.shape[1] != nb:
            raise ValueError("weight and activation block counts differ")
        w_int = (scales.astype(np.int32)[..., None] * q6.reshape(m, nb, 16, 16).astype(np.int32)).reshape(m, nb, QK_K)
        out = np.zeros((n, m), dtype=np.float64)
        for i in range(nb):
            s1 = q8[:, i].astype(np.float64) @ w_int[:, i].astype(np.float64).T
            out += d_a[:, i, None].astype(np.float64) * d_w[None, :, i].astype(np.float64) * s1
        return out
    raise ValueError(f"no integer reference for {qtype}")
