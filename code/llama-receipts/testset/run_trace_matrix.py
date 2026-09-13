"""Attack test set for the activation trace (rung 4).

Every case produces traced receipts and verifies them in mode "trace": no model
execution on the verifier, only hash checks on the trace and numpy
re-execution of the sampled openings. Forged cases patch the tracer's leaves
the way a prover who controls the tracer would, then re-sign.

Run:  uv run python -m testset.run_trace_matrix [--n-predict 32] [--prompts 4] [--openings 32]
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from receipts import keys, receipt
from receipts.engine import Engine, EngineOptions
from receipts.model_commit import gguf_commitment
from receipts.prove import build_receipt, generate, tracer_for
from receipts.receipt import canonical_bytes
from receipts.sampler import SamplerConfig
from receipts.trace import TraceDoc, Tracer, build_openings, challenge_binding, derive_indices, save_trace
from receipts.verify import verify
from testset.run_matrix import HIDDEN_PREFIX, MODELS, PROMPTS

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "trace"
CFG = SamplerConfig(temperature=0.7, top_k=40, top_p=0.95, seed=1234)
GPU = EngineOptions(n_gpu_layers=-1)
CPU = EngineOptions(n_gpu_layers=0, n_threads=8)


@dataclass(frozen=True)
class Case:
    name: str
    expected: str  # accept, reject, or limitation (a sparse cheat the sampling is not designed to catch)
    prove_model: str
    claim_model: str
    opts: EngineOptions
    hidden_prefix: str = ""
    forge: Callable[[Tracer, dict], None] | None = None  # mutates the tracer's leaves before the root is taken
    after_sign: Callable[[dict, TraceDoc], tuple[dict, TraceDoc]] | None = None
    also_replay: bool = False  # run the rung-3 replay too, to compare verifier cost
    note: str = ""


def forge_weight_types(tracer: Tracer, claimed_commit: dict) -> None:
    """Make the leaves describe the claimed model's tensor types; the bytes stay from the model actually run."""
    types = {t["name"]: t["type"].lower() for t in claimed_commit["tensors"]}
    for leaf in tracer.leaves:
        for s in leaf["srcs"]:
            if s["kind"] == "weight" and s["base"]["name"] in types:
                s["type"] = s["base"]["type"] = types[s["base"]["name"]]
    tracer.leaf_bytes = [canonical_bytes(x) for x in tracer.leaves]


def forge_one_node(tracer: Tracer, _commit: dict) -> None:
    """Fabricate one mid-network activation and keep every edge consistent with it."""
    target = next(i for i, x in enumerate(tracer.leaves) if x["g"] == 2 and x["name"] == "l_out-13")
    fake = hashlib.sha256(b"fabricated" + tracer.leaves[target]["out"]["base"]["sha256"].encode()).hexdigest()
    tracer.leaves[target]["out"]["base"]["sha256"] = fake
    for leaf in tracer.leaves:
        for s in leaf["srcs"]:
            if s["kind"] == "data" and s["producer"] == target:
                s["base"]["sha256"] = fake
    tracer.leaf_bytes = [canonical_bytes(x) for x in tracer.leaves]


def forge_root(doc: dict, tdoc: TraceDoc) -> tuple[dict, TraceDoc]:
    doc = copy.deepcopy(doc)
    root = bytearray.fromhex(doc["trace"]["root"])
    root[0] ^= 0x01
    doc["trace"]["root"] = root.hex()
    receipt.sign_receipt(doc, keys.load_key())
    return doc, tdoc


def edit_token_resign(doc: dict, tdoc: TraceDoc) -> tuple[dict, TraceDoc]:
    doc = copy.deepcopy(doc)
    toks = doc["response"]["tokens"]
    i = len(toks) // 3
    alt = doc["response"]["per_token"][i]["candidates"]
    new = next((t for t, _ in alt if t != toks[i]), toks[i] + 1)
    toks[i] = new
    doc["response"]["per_token"][i]["token"] = new
    doc["commitments"]["tokens_sha256"] = hashlib.sha256(
        canonical_bytes({"prompt": doc["request"]["prompt_tokens"], "response": toks})).hexdigest()
    receipt.sign_receipt(doc, keys.load_key())
    return doc, tdoc


