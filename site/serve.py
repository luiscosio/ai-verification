#!/usr/bin/env python3
"""Serve the registry page locally and verify Expander proof packages on the server.

    uv run --with fastapi --with 'uvicorn[standard]' --with python-multipart python3 site/serve.py [--port 8788]

GET  /                      the page built by build_site.py (Groth16 verification runs in the browser)
GET  /api/models            the manifests
POST /api/verify/expander   multipart: model (manifest id), tensor, public (public.json), proof (proof.bin)
                            runs `receipts-zk verify --commitment <registered>` with a size cap and a timeout;
                            the server holds no weights, only the manifests
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "code" / "llama.cpp" / "examples" / "receipts" / "zk" / "target" / "release" / "receipts-zk"
MAX_PROOF = 64 * 1024 * 1024
MAX_PUBLIC = 4 * 1024 * 1024
TIMEOUT = 120

app = FastAPI(title="llama-receipts registry")
manifests = {m["manifest_id"]: m for m in (json.loads(f.read_text()) for f in sorted((ROOT / "registry").glob("*/manifest.json")))}


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "site" / "index.html").read_text()


@app.get("/api/models")
def models():
    return JSONResponse(list(manifests.values()))


@app.post("/api/verify/expander")
async def verify_expander(model: str = Form(...), tensor: str = Form(...), public: UploadFile = File(...), proof: UploadFile = File(...)):
    m = manifests.get(model)
    if m is None:
        raise HTTPException(404, "unknown manifest id")
    entry = next((t for t in m["tensors"] if t["name"] == tensor), None)
    if entry is None or "commitment" not in entry:
        raise HTTPException(404, "tensor has no registered Orion commitment")
    pub = await public.read(MAX_PUBLIC + 1)
    prf = await proof.read(MAX_PROOF + 1)
    if len(pub) > MAX_PUBLIC or len(prf) > MAX_PROOF:
        raise HTTPException(413, "package exceeds the size limits")
    try:
        pj = json.loads(pub)
        if pj.get("m") != entry["shape"][1] or pj.get("k") != entry["shape"][0]:
            raise HTTPException(400, "public.json shape is not the registered tensor's")
    except json.JSONDecodeError:
        raise HTTPException(400, "public.json is not JSON")
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "public.json").write_bytes(pub)
        (Path(tmp) / "proof.bin").write_bytes(prf)
        t0 = time.time()
        try:
            r = subprocess.run([str(BIN), "verify", str(Path(tmp) / "public.json"), str(Path(tmp) / "proof.bin"), "orion", "--commitment", entry["commitment"]["value"]],
                               capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, f"verification exceeded {TIMEOUT}s")
    accept = r.returncode == 0
    return {"accept": accept, "seconds": round(time.time() - t0, 3), "registered_commitment": entry["commitment"]["value"], "stderr": r.stderr[-600:],
            "coverage": "one matmul node, integer core, all rows; Expander proof: binding, not zero-knowledge",
            "reproduce": f"receipts-zk verify public.json proof.bin orion --commitment {entry['commitment']['value']}"}


if __name__ == "__main__":
    import uvicorn
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8788)
    a = p.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=a.port)
