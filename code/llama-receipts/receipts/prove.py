"""Generate text and emit a signed inference receipt.

The receipt commits to the model file, the exact token sequence, the sampler
settings and seed, the per-position uniform draws, and a hash of the logits
at every generated position. With `--trace` it also commits to a Merkle root
over every intermediate tensor of the forward pass and writes a sidecar with
the leaves and Fiat-Shamir sampled openings (rung 4).
"""

from __future__ import annotations

import argparse
import hashlib
import time
from dataclasses import dataclass, field

import numpy as np

from receipts import RECEIPT_VERSION, keys, receipt
from receipts.engine import Engine, EngineOptions
from receipts.model_commit import gguf_commitment, summary
from receipts.sampler import SamplerConfig, sample
from receipts.trace import TraceDoc, Tracer, build_openings, challenge_binding, derive_indices, save_trace, sidecar_path


@dataclass
class TokenRecord:
    position: int  # absolute position in the context
    token: int
    logprob: float
    logprob_full: float
    u: float | None
    boundary_distance: float | None
    logits_sha256: str
    candidates: list[tuple[int, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "position": self.position,
            "token": self.token,
            "logprob": round(self.logprob, 6),
            "logprob_full": round(self.logprob_full, 6),
            "u": self.u,
            "boundary_distance": None if self.boundary_distance is None else round(self.boundary_distance, 9),
            "logits_sha256": self.logits_sha256,
            "candidates": [[t, round(p, 6)] for t, p in self.candidates],
        }


def logits_hash(logits: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(logits, dtype=np.float32).tobytes()).hexdigest()


def generate(
    engine: Engine,
    context_tokens: list[int],
    cfg: SamplerConfig,
    n_predict: int,
    top_n: int = 10,
    stop_at_eog: bool = True,
    position_base: int | None = None,
) -> list[TokenRecord]:
    """Decode `n_predict` tokens after `context_tokens` with our sampler.

    `context_tokens` is what the model actually sees. What the receipt claims
    it saw is the caller's business (this is how the test set models a hidden
    system prompt). `position_base` overrides the position used for the
    uniform draws, so a forged receipt can still be internally consistent.
    """
    engine.reset()
    if engine.tracer is not None:
        engine.tracer.reset()
    logits = engine.feed(context_tokens)
    base = len(context_tokens) if position_base is None else position_base
    records: list[TokenRecord] = []
    for i in range(n_predict):
        position = base + i
        res = sample(logits, cfg, position, top_n=top_n)
        records.append(TokenRecord(
            position, res.token, res.logprob, res.logprob_full, res.u,
            res.boundary_distance, logits_hash(logits), res.candidates,
        ))
        if stop_at_eog and engine.is_end_of_generation(res.token):
            break
        logits = engine.feed([res.token])
    return records


def build_receipt(
    engine: Engine,
    model_commit: dict,
    prompt_text: str,
    prompt_tokens: list[int],
    cfg: SamplerConfig,
    records: list[TokenRecord],
    n_predict: int,
) -> dict:
    out_tokens = [r.token for r in records]
    request = {
        "prompt_text": prompt_text,
        "prompt_tokens": prompt_tokens,
        "sampler": {"type": "seeded-inverse-cdf/v1", **cfg.to_dict()},
        "n_predict": n_predict,
    }
    response = {
        "tokens": out_tokens,
        "text": engine.detokenize(out_tokens),
        "per_token": [r.to_dict() for r in records],
    }
    doc = {
        "receipt_version": RECEIPT_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "engine": engine.info(),
        "model": summary(model_commit),
        "request": request,
        "response": response,
        "commitments": {
            "tokens_sha256": hashlib.sha256(
                receipt.canonical_bytes({"prompt": prompt_tokens, "response": out_tokens})
            ).hexdigest(),
            "content_sha256": hashlib.sha256(receipt.canonical_bytes({"prompt_text": request["prompt_text"], "response_text": response["text"]})).hexdigest(),
        },
    }
    if engine.tracer is not None:
        if engine.tracer.errors:
            raise RuntimeError(f"trace errors: {engine.tracer.errors[:3]}")
        doc["trace"] = engine.tracer.summary()
    return doc


def tracer_for(model_commit: dict) -> Tracer:
    return Tracer({t["name"]: t["sha256"] for t in model_commit["tensors"]})


def open_trace(engine: Engine, doc: dict, context_tokens: list[int], k: int, seed: bytes = b"") -> TraceDoc:
    """Pass two: replay the exact generation, capture the sampled leaves, and build openings.

    `context_tokens` is what the model saw in pass one (normally the prompt).
    The replay must reproduce the committed root bit for bit, which holds on a
    single backend once the KV cache is cleared between runs.
    """
    tracer = engine.tracer
    tr = doc["trace"]
    indices = derive_indices(tr["root"], challenge_binding(doc), tr["n_leaves"], k, seed)
    tracer.reset(capture=set(indices))
    engine.reset()
    engine.feed(context_tokens)
    for tok in doc["response"]["tokens"][: tr["n_graphs"] - 1]:
        engine.feed([tok])
    if tracer.errors:
        raise RuntimeError(f"trace errors during opening replay: {tracer.errors[:3]}")
    root = tracer.root()
    if root != tr["root"]:
        raise RuntimeError(f"opening replay diverged from the committed trace: {root[:16]} vs {tr['root'][:16]}")
    challenge = {"mode": "interactive" if seed else "fiat-shamir", "k": len(indices), "indices": indices, "seed": seed.hex()}
    return TraceDoc(root=root, n_graphs=tr["n_graphs"], leaves=tracer.leaves, openings=build_openings(tracer, indices),
                    challenge=challenge, topology_sha256=tr["topology_sha256"], stats=tracer.stats.to_dict())


def prove(
    model_path: str,
    prompt_text: str,
    cfg: SamplerConfig,
    n_predict: int,
    opts: EngineOptions | None = None,
    key=None,
    engine: Engine | None = None,
    trace_openings: int | None = None,
) -> dict | tuple[dict, TraceDoc]:
    """Generate and sign a receipt. With `trace_openings`, also return the trace sidecar."""
    if trace_openings is not None and trace_openings <= 0:
        raise ValueError("trace_openings must be positive")
    commit = gguf_commitment(model_path)
    if engine is None:
        engine = Engine(model_path, opts, tracer=tracer_for(commit) if trace_openings is not None else None)
    if trace_openings is not None and engine.tracer is None:
        raise ValueError("a traced receipt needs an engine built with a tracer")
    prompt_tokens = engine.tokenize(prompt_text)
    records = generate(engine, prompt_tokens, cfg, n_predict)
    doc = build_receipt(engine, commit, prompt_text, prompt_tokens, cfg, records, n_predict)
    doc = receipt.sign_receipt(doc, key or keys.load_key())
    if trace_openings is None:
        return doc
    return doc, open_trace(engine, doc, prompt_tokens, trace_openings)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate text and a signed inference receipt.")
    p.add_argument("--model", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--n-predict", type=int, default=64)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--top-k", type=int, default=40)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n-gpu-layers", type=int, default=-1)
    p.add_argument("--n-threads", type=int, default=None)
    p.add_argument("--n-ctx", type=int, default=1024)
    p.add_argument("--trace", action="store_true", help="commit to the activation trace and write <out>.trace.json.gz")
    p.add_argument("--openings", type=int, default=32, help="leaves opened for the trace challenge")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    cfg = SamplerConfig(a.temperature, a.top_k, a.top_p, a.seed)
    opts = EngineOptions(n_gpu_layers=a.n_gpu_layers, n_threads=a.n_threads, n_ctx=a.n_ctx)
    result = prove(a.model, a.prompt, cfg, a.n_predict, opts, trace_openings=a.openings if a.trace else None)
    doc, tdoc = result if isinstance(result, tuple) else (result, None)
    receipt.save(doc, a.out)
    print(doc["response"]["text"])
    print(f"\n[receipt] {len(doc['response']['tokens'])} tokens, sha256 {receipt.receipt_digest(doc)[:16]}, saved to {a.out}")
    if tdoc is not None:
        path = sidecar_path(a.out)
        save_trace(tdoc, path)
        tr = doc["trace"]
        print(f"[trace] root {tr['root'][:16]}, {tr['n_leaves']} leaves over {tr['n_graphs']} graphs, "
              f"{len(tdoc.openings)} openings, saved to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
