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
import asyncio
import sys
import re
import json
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

sys.path.insert(0, str(BIN.parents[2]))
from registration_schema import validate_manifest
verification_slot = asyncio.Semaphore(1)

app = FastAPI(title="llama-receipts registry")
manifests = {m["manifest_id"]: m for m in (json.loads(f.read_text()) for f in sorted((ROOT / "registry").glob("*/manifest.json")))}

for manifest in manifests.values():
    validate_manifest(manifest)


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "site" / "index.html").read_text().replace("__PUBLIC_ORIGIN__", "http://127.0.0.1").replace("__ROBOTS__", "noindex")


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
        if not isinstance(pj, dict):
            raise ValueError("public.json must be an object")
        m, k = entry["shape"][1], entry["shape"][0]
        if type(pj.get("m")) is not int or type(pj.get("k")) is not int or (pj["m"], pj["k"]) != (m, k):
            raise ValueError("public.json shape is not the registered tensor's")
        if pj.get("config") != "orion" or not isinstance(pj.get("commitment"), str) or not re.fullmatch(r"[0-9a-f]{64}", pj["commitment"]):
            raise ValueError("unsupported commitment format")
        for name, count, bound in (("q8", k, 127), ("s1", m * k // 256, 30723840), ("s2", m * k // 256, 2048256)):
            values = pj.get(name)
            if not isinstance(values, list) or len(values) != count or any(type(v) is not int or abs(v) > bound for v in values):
                raise ValueError(f"invalid {name} length or integer range")
    except (ValueError, UnicodeError) as e:
        raise HTTPException(400, str(e))
    if verification_slot.locked():
        raise HTTPException(503, "verifier busy; retry later")
    async with verification_slot:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "public.json").write_bytes(pub)
            (Path(tmp) / "proof.bin").write_bytes(prf)
            t0 = time.time()
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(str(BIN), "verify", str(Path(tmp) / "public.json"), str(Path(tmp) / "proof.bin"),
                    "orion", "--commitment", entry["commitment"]["value"], stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await asyncio.wait_for(proc.communicate(), TIMEOUT)
            except asyncio.TimeoutError:
                raise HTTPException(504, f"verification exceeded {TIMEOUT}s")
            except OSError:
                raise HTTPException(503, "verifier executable unavailable")
            finally:
                if proc is not None and proc.returncode is None:
                    proc.kill()
                    await proc.communicate()
    accept = proc.returncode == 0
    return {"accept": accept, "seconds": round(time.time() - t0, 3), "registered_commitment": entry["commitment"]["value"], "stderr": stderr.decode("utf-8", "replace")[-600:],
            "coverage": "one matmul node, integer core, all rows; Expander proof: binding, not zero-knowledge",
            "reproduce": f"receipts-zk verify public.json proof.bin orion --commitment {entry['commitment']['value']}"}


if __name__ == "__main__":
    import uvicorn
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8788)
    a = p.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=a.port)
