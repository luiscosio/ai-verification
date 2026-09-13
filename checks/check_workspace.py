"""Local workspace boundaries, lifecycle, single-file verification and launcher fallback."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('local_prover', ROOT / 'site/local_prover.py')
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


async def request(app, path, method='GET', body=b'', headers=None):
    messages = []
    sent = False
    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        await asyncio.Event().wait()
    async def send(message):
        messages.append(message)
    scope = {'type':'http', 'asgi':{'version':'3.0', 'spec_version':'2.4'}, 'http_version':'1.1',
             'method':method, 'scheme':'http', 'path':path, 'raw_path':path.encode(), 'query_string':b'',
             'headers':[(k.encode(), v.encode()) for k, v in (headers or {}).items()],
             'client':('127.0.0.1', 12345), 'server':('127.0.0.1', 8789)}
    await asyncio.wait_for(app(scope, receive, send), 5)
    status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
    raw = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
    return status, json.loads(raw)


class WorkspaceChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = local.create_app()
        self.headers = {'host':'127.0.0.1:8789', 'x-prover-token':self.app.state.token}

    async def asyncTearDown(self):
        await self.app.state.prover.cancel()

    async def test_local_access_boundaries(self):
        for headers in ({'host':'127.0.0.1:8789'}, self.headers | {'host':'attacker.example'},
                        self.headers | {'origin':'https://attacker.example'}):
            status, _ = await request(self.app, '/api/local/config', headers=headers)
            self.assertEqual(status, 403)
        status, body = await request(self.app, '/api/local/config', headers=self.headers)
        self.assertEqual(status, 200); self.assertIn('models', body)

    async def test_bad_requests_and_unknown_run(self):
        for body in (b'null', b'[]', b'{', json.dumps({'model':'wrong', 'prompt':'test'}).encode(), b'x' * 4097):
            status, _ = await request(self.app, '/api/local/jobs', 'POST', body, self.headers)
            self.assertIn(status, (400, 413))
        status, _ = await request(self.app, '/api/local/jobs/missing/proof', headers=self.headers)
        self.assertEqual(status, 404)

    async def test_one_job_and_cancel_recovery(self):
        async def pending(prover, prompt, registration):
            try:
                await asyncio.sleep(60)
            finally:
                prover.job['status'] = 'cancelled'
        with patch.object(local.Prover, 'run', pending), patch.object(local, 'prerequisites', return_value=[]):
            body = json.dumps({'model':local.manifest()['manifest_id'], 'prompt':'test'}).encode()
            status, job = await request(self.app, '/api/local/jobs', 'POST', body, self.headers)
            self.assertEqual(status, 200)
            status, _ = await request(self.app, '/api/local/jobs', 'POST', body, self.headers)
            self.assertEqual(status, 409)
            status, _ = await request(self.app, '/api/local/jobs/' + job['id'] + '/proof', headers=self.headers)
            self.assertEqual(status, 409)
            status, job = await request(self.app, '/api/local/jobs/' + job['id'] + '/cancel', 'POST', headers=self.headers)
            self.assertEqual(status, 200); self.assertEqual(job['status'], 'cancelled')
            status, job = await request(self.app, '/api/local/jobs', 'POST', body, self.headers)
            self.assertEqual(status, 200)

    async def test_process_failure_timeout_and_progress(self):
        prover = local.Prover(); prover.job = {'stage':'model'}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(local.JobFailure):
                await prover.command([sys.executable, '-c', 'raise SystemExit(9)'], directory)
            with self.assertRaises(local.JobFailure):
                await prover.command([sys.executable, '-c', 'import time; time.sleep(30)'], directory, timeout=0.04)
            await prover.command([sys.executable, '-c', 'print(\'{"event":"progress","stage":"proving"}\')'], directory, progress=True)
            self.assertEqual(prover.job['stage'], 'proving')

    async def test_failed_job_has_no_download(self):
        prover = self.app.state.prover
        with patch.object(local, 'sha256', return_value='wrong'):
            prover.start('test', local.manifest())
            await prover.task
        self.assertEqual(prover.job['status'], 'failed'); self.assertIsNone(prover.package)
        status, _ = await request(self.app, '/api/local/jobs/' + prover.job['id'] + '/proof', headers=self.headers)
        self.assertEqual(status, 409)

    async def test_cancel_before_first_step(self):
        prover = self.app.state.prover
        prover.start('test', local.manifest())
        await prover.cancel()
        self.assertEqual(prover.job['status'], 'cancelled')


class ToolChecks(unittest.TestCase):
    def test_single_file_cli(self):
        m = local.manifest()
        base = {'format':'llama-receipts/proof-package/v1', 'claim':'q4k-integer-row-group/v1',
                'registration_id':m['manifest_id'], 'tensor':'blk.0.attn_k.weight', 'group':0}
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'proof.llamaproof'
            for name, expected in [('honest', 0), ('out-of-range', 1)]:
                fixture = ROOT / 'checks/fixtures/groth16'
                file.write_text(json.dumps(base | {'proof':json.loads((fixture / f'{name}-proof.json').read_text()),
                                                  'public':json.loads((fixture / f'{name}-public.json').read_text())}))
                result = subprocess.run(['node', str(ROOT / 'site/verify-file.cjs'), str(file)], capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_builder_message_on_missing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / 'registry'; (registry / 'model').mkdir(parents=True)
            (registry / 'model/manifest.json').write_bytes(local.REGISTRATION.read_bytes())
            result = subprocess.run([sys.executable, str(ROOT / 'site/build_site.py'), '--registry', str(registry)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Site build failed:', result.stderr)
            self.assertIn('verification_key.json', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_uv_fallback_and_explicit_override(self):
        # Fake interpreters exercise selection without downloading dependencies or rerunning expensive checks.
        with tempfile.TemporaryDirectory() as directory:
            bin = Path(directory)
            (bin / 'python').write_text('#!/bin/sh\nif [ "$1" = -c ]; then exit 1; fi\nexit 0\n')
            (bin / 'uv').write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$CALL_LOG"\n')
            (bin / 'node').write_text('#!/bin/sh\nexit 0\n')
            for file in bin.iterdir(): file.chmod(0o755)
            env = dict(os.environ, PYTHON=str(bin / 'python'), PATH=str(bin) + ':' + os.environ['PATH'], CALL_LOG=str(bin / 'calls'))
            env.pop('API_PYTHON', None)
            result = subprocess.run(['bash', str(ROOT / 'checks/run.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--with fastapi --with python-multipart', (bin / 'calls').read_text())
            env['API_PYTHON'] = str(bin / 'python')
            result = subprocess.run(['bash', str(ROOT / 'checks/run.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
