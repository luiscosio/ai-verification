"""Reference re-execution of ggml ops in numpy, for checking opened trace nodes.

Conventions. A ggml tensor with `ne = [n0, n1, n2, n3]` and byte strides `nb`
becomes a numpy array of shape `(n3, n2, n1, n0)` built directly on the base
tensor's bytes with `as_strided`, so permuted and sliced views cost nothing.
Reference math runs in float64 and is compared to the prover's output with a
normalized error, `max|out - ref| / max(max|ref|, floor)`. Ops that only move
or convert data (CONT, SET_ROWS) are compared bit for bit.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

import numpy as np

from receipts import qdot

NP_DTYPES = {"f32": np.float32, "f16": np.float16, "i32": np.int32, "i64": np.int64, "f64": np.float64,
             "bf16": np.uint16, "i8": np.int8, "i16": np.int16}
EXACT_OPS = frozenset({"CONT", "SET_ROWS", "DUP", "CPY"})
UNSUPPORTED = "unsupported"


class OpError(Exception):
    pass


@dataclass
class OpResult:
    op: str
    exact: bool  # compared bitwise
    ok: bool
    error: float  # normalized max abs error (0 when exact and equal)
    detail: str = ""
    checked_fraction: float = 1.0  # < 1 when only a row subset of a large matmul was recomputed

    def to_dict(self) -> dict:
        return {"op": self.op, "exact": self.exact, "ok": self.ok,
                "error": None if math.isinf(self.error) else self.error, "detail": self.detail,
                "checked_fraction": self.checked_fraction}


def tensor_from_bytes(blob: bytes, ttype: str, ne: list[int], nb: list[int], offset: int = 0) -> np.ndarray:
    """Read-only strided numpy view over `blob` for a (possibly non-contiguous) ggml tensor."""
    if ttype not in NP_DTYPES:
        raise OpError(f"cannot view quantized or unknown type {ttype} as an array")
    dt = np.dtype(NP_DTYPES[ttype])
    span_end = offset + sum((n - 1) * s for n, s in zip(ne, nb)) + dt.itemsize
    if span_end > len(blob):
        raise OpError(f"view needs {span_end} bytes but base has {len(blob)}")
    if offset % dt.itemsize or any(s % dt.itemsize for s in nb):
        raise OpError("view is not element aligned")
    n_items = (span_end - offset) // dt.itemsize
    typed = np.frombuffer(blob, dtype=np.uint8)[offset: offset + n_items * dt.itemsize].view(dt)
    return np.lib.stride_tricks.as_strided(typed, shape=tuple(reversed(ne)), strides=tuple(reversed(nb)), writeable=False)


def f32_params(params_hex: str, n: int, skip_bytes: int = 0) -> list[float]:
    raw = bytes.fromhex(params_hex).ljust(skip_bytes + 4 * n, b"\0")
    return list(struct.unpack("<" + "f" * n, raw[skip_bytes: skip_bytes + 4 * n]))


def i32_params(params_hex: str, n: int) -> list[int]:
    raw = bytes.fromhex(params_hex).ljust(4 * n, b"\0")
    return list(struct.unpack("<" + "i" * n, raw[: 4 * n]))


def normalized_error(out: np.ndarray, ref: np.ndarray, floor: float = 1e-6) -> float:
    out64 = _to_f64(out)
    ref64 = _to_f64(ref)
    if out64.shape != ref64.shape:
        return math.inf
    if ref64.size == 0:
        return 0.0
    if not np.all(np.isfinite(out64)) or not np.all(np.isfinite(ref64)):
        return math.inf
    scale = max(float(np.max(np.abs(ref64))), floor)
    return float(np.max(np.abs(out64 - ref64))) / scale


def _to_f64(arr: np.ndarray) -> np.ndarray:
    if arr.dtype == np.uint16:  # bf16 payload
        return (arr.astype(np.uint32) << 16).view(np.float32).astype(np.float64)
    return arr.astype(np.float64)


def _repeat_to(b: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    """ggml broadcasting: each dim of b divides the target dim (not only 1)."""
    reps = []
    for tgt, cur in zip(shape, b.shape):
        if tgt % cur:
            raise OpError(f"cannot repeat {b.shape} to {shape}")
        reps.append(tgt // cur)
    return np.tile(b, reps) if any(r != 1 for r in reps) else b


def _silu(x: np.ndarray) -> np.ndarray:
    return x / (1.0 + np.exp(-x))


def _gelu(x: np.ndarray) -> np.ndarray:
    return 0.5 * x * (1.0 + np.tanh(math.sqrt(2.0 / math.pi) * (x + 0.044715 * x**3)))


# --- individual ops (float64 arrays, numpy-ordered shapes) ---------------------------------

def op_add(a, b):
    return a + _repeat_to(b, a.shape)


def op_mul(a, b):
    return a * _repeat_to(b, a.shape)


def op_scale(a, params_hex):
    s, bias = f32_params(params_hex, 2)
    return a * s + bias


def op_rms_norm(a, params_hex):
    (eps,) = f32_params(params_hex, 1)
    ms = np.mean(a * a, axis=-1, keepdims=True)
    return a / np.sqrt(ms + eps)


def op_norm(a, params_hex):
    (eps,) = f32_params(params_hex, 1)
    mu = np.mean(a, axis=-1, keepdims=True)
    var = np.mean((a - mu) ** 2, axis=-1, keepdims=True)
    return (a - mu) / np.sqrt(var + eps)


def op_mul_mat(a, b):
    """ggml_mul_mat: a (a3,a2,M,K), b (b3,b2,N,K) -> (b3,b2,N,M); a broadcasts over dims 2,3."""
    a3, a2, M, K = a.shape
    b3, b2, N, Kb = b.shape
    if K != Kb or b3 % a3 or b2 % a2:
        raise OpError(f"mul_mat shapes {a.shape} x {b.shape}")
    out = np.empty((b3, b2, N, M), dtype=np.float64)
    for i3 in range(b3):
        for i2 in range(b2):
            out[i3, i2] = b[i3, i2] @ a[i3 // (b3 // a3), i2 // (b2 // a2)].T
    return out


def op_get_rows(a, ids):
    """a (a3, a2, R, C), ids (.., a2 or 1, n) int -> (a3, a2, n, C)."""
    a3, a2, R, C = a.shape
    ids2 = ids.reshape(ids.shape[-2], ids.shape[-1]) if ids.ndim >= 2 else ids.reshape(1, -1)
    n = ids2.shape[-1]
    out = np.empty((a3, a2, n, C), dtype=a.dtype)
    for i3 in range(a3):
        for i2 in range(a2):
            idx = ids2[i2 if ids2.shape[0] > 1 else 0]
            if np.any(idx < 0) or np.any(idx >= R):
                raise OpError("get_rows index out of range")
            out[i3, i2] = a[i3, i2, idx]
    return out


def rope_params(params_hex: str) -> dict:
    p = i32_params(params_hex, 5)
    freq_base, freq_scale, ext_factor, attn_factor, beta_fast, beta_slow = f32_params(params_hex, 6, skip_bytes=20)
    return {"n_dims": p[1], "mode": p[2], "n_ctx_orig": p[4], "freq_base": freq_base, "freq_scale": freq_scale,
            "ext_factor": ext_factor, "attn_factor": attn_factor, "beta_fast": beta_fast, "beta_slow": beta_slow}


def op_rope(x, pos, params_hex):
    """x (1, n, H, D) [ne = D, H, n], pos (n,) int32."""
    rp = rope_params(params_hex)
    if rp["ext_factor"] != 0.0:
        raise OpError("rope with YaRN ext_factor is not implemented")
    if rp["mode"] & 8:
        raise OpError("multi-section rope is not implemented")
    n_dims, mode = rp["n_dims"], rp["mode"]
    _, n, H, D = x.shape
    pos = pos.reshape(-1).astype(np.float64)
    if pos.shape[0] != n:
        raise OpError(f"rope positions {pos.shape[0]} vs tokens {n}")
    half = n_dims // 2
    inv = rp["freq_base"] ** (-np.arange(half, dtype=np.float64) * 2.0 / n_dims)
    theta = pos[:, None] * rp["freq_scale"] * inv[None, :]  # (n, half)
    cos = (np.cos(theta) * rp["attn_factor"])[:, None, :]
    sin = (np.sin(theta) * rp["attn_factor"])[:, None, :]
    out = x.copy()
    if mode & 2:  # NEOX: pair i with i + half
        x0, x1 = x[0, :, :, :half], x[0, :, :, half:n_dims]
        out[0, :, :, :half] = x0 * cos - x1 * sin
        out[0, :, :, half:n_dims] = x0 * sin + x1 * cos
    else:  # NORMAL: adjacent pairs
        x0, x1 = x[0, :, :, 0:n_dims:2], x[0, :, :, 1:n_dims:2]
        out[0, :, :, 0:n_dims:2] = x0 * cos - x1 * sin
        out[0, :, :, 1:n_dims:2] = x0 * sin + x1 * cos
    return out


def op_soft_max(x, mask, params_hex):
    """x (1, H, n, n_kv) [ne = n_kv, n, H], mask (1, 1 or H, >=n, n_kv) or None."""
    scale, max_bias = f32_params(params_hex, 2)
    if max_bias != 0.0:
        raise OpError("soft_max with ALiBi max_bias is not implemented")
    z = x * scale
    if mask is not None:
        m = mask[:, :, : x.shape[2], :]
        z = z + _repeat_to(m, z.shape)
    z = z - np.max(z, axis=-1, keepdims=True)
    e = np.exp(z)
    return e / np.sum(e, axis=-1, keepdims=True)


def op_glu(a, b, params_hex):
    p = i32_params(params_hex, 2)
    glu_op, swapped = p[0], p[1]
    if b is None:
        half = a.shape[-1] // 2
        a, b = (a[..., half:], a[..., :half]) if swapped else (a[..., :half], a[..., half:])
    elif swapped:
        a, b = b, a
    if glu_op == 0:  # REGLU
        return np.maximum(a, 0.0) * b
    if glu_op == 1:  # GEGLU
        return _gelu(a) * b
    if glu_op == 2:  # SWIGLU
        return _silu(a) * b
    raise OpError(f"glu op {glu_op} not implemented")


def op_unary(a, name: str):
    if name == "SILU":
        return _silu(a)
    if name == "GELU":
        return _gelu(a)
    if name == "RELU":
        return np.maximum(a, 0.0)
    if name == "SIGMOID":
        return 1.0 / (1.0 + np.exp(-a))
    if name == "EXP":
        return np.exp(a)
    raise OpError(f"unary {name} not implemented")


def op_set_rows(dst_before: np.ndarray, src: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """dst (d3,d2,D1,D0), src (s3,s2,R,D0), idx (..,R) -> dst with rows idx[r] = src[r], in dst's dtype."""
    out = np.array(dst_before, copy=True)
    d3, d2, D1, D0 = out.shape
    s3, s2, R, C = src.shape
    if C != D0:
        raise OpError("set_rows row length mismatch")
    idx3 = idx.reshape(-1, idx.shape[-1]) if idx.ndim >= 2 else idx.reshape(1, -1)
    if idx3.shape[-1] != R:
        raise OpError("set_rows index count differs from source rows")
    for i3 in range(d3):
        for i2 in range(d2):
            rows = idx3[(i3 * d2 + i2) % idx3.shape[0]]
            if np.any(rows < 0) or np.any(rows >= D1):
                raise OpError("set_rows index out of range")
            out[i3, i2, rows, :] = src[i3 % s3, i2 % s2].astype(out.dtype)
    return out


