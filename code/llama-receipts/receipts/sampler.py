"""Deterministic, replayable sampler.

The randomness for position t is u_t = H(seed, t), so a verifier can redo
the exact draw without sharing RNG state. Ties are broken by token id so the
same logits always give the same token on any platform.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

import numpy as np

DOMAIN = b"llama-receipts/u/v1/"


@dataclass(frozen=True)
class SamplerConfig:
    temperature: float = 0.7
    top_k: int = 40
    top_p: float = 0.95
    seed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> SamplerConfig:
        return cls(
            temperature=float(d["temperature"]),
            top_k=int(d["top_k"]),
            top_p=float(d["top_p"]),
            seed=int(d["seed"]),
        )


@dataclass(frozen=True)
class SampleResult:
    token: int
    logprob: float  # log-prob under the distribution the sampler actually drew from
    logprob_full: float  # log-prob under the full temperature-scaled softmax
    u: float | None  # the uniform draw, None for greedy
    boundary_distance: float | None  # how far u sat from the nearest CDF edge
    candidates: list[tuple[int, float]]  # top tokens with their sampling probs


def uniform_at(seed: int, position: int) -> float:
    """Uniform in [0, 1) derived from (seed, position) with SHA-256."""
    msg = DOMAIN + seed.to_bytes(8, "big") + position.to_bytes(8, "big")
    digest = hashlib.sha256(msg).digest()
    return int.from_bytes(digest[:8], "big") / 2.0**64


def log_softmax(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float64)
    m = x.max()
    z = np.log(np.exp(x - m).sum()) + m
    return x - z


def _ordered_ids(x: np.ndarray) -> np.ndarray:
    """Token ids sorted by score descending, ties broken by id ascending."""
    ids = np.arange(x.shape[0])
    return np.lexsort((ids, -x))


def sampling_distribution(logits: np.ndarray, cfg: SamplerConfig) -> tuple[np.ndarray, np.ndarray]:
    """Return (ordered token ids, probabilities) after temperature, top-k, top-p."""
    x = logits.astype(np.float64) / cfg.temperature
    order = _ordered_ids(x)
    if cfg.top_k > 0:
        order = order[: cfg.top_k]
    probs = np.exp(x[order] - x[order].max())
    probs /= probs.sum()
    if 0.0 < cfg.top_p < 1.0:
        cum = np.cumsum(probs)
        keep = int(np.searchsorted(cum, cfg.top_p, side="left")) + 1
        order, probs = order[:keep], probs[:keep]
        probs = probs / probs.sum()
    return order, probs


def sample(logits: np.ndarray, cfg: SamplerConfig, position: int, top_n: int = 10) -> SampleResult:
    """Draw the token for `position` from `logits` under `cfg`."""
    if cfg.temperature <= 0.0:
        return _greedy(logits, top_n)
    order, probs = sampling_distribution(logits, cfg)
    u = uniform_at(cfg.seed, position)
    cum = np.cumsum(probs)
    idx = int(np.searchsorted(cum, u, side="right"))
    idx = min(idx, len(order) - 1)
    token = int(order[idx])
    lower = float(cum[idx - 1]) if idx > 0 else 0.0
    boundary = min(float(cum[idx]) - u, u - lower)
    full = log_softmax(logits.astype(np.float64) / cfg.temperature)
    cands = [(int(t), float(p)) for t, p in zip(order[:top_n], probs[:top_n])]
    return SampleResult(token, float(np.log(probs[idx])), float(full[token]), u, boundary, cands)


def _greedy(logits: np.ndarray, top_n: int) -> SampleResult:
    x = logits.astype(np.float64)
    order = _ordered_ids(x)
    token = int(order[0])
    full = log_softmax(x)
    cands = [(int(t), float(np.exp(full[t]))) for t in order[:top_n]]
    return SampleResult(token, 0.0, float(full[token]), None, None, cands)


def cdf_interval(logits: np.ndarray, cfg: SamplerConfig, token: int) -> tuple[float, float] | None:
    """The [lo, hi) slice of the unit interval that draws `token`, or None if truncated away."""
    if cfg.temperature <= 0.0:
        return None
    order, probs = sampling_distribution(logits, cfg)
    hits = np.flatnonzero(order == token)
    if not len(hits):
        return None
    cum = np.cumsum(probs)
    i = int(hits[0])
    return (float(cum[i - 1]) if i > 0 else 0.0, float(cum[i]))


def draw_gap(logits: np.ndarray, cfg: SamplerConfig, token: int, u: float | None) -> float | None:
    """How far `u` sits outside the interval that would have drawn `token` (0 if inside)."""
    if u is None:
        return None
    iv = cdf_interval(logits, cfg, token)
    if iv is None:
        return None
    lo, hi = iv
    if lo <= u < hi:
        return 0.0
    return lo - u if u < lo else u - hi


def logprob_of(logits: np.ndarray, cfg: SamplerConfig, token: int) -> float:
    """Log-prob of `token` under the sampling distribution; -inf if truncated away."""
    if cfg.temperature <= 0.0:
        return 0.0 if int(_ordered_ids(logits.astype(np.float64))[0]) == token else float("-inf")
    order, probs = sampling_distribution(logits, cfg)
    hits = np.flatnonzero(order == token)
    return float(np.log(probs[hits[0]])) if len(hits) else float("-inf")