CASES = [
    Case("TH1 honest / Metal prove, trace-only verify", "accept", "qwen", "qwen", GPU, also_replay=True,
         note="verifier holds weights but never runs the model; replay time shown for comparison"),
    Case("TH2 honest / CPU prove, trace-only verify", "accept", "qwen", "qwen", CPU,
         note="CPU kernels quantize activations to 8 bits before the dot product; tolerances must cover it"),
    Case("TA1 cheaper quant served (Q2_K), claims Q4_K_M, leaf types forged", "reject", "qwen_q2k", "qwen", GPU,
         forge=forge_weight_types, note="only the opened bytes betray it: every weight matmul re-executes wrong"),
    Case("TA2 different model served (phi3), claims qwen", "reject", "phi3", "qwen", GPU,
         note="leaves reference tensors the claimed model does not have"),
    Case("TA3 hidden system prompt", "reject", "qwen", "qwen", GPU, hidden_prefix=HIDDEN_PREFIX,
         note="the prefill graph's token input hashes to more tokens than the receipt claims"),
    Case("TA7 token edit, commitments and signature refreshed, trace untouched", "reject", "qwen", "qwen", GPU,
         after_sign=edit_token_resign, note="the decode graph that consumed the edited token has a different token input"),
    Case("TA9 single fabricated activation, edges kept consistent", "limitation", "qwen", "qwen", GPU,
         forge=forge_one_node, note="caught only when the node or a consumer is sampled; this is the sampling bound"),
    Case("TA10 signed root differs from the leaves", "reject", "qwen", "qwen", GPU, after_sign=forge_root),
]


class Engines:
    def __init__(self):
        self._cache: dict[tuple, Engine] = {}
        self._commits: dict[str, dict] = {}

    def commit(self, model_key: str) -> dict:
        if model_key not in self._commits:
            self._commits[model_key] = gguf_commitment(str(MODELS[model_key]))
        return self._commits[model_key]

    def get(self, prove_model: str, claim_model: str, opts: EngineOptions) -> Engine:
        k = (prove_model, claim_model, opts.n_gpu_layers, opts.n_threads)
        if k not in self._cache:
            hashes_from = claim_model if prove_model == "qwen_q2k" else prove_model
            self._cache[k] = Engine(str(MODELS[prove_model]), opts, tracer=tracer_for(self.commit(hashes_from)))
        return self._cache[k]


def make_traced_receipt(case: Case, prompt: str, engines: Engines, key, n_predict: int, k: int) -> tuple[dict, TraceDoc]:
    engine = engines.get(case.prove_model, case.claim_model, case.opts)
    claimed_commit = engines.commit(case.claim_model)
    claimed_prompt_tokens = engine.tokenize(prompt)
    context = engine.tokenize(case.hidden_prefix + prompt)
    records = generate(engine, context, CFG, n_predict, position_base=len(claimed_prompt_tokens))
    if case.forge:
        case.forge(engine.tracer, claimed_commit)
    doc = build_receipt(engine, claimed_commit, prompt, claimed_prompt_tokens, CFG, records, n_predict)
    receipt.sign_receipt(doc, key)
    # pass two: replay for openings, applying the same forgery so the roots agree
    tr = doc["trace"]
    indices = derive_indices(tr["root"], challenge_binding(doc), tr["n_leaves"], k)
    tracer = engine.tracer
    tracer.reset(capture=set(indices))
    engine.reset()
    engine.feed(context)
    for tok in doc["response"]["tokens"][: tr["n_graphs"] - 1]:
        engine.feed([tok])
    if case.forge:
        case.forge(tracer, claimed_commit)
    if tracer.root() != tr["root"]:
        raise RuntimeError(f"{case.name}: opening replay did not reproduce the root")
    tdoc = TraceDoc(root=tr["root"], n_graphs=tr["n_graphs"], leaves=tracer.leaves, openings=build_openings(tracer, indices),
                    challenge={"mode": "fiat-shamir", "k": k, "indices": indices, "seed": ""}, stats=tracer.stats.to_dict())
    if case.after_sign:
        doc, tdoc = case.after_sign(doc, tdoc)
    return doc, tdoc


def run_case(case: Case, engines: Engines, key, n_predict: int, prompts: list[str], k: int) -> dict:
    t0 = time.time()
    rows = []
    case_dir = OUT / case.name.split(" ")[0]
    case_dir.mkdir(parents=True, exist_ok=True)
    model_path = str(MODELS[case.claim_model])
    for i, prompt in enumerate(prompts):
        t1 = time.time()
        doc, tdoc = make_traced_receipt(case, prompt, engines, key, n_predict, k)
        t_prove = time.time() - t1
        receipt.save(doc, case_dir / f"{i}.receipt.json")
        save_trace(tdoc, case_dir / f"{i}.trace.json.gz")
        t2 = time.time()
        res = verify(doc, model_path, mode="trace", trace_doc=tdoc)
        t_verify = time.time() - t2
        (case_dir / f"{i}.verify.json").write_text(json.dumps(res, indent=1))
        row = {"prompt": i, "verdict": res["verdict"], "reason": res["reason"], "n_tokens": len(doc["response"]["tokens"]),
               "n_leaves": doc["trace"]["n_leaves"], "n_graphs": doc["trace"]["n_graphs"], "k": k,
               "prove_s": round(t_prove, 2), "verify_s": round(t_verify, 2),
               "sidecar_bytes": (case_dir / f"{i}.trace.json.gz").stat().st_size,
               "failed_checks": [n for n, c in (res.get("trace") or {}).get("checks", {}).items() if not c["ok"]],
               "worst_error": ((res.get("trace") or {}).get("checks", {}).get("openings", {}) or {}).get("worst_error"),
               "ops": ((res.get("trace") or {}).get("coverage", {}) or {}).get("ops")}
        if case.also_replay:
            # rung-3 replay on the same engine with the tracer switched off, so the comparison is fair
            engine = engines.get(case.prove_model, case.claim_model, case.opts)
            engine.tracer.enabled = False
            t3 = time.time()
            full = verify(doc, model_path, mode="incremental", engine=engine)
            row["replay_s"] = round(time.time() - t3, 2)
            engine.tracer.enabled = True
            row["replay_verdict"] = full["verdict"]
        rows.append(row)
    return {"case": case.name, "expected": case.expected, "note": case.note, "seconds": round(time.time() - t0, 1), "rows": rows}