# --- dispatch ----------------------------------------------------------------------------

@dataclass
class Tolerances:
    """Normalized max error allowed per op. Defaults come from the calibration runs in testset/."""

    # Calibrated Sep 11, 2026 on qwen2.5 1.5B Q4_K_M, about 1200 openings per backend (testset/results-trace.md).
    # Elementwise and normalization ops re-execute to about 1e-7 on both backends; ROPE reached 1.8e-6 and
    # SOFT_MAX 2.4e-5 on CPU. MUL_MAT is judged against three references (f32, f16 inputs, Q8_K integer path)
    # and takes the best: CPU weight matmuls then land at 7e-7 and Metal decode at 6e-7. What remains is
    # half-precision accumulation the references cannot reproduce: Metal prefill weight matmuls up to 2.9e-3
    # and CPU KV-cache matmuls up to 1.2e-3. The MUL_MAT limit leaves about 3x over the worst honest value.
    default: float = 1e-4
    per_op: dict[str, float] = field(default_factory=lambda: {
        "ADD": 1e-5, "MUL": 1e-5, "SCALE": 1e-5, "GET_ROWS": 1e-5,
        "RMS_NORM": 1e-5, "NORM": 1e-5, "ROPE": 5e-5, "SOFT_MAX": 2e-4, "SWIGLU": 1e-5, "GLU": 1e-5,
        "SILU": 1e-5, "GELU": 1e-5,
        "MUL_MAT": 8e-3,
    })

    def for_op(self, op: str) -> float:
        return self.per_op.get(op, self.default)


