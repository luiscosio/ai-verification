#!/usr/bin/env python3
"""Check an isolated release image or a live HTTPS workspace. Never provisions."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Unexpected redirect; credentials were not forwarded")


def check(url, password, context, folder):
    opener = urllib.request.build_opener(
        NoRedirect(), urllib.request.HTTPSHandler(context=context))
    auth = 'Basic ' + base64.b64encode(('proof:' + password).encode()).decode()

    def request(path, body=None, headers=None, authenticated=True):
        headers = dict(headers or {})
        if authenticated:
            headers['Authorization'] = auth
        if body is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(url + path, headers=headers,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with opener.open(req, timeout=30) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    deadline = time.monotonic() + 60
    while True:
        try:
            status, html, headers = request('/')
            if status == 200:
                break
            require(status in (502, 503), 'Authenticated page returned HTTP ' + str(status))
        except urllib.error.URLError:
            if time.monotonic() >= deadline:
                raise
        require(time.monotonic() < deadline, 'Workspace did not become ready')
        time.sleep(1)
    require(headers.get('Cache-Control') == 'no-store', 'Page must not be cached')
    for path in ('/', '/api/local/config'):
        require(request(path, authenticated=False)[0] == 401, 'Login is not enforced')
    require(request('/api/local/config')[0] == 403, 'Missing request token was accepted')
    match = re.search(r'const LOCAL = (\{[^;]+\});', html.decode())
    require(match is not None, 'Hosted configuration missing')
    local = json.loads(match.group(1))
    require(local.get('hosted') is True, 'Page does not declare server execution')
    headers = {'X-Prover-Token': local['token'], 'Origin': url}
    require(request('/api/local/config', headers=headers | {'Origin': 'https://attacker.invalid'})[0] == 403,
            'Wrong origin was accepted')
    wrong_status, wrong_body, _ = request('/api/local/config', headers=headers | {'Host': 'attacker.invalid'})
    # Caddy may return an empty 200 for an unmatched virtual host; it must never serve the API.
    require(wrong_status != 200 or not wrong_body, 'Wrong host received application content')
    require(request('/api/local/jobs', {'padding': 'x' * 17000}, headers)[0] == 413,
            'Oversized request was not rejected by proxy')
    status, raw, _ = request('/api/local/config', headers=headers)
    require(status == 200, 'Authenticated configuration failed')
    models = json.loads(raw)['models']
    require(bool(models) and models[0]['ready'], 'Registered model is not ready')
    started = time.monotonic()
    status, raw, _ = request('/api/local/jobs',
                             {'model': models[0]['id'], 'prompt': 'The capital of France is'}, headers)
    require(status == 200, 'Generation could not start (workspace may be busy)')
    job_id = json.loads(raw)['id']
    try:
        deadline = time.monotonic() + 600
        while True:
            status, raw, _ = request('/api/local/jobs/' + job_id, headers=headers)
            require(status == 200, 'Job status request failed')
            job = json.loads(raw)
            if job['status'] != 'running':
                break
            require(time.monotonic() < deadline, 'Generation timed out')
            time.sleep(1)
        require(job['status'] == 'complete', 'Generation did not complete')
        status, raw, _ = request('/api/local/jobs/' + job_id + '/proof', headers=headers)
        require(status == 200, 'Proof download failed')
    except BaseException:
        # Cancel only the job created by this check, never another visitor's job.
        try:
            request('/api/local/jobs/' + job_id + '/cancel', {}, headers)
        except Exception:
            pass
        raise
    proof = folder / 'proof.llamaproof'
    proof.write_bytes(raw)
    verifier = ['node', str(ROOT / 'site/verify-file.cjs')]
    verified = subprocess.run(verifier + [str(proof)], capture_output=True, text=True, timeout=60)
    require(verified.returncode == 0, 'Independent verification rejected generated proof')
    verdict = json.loads(verified.stdout)
    require(verdict.get('accept') is True, 'Missing independent acceptance')
    tampered = json.loads(raw)
    tampered['public'][-1] = str(int(tampered['public'][-1]) + 1)
    proof.write_text(json.dumps(tampered))
    rejected = subprocess.run(verifier + [str(proof)], capture_output=True, text=True, timeout=60)
    require(rejected.returncode == 1, 'Tampered proof must produce a verification rejection')
    return {'url': url, 'generation_and_verification_seconds': round(time.monotonic() - started, 2),
            'proof_bytes': len(raw), 'proof_sha256': hashlib.sha256(raw).hexdigest(),
            'independent_verifier': verdict, 'tampered_proof_rejected': True,
            'access_checks': ['login', 'request token', 'origin', 'host', '16KB body limit', 'no-store']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--image', help='Local release image; starts and removes isolated containers')
    target.add_argument('--url', help='Live HTTPS origin; password from PROVER_PASSWORD')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='proof-release-check-') as temporary:
        folder = Path(temporary)
        if args.url:
            url = args.url.rstrip('/')
            parsed = urllib.parse.urlsplit(url)
            require(parsed.scheme == 'https' and parsed.hostname and not
                    (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment),
                    'URL must be an HTTPS origin')
            password = os.environ.get('PROVER_PASSWORD')
            require(bool(password), 'Set PROVER_PASSWORD privately in the environment')
            result = check(url, password, ssl.create_default_context(), folder)
            result['tls_scope'] = 'Public certificate verification enabled'
        else:
            password = secrets.token_urlsafe(24)
            hashed = subprocess.check_output(['docker', 'run', '--rm', 'caddy:2.10.2-alpine',
                                              'caddy', 'hash-password', '--plaintext', password], text=True).strip()
            compose = (DEPLOY / 'compose.yaml').read_text().replace(
                'ports: ["80:80", "443:443"]', 'ports: ["127.0.0.1:18443:18443"]')
            require(compose != (DEPLOY / 'compose.yaml').read_text(), 'Cannot isolate proxy port mapping')
            (folder / 'compose.yaml').write_text(compose)
            (folder / 'override.yaml').write_text('services:\n  prover:\n    image: ' + json.dumps(args.image) + '\n')
            (folder / 'Caddyfile').write_text((DEPLOY / 'Caddyfile').read_text().replace(
                '{$PROVER_DOMAIN} {', '{$PROVER_DOMAIN} {\n    tls internal', 1))
            env = os.environ | {'APP_REVISION': 'local-check', 'PROVER_DOMAIN': 'localhost:18443',
                                'PROVER_PASSWORD_HASH': hashed}
            command = ['docker', 'compose', '-p', 'proof-check-' + secrets.token_hex(4),
                       '-f', str(folder / 'compose.yaml'), '-f', str(folder / 'override.yaml')]
            try:
                subprocess.run(command + ['up', '-d', '--no-build'], env=env, check=True)
                result = check('https://localhost:18443', password, ssl._create_unverified_context(), folder)
                result['image_id'] = subprocess.check_output(
                    ['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], text=True).strip()
                result['tls_scope'] = 'Isolated local test certificate; public DNS/ACME not tested'
            finally:
                subprocess.run(command + ['down', '--volumes'], env=env, check=True)
        result['operator_commit'] = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        result['operator_tree_dirty'] = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain']))
        result['checked_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n')
        print('Hosted release checks passed; report: ' + str(args.out))


if __name__ == '__main__':
    main()
