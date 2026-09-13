#!/usr/bin/env python3
"""Local-only generation companion. The published verifier has no proving endpoints."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import sys
import tempfile
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parents[1]
G16 = ROOT / 'code/llama.cpp/examples/receipts/zk/groth16'
sys.path.insert(0, str(G16.parent))
from registration_schema import validate_manifest

BINARY = ROOT / 'code/llama.cpp/build/bin/llama-receipts'
MODEL = ROOT / 'models/qwen3-0.6b-q4_k_m.gguf'
REGISTRATION = ROOT / 'registry/qwen3-0.6b-q4_k_m/manifest.json'
CIRCUIT = 'r16_k1024'
STAGES = ('model', 'inference', 'witness', 'proving', 'checking', 'export')
MAX_REQUEST = 4096


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def manifest():
    value = json.loads(REGISTRATION.read_text())
    validate_manifest(value)
    return value


def prerequisites():
    required = [(MODEL, 'Place the registered Qwen3 GGUF in models/qwen3-0.6b-q4_k_m.gguf.'),
                (BINARY, 'Build the llama-receipts executable first (README: local setup).'),
                (G16 / 'node_modules/snarkjs/build/cli.cjs', 'Install the pinned Groth16 npm dependencies.'),
                (G16 / 'build' / CIRCUIT / 'main_js/main.wasm', 'Install the registered r16_k1024 circuit build.'),
                (G16 / 'build' / CIRCUIT / 'main_final.zkey', 'Install the existing registered r16_k1024 proving key. A new setup changes the registration.'),
                (G16 / 'build' / CIRCUIT / 'verification_key.json', 'Install the r16_k1024 verification key.')]
    issues = [message for file, message in required if not file.is_file()]
    if not shutil.which('node'): issues.append('Install Node.js and make it available to this workspace.')
    try:
        import numpy  # noqa: F401
    except ImportError:
        issues.append('Start with ./start-workspace.sh to supply Python dependencies.')
    return issues


class JobFailure(Exception):
    pass


class Prover:
    def __init__(self):
        self.job = None
        self.task = None
        self.package = None

    def snapshot(self):
        if self.job is None:
            return None
        return {k: v for k, v in self.job.items() if k != 'started'} | {
            'elapsed_seconds': round(self.job.get('finished', time.monotonic()) - self.job['started'], 1)}

    def start(self, prompt, registration):
        if self.task and not self.task.done():
            raise HTTPException(409, 'A proof is already running. Wait for it or cancel it first.')
        self.package = None
        self.job = {'id': secrets.token_hex(16), 'status': 'running', 'stage': 'model',
                    'started': time.monotonic(), 'prompt': prompt, 'error': '', 'measurements': {}}
        self.task = asyncio.create_task(self.run(prompt, registration))
        return self.snapshot()

    async def command(self, args, directory, progress=False, timeout=300):
        proc = None
        tail = ''
        try:
            proc = await asyncio.create_subprocess_exec(*map(str, args), cwd=directory,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT, start_new_session=True, limit=1024 * 1024)
            async def drain():
                nonlocal tail
                while line := await proc.stdout.readline():
                    line = line.decode('utf-8', 'replace')
                    tail = (tail + line)[-4000:]
                    if progress and line.startswith('{'):
                        try:
                            event = json.loads(line)
                            if event.get('event') == 'progress' and event.get('stage') in STAGES:
                                self.job['stage'] = event['stage']
                        except (ValueError, AttributeError):
                            pass
                return await proc.wait()
            rc = await asyncio.wait_for(drain(), timeout)
            if rc:
                raise JobFailure(f"{self.job['stage'].capitalize()} failed. Check the installed model and proving materials. Local tool detail: {tail[-400:]}")
            return tail
        except asyncio.TimeoutError:
            raise JobFailure(f"{self.job['stage'].capitalize()} exceeded {timeout} seconds. The local process was stopped; try again after freeing resources.")
        finally:
            if proc is not None:
                # Kill the owned process group, including snarkjs grandchildren, before deleting its inputs.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()

    async def run(self, prompt, registration):
        try:
            with tempfile.TemporaryDirectory(prefix='llama-proof-') as directory:
                work = Path(directory)
                start = time.monotonic()
                if await asyncio.to_thread(sha256, MODEL) != registration['model']['file_sha256']:
                    raise JobFailure('The installed model does not match this registration. Install the registered Qwen3 GGUF before trying again.')
                self.job['measurements']['model_check_seconds'] = round(time.monotonic() - start, 3)
                self.job['stage'] = 'inference'
                start = time.monotonic()
                receipt = work / 'receipt.json'
                await self.command([BINARY, '-m', MODEL, '-p', prompt, '-n', '2', '--temp', '0', '--seed', '0',
                    '-ngl', '0', '-t', '8', '-c', '1024', '-b', '512', '--trace', '--openings', '2048', '--out', receipt], work, timeout=180)
                self.job['measurements']['inference_and_capture_seconds'] = round(time.monotonic() - start, 3)
                rec = json.loads(receipt.read_text())
                if rec['model']['file_sha256'] != registration['model']['file_sha256']:
                    raise JobFailure('The inference model digest differs from the registration.')
                if len(rec['request']['prompt_tokens']) > registration['execution']['max_prompt_tokens']:
                    raise JobFailure('This checkpoint supports at most 64 prompt tokens. Shorten the prompt and try again.')
                trace = json.loads((work / 'receipt.trace.json').read_text())
                tensors = {t['name']: t for t in registration['tensors'] if t.get('groth16', {}).get('circuit') == CIRCUIT}
                candidates = []
                for opening in trace['openings']:
                    leaf = trace['leaves'][opening['index']]
                    if leaf['op'] != 'MUL_MAT' or leaf['out']['ne'][1] != 1 or not leaf['srcs']:
                        continue
                    source = leaf['srcs'][0]
                    name = source.get('base', {}).get('name')
                    if source.get('kind') == 'weight' and name in tensors:
                        candidates.append((tensors[name]['shape'][1], opening['index'], name))
                if not candidates:
                    raise JobFailure('This run did not expose a supported single-row operation. Try a short prompt that produces two tokens.')
                _, index, tensor = min(candidates)
                del trace
                self.job['stage'] = 'witness'
                await self.command([sys.executable, G16 / 'groth16_node.py', receipt, '--model', MODEL,
                    '--index', str(index), '--groups', '0', '--manifest', REGISTRATION,
                    '--progress-json', '--out', work / 'proof'], work, progress=True)
                summary = json.loads((work / 'proof/summary.json').read_text())
                group = summary['groups'][0]
                if not (group['accept'] and group['bound']):
                    raise JobFailure('The generated proof failed its local acceptance checks.')
                self.job['stage'] = 'export'
                package = {'format': 'llama-receipts/proof-package/v1', 'claim': 'q4k-integer-row-group/v1',
                           'registration_id': registration['manifest_id'], 'tensor': tensor, 'group': 0,
                           'proof': json.loads((work / 'proof/group0/proof.json').read_text()),
                           'public': json.loads((work / 'proof/group0/public.json').read_text())}
                exported = work / 'computation.llamaproof'
                exported.write_text(json.dumps(package))
                await self.command(['node', ROOT / 'site/verify-file.cjs', exported], work, timeout=30)
                self.job['measurements'].update({k: group[k] for k in ('witness_seconds', 'prove_seconds', 'verify_seconds')})
                self.job['measurements'].update(package_bytes=exported.stat().st_size, circuit=CIRCUIT,
                    coverage='One integer row group; no prompt or answer binding',
                    verifier_sha256=registration['proof_system']['groth16']['verifier_sha256'])
                self.job['answer'] = rec['response']['text']
                self.package = package
            # Private trace and temporary prover inputs have been removed before offering the download.
            self.job['status'] = 'complete'
        except asyncio.CancelledError:
            self.job['status'] = 'cancelled'
            self.package = None
        except (JobFailure, OSError, ValueError, KeyError) as error:
            self.job['status'] = 'failed'
            self.job['error'] = str(error)[:600]
            self.package = None
        except Exception:
            self.job['status'] = 'failed'
            self.job['error'] = 'The local prover stopped unexpectedly. Restart the workspace and check the installed tools.'
            self.package = None
        finally:
            self.job['finished'] = time.monotonic()

    async def cancel(self):
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                # A task cancelled before its first step cannot run its own finally block.
                self.job.update(status='cancelled', finished=time.monotonic())
                self.package = None


def create_app(port=8789):
    prover = Prover()
    token = secrets.token_urlsafe(32)
    authority = f'127.0.0.1:{port}'
    origin = 'http://' + authority

    @asynccontextmanager
    async def lifespan(app):
        yield
        await prover.cancel()

    app = FastAPI(title='Local proof workspace', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.prover = prover
    app.state.token = token

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        if request.headers.get('host') != authority or request.headers.get('origin', origin) != origin:
            return JSONResponse({'detail': 'Open the workspace at ' + origin + '.'}, status_code=403)
        if request.url.path.startswith('/api/') and not secrets.compare_digest(request.headers.get('x-prover-token', ''), token):
            return JSONResponse({'detail': 'Reload the local workspace to reconnect.'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/', response_class=HTMLResponse)
    async def page():
        html = (ROOT / 'site/index.html').read_text()
        return html.replace('/*LOCAL_CONFIG*/null', json.dumps({'token': token}))

    @app.get('/api/local/config')
    async def config():
        m = manifest()
        issues = prerequisites()
        return {'models': [{'id': m['manifest_id'], 'name': m['model']['name'], 'ready': not issues, 'issues': issues}], 'job': prover.snapshot()}

    @app.post('/api/local/jobs')
    async def start(request: Request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_REQUEST:
                raise HTTPException(413, 'Request too large. Use a shorter prompt.')
        try:
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {'model', 'prompt'}:
                raise ValueError('Expected a model and prompt.')
            if not isinstance(data['prompt'], str) or not data['prompt'].strip() or len(data['prompt']) > 512 or '\x00' in data['prompt']:
                raise ValueError('Enter a prompt of 1 to 512 characters, without NUL characters.')
            m = manifest()
            if data['model'] != m['manifest_id']:
                raise ValueError('Choose the registered model offered by this workspace.')
        except (ValueError, UnicodeError) as error:
            raise HTTPException(400, str(error))
        issues = prerequisites()
        if issues:
            raise HTTPException(503, ' '.join(issues))
        return prover.start(data['prompt'], m)

    def job_or_404(job_id):
        if not prover.job or job_id != prover.job['id']:
            raise HTTPException(404, 'This run is no longer available. Start a new run.')

    @app.get('/api/local/jobs/{job_id}')
    async def job(job_id: str):
        job_or_404(job_id)
        return prover.snapshot()

    @app.post('/api/local/jobs/{job_id}/cancel')
    async def cancel(job_id: str):
        job_or_404(job_id)
        await prover.cancel()
        return prover.snapshot()

    @app.get('/api/local/jobs/{job_id}/proof')
    async def proof(job_id: str):
        job_or_404(job_id)
        if prover.job['status'] != 'complete' or prover.package is None:
            raise HTTPException(409, 'A verified proof is not ready for download.')
        return prover.package

    return app


if __name__ == '__main__':
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8789)
    args = parser.parse_args()
    print(f'Open http://127.0.0.1:{args.port} to generate and verify proofs locally.', flush=True)
    uvicorn.run(create_app(args.port), host='127.0.0.1', port=args.port)
