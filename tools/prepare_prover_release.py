#!/usr/bin/env python3
"""Prepare public proving assets; never include traces, inputs or witnesses."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
G16 = ROOT / 'code/llama.cpp/examples/receipts/zk/groth16'
CIRCUITS = ('r16_k1024', 'r16_k1536', 'r8_k2048', 'r8_k3072')
TAG = 'prover-materials-v1'


def sha(file):
    with file.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    assets = []
    for circuit in CIRCUITS:
        build = G16 / 'build' / circuit
        expected = json.loads((ROOT / 'registry/circuits' / circuit / 'verification_key.json').read_text())
        exported = args.out / (circuit + '-verification_key.json')
        subprocess.run(['node', str(G16 / 'node_modules/snarkjs/build/cli.cjs'), 'zkey', 'export', 'verificationkey', str(build / 'main_final.zkey'), str(exported)], check=True)
        if json.loads(exported.read_text()) != expected:
            raise ValueError(circuit + ': zkey does not match the registered verification key')
        exported.unlink()
        for relative in ('main_final.zkey', 'main_js/main.wasm', 'main.r1cs'):
            source = build / relative
            name = circuit + '-' + source.name
            target = args.out / name
            shutil.copyfile(source, target)
            assets.append({'name':name, 'circuit':circuit, 'path':relative, 'bytes':target.stat().st_size, 'sha256':sha(target)})
    source = G16 / 'ptau/pot18_final.ptau'
    target = args.out / source.name
    shutil.copyfile(source, target)
    assets.append({'name':target.name, 'circuit':None, 'path':'ptau/pot18_final.ptau', 'bytes':target.stat().st_size, 'sha256':sha(target)})
    manifests = [json.loads(p.read_text()) for p in (ROOT / 'registry').glob('*/manifest.json')]
    for manifest in manifests:
        if manifest['proof_system'].get('groth16'):
            if manifest['proof_system']['groth16']['setup_sha256'] != sha(target):
                raise ValueError('setup file differs from registered digest')
    data = {'format':'llama-receipts/prover-materials/v1', 'tag':TAG,
            'base_url':f'https://github.com/luiscosio/ai-verification/releases/download/{TAG}/',
            'fork_commit':subprocess.check_output(['git','-C',str(ROOT/'code/llama.cpp'),'rev-parse','HEAD'],text=True).strip(),
            'circom':'2.2.3', 'snarkjs':'0.7.5', 'circomlib':'2.0.5',
            'trust':'Existing experimental setup; publishing files does not add an independent ceremony.', 'assets':assets}
    (args.out / 'prover-materials-v1.json').write_text(json.dumps(data, indent=2)+'\n')
    print(f'Prepared {len(assets)} assets ({sum(a["bytes"] for a in assets):,} bytes) in {args.out}')


if __name__ == '__main__':
    main()
