#!/usr/bin/env python3
"""Per-op inventory and value ranges of a fully opened llama-receipts trace.

    llama-receipts -m model.gguf -p "..." -n 1 --trace --openings 1000000 --out all.json
    python3 trace_stats.py all.json --out stats.json

For each op: how many nodes, the output type, the largest |value| over all opened outputs, and
for MUL_MAT the weight type and the reduction length K. The fixed-point column says how many
integer bits a value of that magnitude needs; add the fraction bits you choose and, for a
sum over K products, twice that plus log2(K).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "code" / "llama.cpp" / "examples" / "receipts"))
import verify_trace as vt  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("receipt")
    p.add_argument("--out")
    a = p.parse_args(argv)
    tpath = Path(a.receipt).with_name(Path(a.receipt).name.removesuffix(".json") + ".trace.json")
    tdoc = json.loads(tpath.read_text())
    leaves, openings = tdoc["leaves"], tdoc["openings"]
    stats: dict[str, dict] = defaultdict(lambda: {"nodes": 0, "opened": 0, "types": set(), "max_abs": 0.0, "nonfinite": 0, "weights": set(), "k": set()})
    for leaf in leaves:
        key = leaf["op"]
        st = stats[key]
        st["nodes"] += 1
        st["types"].add(leaf["out"]["type"].lower())
        if leaf["op"] == "MUL_MAT":
            s0 = leaf["srcs"][0]
            st["weights"].add(f'{s0.get("base", s0).get("type", s0.get("type", "?")).lower()}{"(weight)" if s0.get("kind") == "weight" else "(data)"}')
            st["k"].add(s0.get("base", s0)["ne"][0] if "ne" in s0.get("base", s0) else s0["ne"][0])
    for o in openings:
        leaf = leaves[o["index"]]
        out = leaf["out"]
        arr = vt.tensor_from_bytes(vt.decode_blob(o["out"], o.get("enc", "base64")), out["type"], out["ne"], out["nb"], out["offset"])
        if arr.dtype.kind == "f":
            arr = arr.astype(np.float64)
            finite = np.isfinite(arr)
            st = stats[leaf["op"]]
            st["opened"] += 1
            st["nonfinite"] += int((~finite).sum())
            if finite.any():
                st["max_abs"] = max(st["max_abs"], float(np.abs(arr[finite]).max()))
        else:
            stats[leaf["op"]]["opened"] += 1
    rows = []
    for op, st in sorted(stats.items(), key=lambda kv: -kv[1]["nodes"]):
        int_bits = max(1, math.ceil(math.log2(st["max_abs"]))) + 1 if st["max_abs"] > 0 else 0
        rows.append({"op": op, "nodes": st["nodes"], "opened": st["opened"], "out_types": sorted(st["types"]),
                     "max_abs": st["max_abs"], "int_bits_signed": int_bits, "nonfinite": st["nonfinite"],
                     "weights": sorted(st["weights"]), "k": sorted(st["k"])})
    print(f"{len(leaves)} leaves, {len(openings)} opened, {tdoc['n_graphs']} graphs")
    print(f"{'op':16s} {'nodes':>5s} {'opened':>6s} {'max|out|':>12s} {'int bits':>8s}  out types / weights / K")
    for r in rows:
        extra = ", ".join(r["out_types"]) + ((" | " + ", ".join(r["weights"]) + " | K=" + ",".join(map(str, r["k"]))) if r["weights"] else "")
        print(f"{r['op']:16s} {r['nodes']:5d} {r['opened']:6d} {r['max_abs']:12.4g} {r['int_bits_signed']:8d}  {extra}")
    if a.out:
        Path(a.out).write_text(json.dumps({"n_leaves": len(leaves), "n_graphs": tdoc["n_graphs"], "ops": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