def _bitwise_equal(a: np.ndarray, b: np.ndarray) -> bool:
    if a.shape != b.shape or a.dtype != b.dtype:
        return False
    return bool(np.array_equal(np.ascontiguousarray(a).view(np.uint8), np.ascontiguousarray(b).view(np.uint8)))


def mul_mat_references(a: np.ndarray, b_raw: np.ndarray, qweight: tuple[np.ndarray, str] | None) -> dict[str, np.ndarray]:
    """The arithmetic the backends actually run, as float64 references.

    f32:  dequantized weight times float32 activation (Metal decode kernels).
    f16:  both operands rounded to half before the product (Metal prefill simdgroup kernels,
          and the CPU's f16 path for the KV cache).
    q8k:  ggml's CPU path for quantized weights: activations quantized to Q8_K, integer dot.
    """
    b = _to_f64(b_raw)
    refs = {"f32": op_mul_mat(a, b)}
    if b_raw.dtype == np.float32:
        refs["f16"] = op_mul_mat(a.astype(np.float16).astype(np.float64), b.astype(np.float16).astype(np.float64))
        if qweight is not None and qweight[1].upper() in qdot.SUPPORTED:
            b3, b2, n, k = b_raw.shape
            q = qdot.mul_mat_q8k(qweight[0], qweight[1], np.ascontiguousarray(b_raw).reshape(-1, k))
            refs["q8k"] = q.reshape(b3, b2, n, -1)
    return refs


