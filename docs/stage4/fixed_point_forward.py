#!/usr/bin/env python3
"""Reference implementation of the circuit-friendly execution mode (candidate stmt/v1) for
qwen3 models in GGUF: one next-token forward pass in integer arithmetic only.

    python3 fixed_point_forward.py model.gguf receipt.json [receipt2.json ...] [--frac 16] [--report out.json]

Every receipt supplies prompt tokens and the token llama.cpp's float path chose greedily. The
reference recomputes the next token in fixed point and reports agreement, the logit margin,
and the largest magnitude every operation produced, which fixes the bit widths a circuit
needs. Nothing here is float at run time except the one-time derivation of constants (scales,
norm weights, RoPE and exp tables), which a registration would publish as integers.

Conventions. Activations are integers with F fraction bits (x = X / 2^F). Constants are
integers with S = 24 fraction bits. Matmuls use ggml's signed-maximum Q8_K convention with integer division and
fixed-point scales, then run ggml's integer core (the Lean spec's s1, s2,
dotQ6); the per-block scales are applied as integers with one rounding per output element.
Divisions round half to even; square roots are integer square roots. Softmax and SiLU use an
exponential built from a 4096-entry table of 2^(f/4096) plus shifts.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code" / "llama.cpp" / "examples" / "receipts"))
sys.path.insert(1, str(ROOT / "code" / "llama.cpp" / "gguf-py"))
import verify_trace as vt  # noqa: E402
from gguf import GGUFReader  # noqa: E402

S = 24                 # fraction bits of constants
EXP_TABLE_BITS = 12    # 2^(f/4096) table
QK_K = 256
STATS: dict[str, int] = {}


def note(op: str, arr) -> None:
    m = int(np.max(np.abs(np.asarray(arr, dtype=object)))) if np.asarray(arr).size else 0
    STATS[op] = max(STATS.get(op, 0), m)


def rdiv(a: int, b: int) -> int:
    """Round-half-even integer division for Python ints (b > 0)."""
    q, r = divmod(a, b)
    twice = 2 * r
    if twice > b or (twice == b and q % 2 == 1):
        q += 1
    return q


def rshift(a, n: int):
    """Round-half-even right shift, elementwise for object arrays or ints."""
    if isinstance(a, np.ndarray):
        return np.vectorize(lambda x: rdiv(int(x), 1 << n), otypes=[object])(a)
    return rdiv(int(a), 1 << n)


def isqrt(n: int) -> int:
    return math.isqrt(n)


def const(x: float) -> int:
    return int(round(x * (1 << S)))


class Consts:
    def __init__(self, frac: int):
        self.F = frac
        self.exp_table = [int(round((2.0 ** (f / (1 << EXP_TABLE_BITS))) * (1 << frac))) for f in range(1 << EXP_TABLE_BITS)]
        self.log2e = const(math.log2(math.e))

    def exp_neg(self, z: int) -> int:
        """exp(z) for z <= 0 in F fraction bits, as an integer with F fraction bits."""
        F = self.F
        if z >= 0:
            return 1 << F
        t = rdiv(z * self.log2e, 1 << S)          # z * log2(e), F fraction bits, negative
        n = -((-t) >> F)                          # floor toward -inf: n <= t/2^F
        n = t >> F                                # Python >> floors
        f = t - (n << F)                          # 0 <= f < 2^F
        base = self.exp_table[f >> (F - EXP_TABLE_BITS)] if F >= EXP_TABLE_BITS else self.exp_table[f << (EXP_TABLE_BITS - F)]
        shift = -n
        return rdiv(base, 1 << shift) if shift < 64 else 0

    def sigmoid(self, x: int) -> int:
        F = self.F
        one = 1 << F
        if x >= 0:
            e = self.exp_neg(-x)
            return rdiv(one * one, one + e)
        e = self.exp_neg(x)
        return rdiv(e * one, one + e)


class Model:
    def __init__(self, path: str, frac: int):
        self.F = frac
        self.store = vt.WeightStore(path)
        r = self.store.reader
        arch = self.field(r, "general.architecture")
        assert arch == "qwen3", f"this reference covers qwen3, got {arch}"
        self.n_layer = int(self.field(r, "qwen3.block_count"))
        self.n_embd = int(self.field(r, "qwen3.embedding_length"))
        self.n_head = int(self.field(r, "qwen3.attention.head_count"))
        self.n_head_kv = int(self.field(r, "qwen3.attention.head_count_kv"))
        self.head_dim = int(self.field(r, "qwen3.attention.key_length"))
        self.eps = float(self.field(r, "qwen3.attention.layer_norm_rms_epsilon"))
        self.rope_base = float(self.field(r, "qwen3.rope.freq_base"))
        self.C = Consts(frac)
        self.eps_fp = int(round(self.eps * (1 << (2 * frac))))
        self.attn_scale = const(1.0 / math.sqrt(self.head_dim))
        self.f32 = {}
        self.types = {t.name: t.tensor_type.name for t in r.tensors}
        self.rope_cache: dict[int, tuple[list[int], list[int]]] = {}

    @staticmethod
    def field(r, name):
        f = r.fields[name]
        part = f.parts[f.data[0]]
        if f.types and f.types[0].name == "STRING":
            return bytes(part).decode()
        return part.tolist()[0]

    def vec_f32(self, name: str) -> np.ndarray:
        if name not in self.f32:
            t = self.store.tensors[name]
            self.f32[name] = np.array(t.data, dtype=np.float32).reshape(-1)
        return self.f32[name]

    def consts_vec(self, name: str) -> np.ndarray:
        return np.array([const(float(x)) for x in self.vec_f32(name)], dtype=object)

    # --- integer building blocks -------------------------------------------------------------
    def rms_norm(self, x: np.ndarray, w: np.ndarray) -> np.ndarray:
        F = self.F
        n = len(x)
        ms = rdiv(int(sum(int(v) * int(v) for v in x)), n)             # mean(x^2) * 2^2F
        r = isqrt(ms + self.eps_fp)                                    # rms * 2^F
        y = np.array([rdiv(int(v) << F, r) for v in x], dtype=object)  # x / rms, F bits
        out = np.array([rdiv(int(a) * int(b), 1 << S) for a, b in zip(y, w)], dtype=object)
        note("RMS_NORM", out)
        return out

    def quantize_q8k(self, x: np.ndarray) -> tuple[list[int], np.ndarray, np.ndarray]:
        """ggml's Q8_K from a fixed-point vector: per 256-block, iscale = -127/amax, q = rint(iscale*x).
        Returns the per-block d_a as fixed point (F bits), the quants, and the 16-wide block sums."""
        F = self.F
        K = len(x)
        nb = K // QK_K
        d_a, q8, bsums = [], np.zeros(K, dtype=np.int64), np.zeros((nb, 16), dtype=np.int64)
        for i in range(nb):
            blk = [int(v) for v in x[i * QK_K:(i + 1) * QK_K]]
            amax = max(blk, key=abs)
            if amax == 0:
                d_a.append(0)
                continue
            # q = rint(-127 * x / amax); d = amax / -127
            sign = 1 if amax > 0 else -1
            qs = [rdiv(-127 * v * sign, abs(amax)) for v in blk]
            q8[i * QK_K:(i + 1) * QK_K] = qs
            d_a.append(rdiv(-amax, 127))                                # F fraction bits (amax has F bits)
            bsums[i] = np.array(qs, dtype=np.int64).reshape(16, 16).sum(axis=1)
        return d_a, q8, bsums

    def matmul(self, name: str, x: np.ndarray) -> np.ndarray:
        """out[m] = sum_k W[m,k] x[k] with W a Q4_K or Q6_K tensor, ggml's integer core, integer scale application."""
        F = self.F
        blocks = self.store.blocks(name)
        M = blocks.shape[0]
        K = len(x)
        nb = K // QK_K
        d_a, q8, bsums = self.quantize_q8k(x)
        t = self.types[name]
        out = np.zeros(M, dtype=object)
        if t == "Q4_K":
            d_w, dmin, sc, mn, q4 = vt.unpack_q4_k(blocks)             # (M,nb) (M,nb) (M,nb,8) (M,nb,8) (M,nb*256)
            q4b = q4.reshape(M, nb, 8, 32).astype(np.int64)
            q8b = q8.reshape(nb, 8, 32).astype(np.int64)
            sub = np.einsum("mijl,ijl->mij", q4b, q8b)
            s1 = np.einsum("mij,mij->mi", sub, sc.astype(np.int64))
            s2 = np.einsum("ij,mij->mi", bsums, np.repeat(mn.astype(np.int64), 2, axis=-1))
            D = np.vectorize(lambda v: const(float(v)), otypes=[object])(d_w)
            Dm = np.vectorize(lambda v: const(float(v)), otypes=[object])(dmin)
            for m in range(M):
                acc = 0
                for i in range(nb):
                    acc += d_a[i] * (int(D[m, i]) * int(s1[m, i]) - int(Dm[m, i]) * int(s2[m, i]))
                out[m] = rdiv(acc, 1 << S)
        elif t == "Q6_K":
            d_w, scales, q6 = vt.unpack_q6_k(blocks)                    # (M,nb) (M,nb,16) (M,nb*256)
            q6b = q6.reshape(M, nb, 16, 16).astype(np.int64)
            q8b = q8.reshape(nb, 16, 16).astype(np.int64)
            dot = np.einsum("mijl,ijl->mij", q6b, q8b)
            dot = np.einsum("mij,mij->mi", dot, scales.astype(np.int64))
            D = np.vectorize(lambda v: const(float(v)), otypes=[object])(d_w)
            for m in range(M):
                acc = 0
                for i in range(nb):
                    acc += d_a[i] * int(D[m, i]) * int(dot[m, i])
                out[m] = rdiv(acc, 1 << S)
        else:
            raise ValueError(f"{name}: type {t} not covered")
        note("MUL_MAT", out)
        return out

    def embed(self, tok: int) -> np.ndarray:
        """Row `tok` of token_embd (Q6_K) as fixed point: d * scale * q6 per block."""
        F = self.F
        blocks = self.store.blocks("token_embd.weight")[tok:tok + 1]
        d_w, scales, q6 = vt.unpack_q6_k(blocks)
        nb = self.n_embd // QK_K
        D = [const(float(v)) for v in d_w[0]]
        q6 = q6.reshape(nb, 16, 16).astype(np.int64)
        out = []
        for i in range(nb):
            for j in range(16):
                for l in range(16):
                    out.append(rdiv(D[i] * int(scales[0, i, j]) * int(q6[i, j, l]) << F, 1 << S))
        arr = np.array(out, dtype=object)
        note("GET_ROWS", arr)
        return arr

    def rope_tables(self, pos: int) -> tuple[list[int], list[int]]:
        if pos not in self.rope_cache:
            half = self.head_dim // 2
            cos, sin = [], []
            for i in range(half):
                theta = pos * self.rope_base ** (-2.0 * i / self.head_dim)
                cos.append(const(math.cos(theta)))
                sin.append(const(math.sin(theta)))
            self.rope_cache[pos] = (cos, sin)
        return self.rope_cache[pos]

    def rope(self, x: np.ndarray, pos: int) -> np.ndarray:
        """neox rotation on one head vector: pairs (i, i + half)."""
        half = self.head_dim // 2
        cos, sin = self.rope_tables(pos)
        out = np.zeros(self.head_dim, dtype=object)
        for i in range(half):
            a, b = int(x[i]), int(x[i + half])
            out[i] = rdiv(a * cos[i] - b * sin[i], 1 << S)
            out[i + half] = rdiv(a * sin[i] + b * cos[i], 1 << S)
        note("ROPE", out)
        return out

    def head_norm(self, v: np.ndarray, w: np.ndarray) -> np.ndarray:
        return self.rms_norm(v, w)

    # --- the forward pass ---------------------------------------------------------------------
    def forward(self, tokens: list[int]) -> tuple[int, np.ndarray]:
        F = self.F
        n = len(tokens)
        C = self.C
        h = [self.embed(t) for t in tokens]
        kv_ratio = self.n_head // self.n_head_kv
        for l in range(self.n_layer):
            attn_norm = self.consts_vec(f"blk.{l}.attn_norm.weight")
            q_norm = self.consts_vec(f"blk.{l}.attn_q_norm.weight")
            k_norm = self.consts_vec(f"blk.{l}.attn_k_norm.weight")
            ffn_norm = self.consts_vec(f"blk.{l}.ffn_norm.weight")
            Q, Kc, V = [], [], []
            for p in range(n):
                cur = self.rms_norm(h[p], attn_norm)
                q = self.matmul(f"blk.{l}.attn_q.weight", cur).reshape(self.n_head, self.head_dim)
                k = self.matmul(f"blk.{l}.attn_k.weight", cur).reshape(self.n_head_kv, self.head_dim)
                v = self.matmul(f"blk.{l}.attn_v.weight", cur).reshape(self.n_head_kv, self.head_dim)
                q = np.array([self.rope(self.head_norm(q[hh], q_norm), p) for hh in range(self.n_head)], dtype=object)
                k = np.array([self.rope(self.head_norm(k[hh], k_norm), p) for hh in range(self.n_head_kv)], dtype=object)
                Q.append(q); Kc.append(k); V.append(v)
            attn_out = []
            for p in range(n):
                heads = []
                for hh in range(self.n_head):
                    kvh = hh // kv_ratio
                    scores = []
                    for j in range(p + 1):
                        dot = int(sum(int(a) * int(b) for a, b in zip(Q[p][hh], Kc[j][kvh])))   # 2F bits
                        scores.append(rdiv(dot * self.attn_scale, 1 << (S + F)))                  # F bits
                    note("KQ", scores)
                    mx = max(scores)
                    e = [C.exp_neg(s - mx) for s in scores]
                    tot = sum(e)
                    probs = [rdiv(x << F, tot) for x in e]
                    o = np.zeros(self.head_dim, dtype=object)
                    for j in range(p + 1):
                        if probs[j]:
                            o = o + np.array([probs[j] * int(x) for x in V[j][kvh]], dtype=object)
                    heads.append(rshift(o, F))
                attn = np.concatenate(heads)
                note("FLASH_ATTN_EXT", attn)
                attn_out.append(attn)
            for p in range(n):
                cur = self.matmul(f"blk.{l}.attn_output.weight", attn_out[p])
                ffn_inp = h[p] + cur
                note("ADD", ffn_inp)
                cur = self.rms_norm(ffn_inp, ffn_norm)
                gate = self.matmul(f"blk.{l}.ffn_gate.weight", cur)
                up = self.matmul(f"blk.{l}.ffn_up.weight", cur)
                act = np.array([rdiv(rdiv(int(g) * C.sigmoid(int(g)), 1 << F) * int(u), 1 << F) for g, u in zip(gate, up)], dtype=object)
                note("SWIGLU", act)
                down = self.matmul(f"blk.{l}.ffn_down.weight", act)
                h[p] = ffn_inp + down
                note("ADD", h[p])
        cur = self.rms_norm(h[n - 1], self.consts_vec("output_norm.weight"))
        out_name = "output.weight" if "output.weight" in self.types else "token_embd.weight"
        logits = self.matmul(out_name, cur)
        best = int(np.argmax(np.array([int(v) for v in logits], dtype=np.int64)))   # argmax keeps the lowest index on ties
        return best, logits


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("model")
    p.add_argument("receipts", nargs="+")
    p.add_argument("--frac", type=int, default=20)
    p.add_argument("--report")
    a = p.parse_args(argv)
    if not 12 <= a.frac <= 24:
        p.error("--frac must be between 12 and 24")
    model = Model(a.model, a.frac)
    rows = []
    agree = 0
    for rp in a.receipts:
        rec = json.loads(Path(rp).read_text())
        toks = rec["request"]["prompt_tokens"]
        want = rec["response"]["tokens"][0]
        t = time.time()
        got, logits = model.forward(toks)
        li = np.array([int(v) for v in logits], dtype=np.int64)
        top2 = np.sort(li)[-2:]
        margin = (int(top2[1]) - int(top2[0])) / (1 << a.frac)
        ok = got == want
        agree += ok
        rows.append({"receipt": rp, "n_prompt": len(toks), "llama_cpp_token": want, "fixed_point_token": got, "agree": ok,
                     "fixed_point_margin": margin, "llama_logit_of_ours": None, "seconds": round(time.time() - t, 1)})
        print(f"{Path(rp).name}: {len(toks)} prompt tokens, llama.cpp {want}, fixed point {got}, {'agree' if ok else 'DIFFER'}, margin {margin:.3f}, {time.time() - t:.1f}s")
    widths = {op: (m, m.bit_length()) for op, m in STATS.items()}
    print(f"agreement: {agree} of {len(rows)}")
    print("largest magnitudes (fixed point, bits):", {op: b for op, (m, b) in widths.items()})
    if a.report:
        Path(a.report).write_text(json.dumps({"model": a.model, "frac_bits": a.frac, "const_bits": S, "exp_table_bits": EXP_TABLE_BITS,
                                              "agreement": agree, "n": len(rows), "cases": rows,
                                              "max_abs": {op: str(m) for op, (m, b) in widths.items()}, "bits": {op: b for op, (m, b) in widths.items()}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
