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
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
G16 = ROOT / "code" / "llama.cpp" / "examples" / "receipts" / "zk" / "groth16"
sys.path.insert(0, str(G16.parent))
from registration_schema import validate_manifest, canonical


def vendor_sources():
    directory = ROOT / "site/vendor"
    manifest = json.loads((directory / "manifest.json").read_text())
    files = {}
    for name in ("snarkjs.min.js", "three.min.js", "snarkjs.LICENSE", "three.LICENSE"):
        data = (directory / name).read_bytes()
        pin = manifest["files"][name]
        if len(data) != pin["bytes"] or hashlib.sha256(data).hexdigest() != pin["sha256"]:
            raise ValueError(f"vendored {name} differs from its pinned digest")
        files[name] = data.decode()
    return files


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT / "site" / "index.html"))
    p.add_argument("--artifact", default=str(ROOT / "site" / "artifact.html"))
    p.add_argument("--registry", default=str(ROOT / "registry"))
    p.add_argument("--example", action="append", default=[], help="label=manifest_id=tensor=group=dir with proof.json and public.json (repeatable)")
    a = p.parse_args()
    manifests = [json.loads(f.read_text()) for f in sorted(Path(a.registry).glob("*/manifest.json"))]
    if not manifests:
        raise ValueError("registry contains no model manifests")
    verifier_source = (G16 / "verify.js").read_text()
    for manifest in manifests:
        validate_manifest(manifest)
        if manifest["proof_system"].get("groth16") and hashlib.sha256(verifier_source.encode()).hexdigest() != manifest["proof_system"]["groth16"]["verifier_sha256"]:
            raise ValueError("verifier source differs from the registration")
    circuits = {t["groth16"]["circuit"] for m in manifests for t in m["tensors"] if t.get("groth16")}
    vkeys = {}
    for c in sorted(circuits):
        f = Path(a.registry) / "circuits" / c / "verification_key.json"
        key = json.loads(f.read_text())
        digest = hashlib.sha256(canonical(key)).hexdigest()
        for m in manifests:
            if any(t.get("groth16", {}).get("circuit") == c for t in m["tensors"]):
                if m["proof_system"]["groth16"]["verification_keys"].get(c) != digest:
                    raise ValueError(f"{c}: verification key digest differs from registration")
        vkeys[c] = key
    examples = []
    for spec in a.example:
        label, mid, tensor, group, d = spec.split("=", 4)
        examples.append({"label": label, "manifest_id": mid, "tensor": tensor, "group": int(group),
                         "proof": json.loads((Path(d) / "proof.json").read_text()), "public": json.loads((Path(d) / "public.json").read_text())})
        m = next((m for m in manifests if m["manifest_id"] == mid), None)
        t = next((t for t in m["tensors"] if t["name"] == tensor), None) if m else None
        if t is None or not t.get("groth16") or not 0 <= int(group) < len(t["groth16"]["groups"]):
            raise ValueError("example does not name a registered row group")
    if not a.example:
        fixtures = ROOT / "checks/fixtures/groth16"
        honest = json.loads((fixtures / "honest-public.json").read_text())
        for m in manifests:
            t = next((t for t in m["tensors"] if t.get("groth16", {}).get("groups", [None])[0] == honest[0]), None)
            if t is None:
                continue
            for name, label in (("honest", "Example valid proof"), ("out-of-range", "Example invalid proof")):
                examples.append({"label": label, "manifest_id": m["manifest_id"], "tensor": t["name"], "group": 0,
                                 "proof": json.loads((fixtures / (name + "-proof.json")).read_text()),
                                 "public": json.loads((fixtures / (name + "-public.json")).read_text())})
            break
    # Same sole registration offered by local_prover.manifest(); other catalogue
    # entries support verification only, not workspace generation.
    workspace = json.loads((ROOT / "registry/qwen3-0.6b-q4_k_m/manifest.json").read_text())["manifest_id"]
    data = {"manifests": manifests, "vkeys": vkeys, "examples": examples,
            "local_generation": [workspace] if any(m["manifest_id"] == workspace for m in manifests) else []}
    template = (ROOT / "site" / "template.html").read_text()
    vendor = vendor_sources()
    for marker, name in (("__SNARKJS__", "snarkjs"), ("__THREE__", "three")):
        # Escape closing script sequences in libraries and embed their license notices.
        source = "/*\n" + vendor[name + ".LICENSE"].replace("*/", "* /") + "\n*/\n" + vendor[name + ".min.js"]
        template = template.replace(marker, source.replace("</", "<\\/"))
    template = template.replace("__STYLE__", (ROOT / "site/style.css").read_text())
    template = template.replace("__FIGURE__", (ROOT / "site/figure.js").read_text())
    template = template.replace("__VERIFIER__", verifier_source)
    template = template.replace("__PACKAGE__", (ROOT / "site/proof-package.js").read_text())
    template = template.replace("__APP__", (ROOT / "site/app.js").read_text())
    html = template.replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("<", "\\u003c")).replace("__BUILT_AT__", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
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
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"Site build failed: {error}", file=sys.stderr)
        raise SystemExit(1)
