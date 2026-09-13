#!/usr/bin/env python3
"""Build the static registry and verification page from registry/*/manifest.json and the Groth16 verification keys.

    uv run python3 site/build_site.py [--out site/index.html] [--artifact site/artifact.html]

index.html is the full page. artifact.html is the same content without the document skeleton,
for publishing as a claude.ai artifact (which supplies its own head and body).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
G16 = ROOT / "code" / "llama.cpp" / "examples" / "receipts" / "zk" / "groth16" / "build"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT / "site" / "index.html"))
    p.add_argument("--artifact", default=str(ROOT / "site" / "artifact.html"))
    p.add_argument("--registry", default=str(ROOT / "registry"))
    p.add_argument("--example", action="append", default=[], help="label=manifest_id=tensor=group=dir with proof.json and public.json (repeatable)")
    a = p.parse_args()
    manifests = [json.loads(f.read_text()) for f in sorted(Path(a.registry).glob("*/manifest.json"))]
    circuits = {t["groth16"]["circuit"] for m in manifests for t in m["tensors"] if t.get("groth16")}
    vkeys = {}
    for c in sorted(circuits):
        f = G16 / c / "verification_key.json"
        if f.exists():
            vkeys[c] = json.loads(f.read_text())
        else:
            print(f"warning: no verification key for {c} ({f})")
    examples = []
    for spec in a.example:
        label, mid, tensor, group, d = spec.split("=", 4)
        examples.append({"label": label, "manifest_id": mid, "tensor": tensor, "group": int(group),
                         "proof": json.loads((Path(d) / "proof.json").read_text()), "public": json.loads((Path(d) / "public.json").read_text())})
    data = {"manifests": manifests, "vkeys": vkeys, "examples": examples}
    template = (ROOT / "site" / "template.html").read_text()
    html = template.replace("__DATA__", json.dumps(data, separators=(",", ":"))).replace("__BUILT_AT__", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    Path(a.out).write_text(html)
    # artifact: strip the document skeleton, keep title, style, main and scripts
    body = html.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    head = html.split("<head>", 1)[1].split("</head>", 1)[0]
    style = head[head.index("<style>"):head.index("</style>") + len("</style>")]
    fonts = [l for l in head.splitlines() if "fonts.googleapis.com" in l]
    Path(a.artifact).write_text("<title>llama-receipts registry</title>\n" + "\n".join(fonts) + "\n" + style + "\n" + body)
    print(f"{a.out}: {len(manifests)} manifests, {len(vkeys)} verification keys ({', '.join(vkeys) or 'none'}), {Path(a.out).stat().st_size:,} bytes; artifact {Path(a.artifact).stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