def execute(leaf: dict, out: np.ndarray, srcs: list[np.ndarray | None], tol: Tolerances,
            rows: np.ndarray | None = None, qweight: tuple[np.ndarray, str] | None = None) -> OpResult:
    """Recompute `leaf` from `srcs` and compare with the prover's `out`.

    `srcs[i]` is the numpy view of source i, already dequantized for weights. For
    SET_ROWS, `srcs[2]` is the destination before the write and `out` the whole
    destination after it. For MUL_MAT, `rows` says that `srcs[0]` holds only those
    rows of the weight and `out` is compared on the matching columns; `qweight`
    carries the raw quantized rows so the integer reference can run too.
    """
    op = leaf["op"]
    params = leaf["params"]
    try:
        if op in EXACT_OPS:
            if op == "SET_ROWS":
                ref = op_set_rows(srcs[2], srcs[0], srcs[1])
            else:  # CONT, CPY, DUP: layout change, optional reshape (cont_2d), optional type conversion
                ref = np.ascontiguousarray(srcs[0]).astype(out.dtype)
                if ref.size == out.size:
                    ref = ref.reshape(out.shape)
            if ref.shape != out.shape:
                return OpResult(op, True, False, math.inf, "shape mismatch")
            same = _bitwise_equal(ref.astype(out.dtype), out)
            return OpResult(op, True, same, 0.0 if same else normalized_error(out, ref), "" if same else "exact op differs")
        if op == "GET_ROWS":
            ref = op_get_rows(_to_f64(srcs[0]), srcs[1].astype(np.int64))
        else:
            a = _to_f64(srcs[0])
            if op == "ADD":
                ref = op_add(a, _to_f64(srcs[1]))
            elif op == "MUL":
                ref = op_mul(a, _to_f64(srcs[1]))
            elif op == "SCALE":
                ref = op_scale(a, params)
            elif op == "RMS_NORM":
                ref = op_rms_norm(a, params)
            elif op == "NORM":
                ref = op_norm(a, params)
            elif op == "MUL_MAT":
                refs = mul_mat_references(a, srcs[1], qweight)
                cmp = out if rows is None else out[..., rows]
                errs = {name: normalized_error(cmp, ref) for name, ref in refs.items()}
                best = min(errs, key=errs.get)
                frac = 1.0 if rows is None else len(rows) / leaf["out"]["ne"][0]
                detail = f"matched {best}; " + ", ".join(f"{k}={v:.1e}" for k, v in errs.items())
                return OpResult(op, False, errs[best] <= tol.for_op(op), errs[best], detail, frac)
            elif op == "ROPE":
                ref = op_rope(a, srcs[1], params)
            elif op == "SOFT_MAX":
                mask = _to_f64(srcs[1]) if len(srcs) > 1 and srcs[1] is not None else None
                ref = op_soft_max(a, mask, params)
            elif leaf["op_name"] == "GLU":
                ref = op_glu(a, _to_f64(srcs[1]) if len(srcs) > 1 and srcs[1] is not None else None, params)
            elif leaf["op_name"] == "UNARY":
                ref = op_unary(a, op)
            else:
                return OpResult(op, False, False, math.inf, UNSUPPORTED)
        err = normalized_error(out, ref)
        return OpResult(op, False, err <= tol.for_op(op), err)
    except OpError as e:
        return OpResult(op, False, False, math.inf, f"{UNSUPPORTED}: {e}")
    except (IndexError, ValueError, TypeError) as e:
        return OpResult(op, False, False, math.inf, f"error: {e}")