def _fmt(x, nd=2):
    return "–" if x is None else f"{x:.{nd}e}" if nd == "e" else f"{x:.{nd}f}"


def write_markdown(results: list[dict], meta: dict) -> str:
    lines = [
        "# Activation trace (rung 4) test set results",
        "",
        f"Model under test: qwen2.5 1.5B instruct (Ollama Q4_K_M blob). Prompts: {meta['n_prompts']}. Tokens per prompt: up to "
        f"{meta['n_predict']}. Openings per receipt: {meta['k']}. Sampler: T={CFG.temperature}, top_k={CFG.top_k}, top_p={CFG.top_p}, "
        f"seed={CFG.seed}. Verifier mode: trace (no model execution). Machine: {meta['machine']}. Generated {meta['date']}.",
        "",
        "| Case | Expected | Verdicts | Leaves / graphs | Prove s | Verify s | Sidecar MB | Failed checks | Worst MUL_MAT error |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        rows = r["rows"]
        n = len(rows)
        acc = sum(x["verdict"] == "accept" for x in rows)
        if r["expected"] == "limitation":
            verdicts = f"{n - acc}/{n} caught"
        else:
            verdicts = f"{sum(x['verdict'] == r['expected'] for x in rows)}/{n} correct"
        leaves = f"{rows[0]['n_leaves']} / {rows[0]['n_graphs']}" if rows else "–"
        prove_s = sum(x["prove_s"] for x in rows) / n
        verify_s = sum(x["verify_s"] for x in rows) / n
        mb = sum(x["sidecar_bytes"] for x in rows) / n / 1e6
        failed = sorted({c for x in rows for c in x["failed_checks"]})
        worst = max((x["worst_error"] or {}).get("MUL_MAT", 0.0) for x in rows) if any(x["worst_error"] for x in rows) else None
        extra = f" (replay {sum(x.get('replay_s', 0) for x in rows) / n:.1f} s)" if any("replay_s" in x for x in rows) else ""
        lines.append(f"| {r['case']} | {r['expected']} | {verdicts} | {leaves} | {prove_s:.1f} | {verify_s:.1f}{extra} | {mb:.1f} | "
                     f"{', '.join(failed) or 'none'} | {'–' if worst is None else f'{worst:.1e}'} |")
    lines += ["", "Notes:", ""]
    for r in results:
        if r["note"]:
            lines.append(f"- {r['case']}: {r['note']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n-predict", type=int, default=32)
    p.add_argument("--prompts", type=int, default=4)
    p.add_argument("--openings", type=int, default=32)
    p.add_argument("--only", help="substring filter on case names")
    a = p.parse_args(argv)
    prompts = PROMPTS[: a.prompts]
    key = keys.load_key()
    engines = Engines()
    results = []
    for case in CASES:
        if a.only and a.only not in case.name:
            continue
        if not MODELS[case.prove_model].exists():
            print(f"skip {case.name}: missing {MODELS[case.prove_model]}")
            continue
        print(f"== {case.name}", flush=True)
        r = run_case(case, engines, key, a.n_predict, prompts, a.openings)
        results.append(r)
        for row in r["rows"]:
            print(f"   {row['verdict']:6s} {row['reason'][:70]:70s} prove {row['prove_s']}s verify {row['verify_s']}s"
                  + (f" replay {row['replay_s']}s" if "replay_s" in row else ""), flush=True)
    meta = {"n_prompts": len(prompts), "n_predict": a.n_predict, "k": a.openings,
            "machine": f"{platform.machine()} {platform.platform()}", "date": time.strftime("%Y-%m-%d")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps({"meta": meta, "cases": results}, indent=1))
    md = write_markdown(results, meta)
    (HERE / "results-trace.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
