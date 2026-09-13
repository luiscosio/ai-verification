"""Verify a receipt by recomputing the generation (Token-DiFR style).

Three checks, cheapest first:
1. signature: the receipt body is intact and signed by the claimed key;
2. model: the GGUF on disk hashes to what the receipt claims;
3. replay: feed the claimed tokens through the model and re-run the seeded
   sampler at every position; count how often it would have picked the same
   token, and how far the claimed token sits from what we see.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from receipts import receipt as receipt_mod
from receipts.engine import Engine, EngineOptions
from receipts.model_commit import file_sha256, gguf_commitment
from receipts.prove import logits_hash
from receipts.sampler import SamplerConfig, draw_gap, logprob_of, sample
from receipts.trace import TraceDoc, load_trace, sidecar_path
from receipts.verify_trace import verify_trace

HARD_GAP = 0.10  # reported only: draws this far (in CDF mass) from the claimed token's interval


@dataclass
class Thresholds:
    """Accept limits for the drift regime (logits not bit-identical).

    Calibrated on testset/results.md: honest Metal-to-CPU replay of a Q4_K_M
    1.5B model reached mean gap 0.022 and max gap 0.43 over 48 tokens, so the
    margins are thin. Same-backend replay is bit-exact and uses a strict rule.
    """

    min_token_match: float = 0.75
    max_mean_abs_dlogprob: float = 0.25
    max_claimed_truncated: int = 0
    max_mean_gap: float = 0.03  # mismatch gaps summed over all positions / n
    max_gap: float = 0.45  # largest single draw gap


def check_structure(rec: dict) -> tuple[bool, str]:
    """Cheap consistency checks before spending GPU time on a replay."""
    try:
        prompt = rec["request"]["prompt_tokens"]
        tokens = rec["response"]["tokens"]
        per = rec["response"]["per_token"]
        SamplerConfig.from_dict(rec["request"]["sampler"])
    except (KeyError, TypeError, ValueError) as e:
        return False, f"missing field: {e}"
    if not tokens:
        return False, "empty response"
    if len(per) != len(tokens):
        return False, "per_token length differs from tokens"
    token_commitment = receipt_mod.receipt_digest({"prompt": prompt, "response": tokens})
    content_commitment = receipt_mod.receipt_digest({"prompt_text": rec["request"]["prompt_text"], "response_text": rec["response"]["text"]})
    if rec.get("commitments", {}).get("tokens_sha256") != token_commitment:
        return False, "token commitment mismatch"
    if rec.get("commitments", {}).get("content_sha256") != content_commitment:
        return False, "content commitment mismatch"
    for i, (t, p) in enumerate(zip(tokens, per)):
        if p["token"] != t:
            return False, f"per_token[{i}].token differs from tokens[{i}]"
        if p["position"] != len(prompt) + i:
            return False, f"per_token[{i}].position is not prompt length + {i}"
    return True, "ok"


def verify_model(rec: dict, model_path: str, full: bool = False) -> dict:
    claimed = rec["model"]
    got_file = file_sha256(Path(model_path))
    out = {"file_sha256_match": got_file == claimed["file_sha256"], "file_sha256": got_file}
    if full:
        commit = gguf_commitment(model_path)
        out["tensor_merkle_root_match"] = commit["tensor_merkle_root"] == claimed["tensor_merkle_root"]
    return out


def _replay_logits(engine: Engine, prompt: list[int], response: list[int], mode: str) -> list[np.ndarray]:
    if mode == "batched":
        arr = engine.logits_for_sequence(prompt + response, len(prompt))
        return [arr[i] for i in range(len(response))]
    engine.reset()
    out = [engine.feed(prompt)]
    for tok in response[:-1]:
        out.append(engine.feed([tok]))
    return out


def replay(engine: Engine, rec: dict, mode: str = "incremental") -> dict:
    """Recompute every generated position and compare with the receipt."""
    prompt = rec["request"]["prompt_tokens"]
    response = rec["response"]["tokens"]
    cfg = SamplerConfig.from_dict(rec["request"]["sampler"])
    per = rec["response"]["per_token"]
    logits_list = _replay_logits(engine, prompt, response, mode)
    rows = []
    for i, (claimed, logits) in enumerate(zip(per, logits_list)):
        res = sample(logits, cfg, claimed["position"])
        lp_claimed_here = logprob_of(logits, cfg, claimed["token"])
        rows.append({
            "i": i,
            "claimed": claimed["token"],
            "replayed": res.token,
            "match": res.token == claimed["token"],
            "logits_hash_match": logits_hash(logits) == claimed["logits_sha256"],
            "claimed_logprob": claimed["logprob"],
            "replay_logprob_of_claimed": lp_claimed_here,
            "abs_dlogprob": abs(lp_claimed_here - claimed["logprob"]) if math.isfinite(lp_claimed_here) else None,
            "boundary_distance": res.boundary_distance,
            "claimed_gap": draw_gap(logits, cfg, claimed["token"], res.u),
        })
    return {"mode": mode, "rows": rows, "summary": summarize(rows)}


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    deltas = [r["abs_dlogprob"] for r in rows if r["abs_dlogprob"] is not None]
    mismatches = [r for r in rows if not r["match"]]
    mismatch_bounds = [m["boundary_distance"] for m in mismatches if m["boundary_distance"] is not None]
    gaps = [m["claimed_gap"] for m in mismatches if m.get("claimed_gap") is not None]
    return {
        "n": n,
        "token_match_rate": sum(r["match"] for r in rows) / n,
        "logits_hash_match_rate": sum(r["logits_hash_match"] for r in rows) / n,
        "n_claimed_truncated": sum(1 for r in rows if r["abs_dlogprob"] is None),
        "mean_abs_dlogprob": float(np.mean(deltas)) if deltas else None,
        "max_abs_dlogprob": float(np.max(deltas)) if deltas else None,
        "first_mismatch": mismatches[0]["i"] if mismatches else None,
        "mismatch_boundary_median": float(np.median(mismatch_bounds)) if mismatch_bounds else None,
        "mismatch_gap_median": float(np.median(gaps)) if gaps else None,
        "mismatch_gap_max": float(np.max(gaps)) if gaps else None,
        "mean_gap_all": float(sum(gaps) / n),
        "n_hard_mismatch": sum(1 for g in gaps if g > HARD_GAP),
    }


def decide(sig_ok: bool, model_ok: bool, struct: tuple[bool, str], s: dict, th: Thresholds) -> tuple[str, str]:
    if not sig_ok:
        return "reject", "signature"
    if not struct[0]:
        return "reject", f"malformed receipt: {struct[1]}"
    if not model_ok:
        return "reject", "model hash mismatch"
    if s.get("n", 0) == 0:
        return "reject", "empty response"
    if s["n_claimed_truncated"] > th.max_claimed_truncated:
        return "reject", f"{s['n_claimed_truncated']} claimed tokens outside the sampler's support"
    if s["logits_hash_match_rate"] == 1.0:
        # Exact regime: same logits and same draws must give the same tokens.
        if s["token_match_rate"] < 1.0:
            n_bad = round((1 - s["token_match_rate"]) * s["n"])
            return "reject", f"logits are bit-identical but the sampler disagrees at {n_bad} positions"
        return "accept", "bit-exact replay"
    # Drift regime: logits differ (other backend, batched replay), so tolerate small gaps.
    if s["mismatch_gap_max"] is not None and s["mismatch_gap_max"] > th.max_gap:
        return "reject", f"a draw sits {s['mismatch_gap_max']:.2f} of CDF mass from the claimed token (> {th.max_gap})"
    if s["mean_gap_all"] > th.max_mean_gap:
        return "reject", f"mean draw gap {s['mean_gap_all']:.4f} > {th.max_mean_gap}"
    if s["token_match_rate"] < th.min_token_match:
        return "reject", f"token match {s['token_match_rate']:.3f} < {th.min_token_match}"
    if s["mean_abs_dlogprob"] is not None and s["mean_abs_dlogprob"] > th.max_mean_abs_dlogprob:
        return "reject", f"mean |dlogprob| {s['mean_abs_dlogprob']:.3f} > {th.max_mean_abs_dlogprob}"
    return "accept", "within backend drift"


def verify(
    rec: dict,
    model_path: str,
    opts: EngineOptions | None = None,
    mode: str = "incremental",
    full_model_check: bool = False,
    th: Thresholds | None = None,
    engine: Engine | None = None,
    trace_doc: TraceDoc | None = None,
    expected_topology_sha256: str | None = None,
    min_openings: int = 32,
) -> dict:
    """Verify a receipt.

    `mode` is "incremental" or "batched" for a full replay, or "trace" to skip
    the replay and judge the receipt on its signature, model hash, and the
    activation trace alone (rung 4, no model execution). A trace, when given,
    is checked in every mode and a failing trace rejects the receipt.
    """
    th = th or Thresholds()
    sig_ok, sig_reason = receipt_mod.check_signature(rec)
    struct = check_structure(rec)
    model = verify_model(rec, model_path, full_model_check)
    model_ok = model["file_sha256_match"] and model.get("tensor_merkle_root_match", True)
    trace_res = None
    if trace_doc is not None and struct[0]:
        trace_res = verify_trace(rec, trace_doc, model_path, expected_topology_sha256=expected_topology_sha256,
                                 min_openings=min_openings)
    if mode == "trace":
        rep = {"mode": mode, "rows": [], "summary": {"n": 0}}
        verdict, reason = decide_trace_only(sig_ok, model_ok, struct, trace_res)
    else:
        if struct[0]:
            engine = engine or Engine(model_path, opts)
            rep = replay(engine, rec, mode)
        else:
            rep = {"mode": mode, "rows": [], "summary": {"n": 0}}
        verdict, reason = decide(sig_ok, model_ok, struct, rep["summary"], th)
        if verdict == "accept" and trace_res is not None and trace_res["verdict"] != "accept":
            verdict, reason = "reject", f"trace: {trace_res['reason']}"
        elif verdict == "accept" and trace_res is not None:
            reason = f"{reason}; trace verified"
    return {
        "verdict": verdict,
        "reason": reason,
        "signature": {"ok": sig_ok, "reason": sig_reason},
        "structure": {"ok": struct[0], "reason": struct[1]},
        "model": model,
        "replay": rep,
        "trace": trace_res,
    }


def decide_trace_only(sig_ok: bool, model_ok: bool, struct: tuple[bool, str], trace_res: dict | None) -> tuple[str, str]:
    if not sig_ok:
        return "reject", "signature"
    if not struct[0]:
        return "reject", f"malformed receipt: {struct[1]}"
    if not model_ok:
        return "reject", "model hash mismatch"
    if trace_res is None:
        return "reject", "no trace to verify"
    if trace_res["verdict"] != "accept":
        return "reject", f"trace: {trace_res['reason']}"
    return "accept", "trace verified, no replay"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify an inference receipt by recomputation.")
    p.add_argument("receipt")
    p.add_argument("--model", help="GGUF to verify against (defaults to the receipt's file name in --model-dir)")
    p.add_argument("--mode", choices=["incremental", "batched", "trace"], default="incremental",
                   help="replay mode, or 'trace' to verify the activation trace without running the model")
    p.add_argument("--trace", help="trace sidecar (default: <receipt>.trace.json.gz when it exists)")
    p.add_argument("--expected-topology-sha256", help="trusted topology digest required when checking a trace")
    p.add_argument("--min-openings", type=int, default=32, help="minimum challenge openings required by verifier policy")
    p.add_argument("--full-model-check", action="store_true", help="also recompute the tensor Merkle root")
    p.add_argument("--n-gpu-layers", type=int, default=-1)
    p.add_argument("--n-threads", type=int, default=None)
    p.add_argument("--n-ctx", type=int, default=1024)
    p.add_argument("--out", help="write the full verification report here")
    a = p.parse_args(argv)
    rec = receipt_mod.load(a.receipt)
    opts = EngineOptions(n_gpu_layers=a.n_gpu_layers, n_threads=a.n_threads, n_ctx=a.n_ctx)
    trace_path = Path(a.trace) if a.trace else sidecar_path(a.receipt)
    trace_doc = load_trace(trace_path) if trace_path.exists() else None
    if a.mode == "trace" and trace_doc is None:
        print(f"no trace sidecar at {trace_path}")
        return 2
    result = verify(rec, a.model, opts, a.mode, a.full_model_check, trace_doc=trace_doc,
                    expected_topology_sha256=a.expected_topology_sha256, min_openings=a.min_openings)
    s = result["replay"]["summary"]
    print(f"verdict: {result['verdict']} ({result['reason']})")
    if result.get("trace"):
        t = result["trace"]
        bad = [n for n, c in t.get("checks", {}).items() if not c["ok"]]
        cov = t.get("coverage", {})
        print(f"trace: {t['verdict']}; {cov.get('k')} openings over {cov.get('n_leaves')} leaves in {cov.get('n_graphs')} graphs; "
              f"failed checks: {bad or 'none'}; {t.get('seconds', {}).get('total')}s")
    print(f"signature: {result['signature']['reason']}; structure: {result['structure']['reason']}; "
          f"model file hash match: {result['model']['file_sha256_match']}")
    if s.get("n"):
        print(f"tokens: {s['n']}  match rate: {s['token_match_rate']:.3f}  logits-hash match: {s['logits_hash_match_rate']:.3f}  "
              f"mean|dlogprob|: {s['mean_abs_dlogprob']}  truncated: {s['n_claimed_truncated']}  "
              f"mean gap: {s['mean_gap_all']:.4f}  max gap: {s['mismatch_gap_max']}")
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=1))
    return 0 if result["verdict"] == "accept" else 1


if __name__ == "__main__":
    raise SystemExit(main())
