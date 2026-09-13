#!/usr/bin/env python3
"""Install or check the pinned model, native tools and existing proving materials."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
G16_REL = Path('code/llama.cpp/examples/receipts/zk/groth16')
DEFAULT_CIRCUIT = 'r16_k1024'


def sha(file):
    with Path(file).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def matches(file, digest, size=None):
    return file.is_file() and (size is None or file.stat().st_size == size) and sha(file) == digest


def fetch(url, target, digest, size=None, local=None):
    """Only verified bytes replace the destination. Partial or corrupt downloads are removed."""
    if matches(target, digest, size):
        print('Verified:', target.name, flush=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=target.name+'.', suffix='.partial', dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        print('Installing:', target.name, flush=True)
        if local:
            stream = local.open('rb')
        else:
            stream = urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'llama-receipts-setup/1'}),timeout=60)
        with stream, temporary.open('wb') as out:
            count=0
            while data := stream.read(1024*1024):
                count += len(data)
                if size is not None and count > size:
                    raise ValueError(target.name+': download exceeds the pinned size')
                out.write(data)
        if not matches(temporary,digest,size):
            raise ValueError(target.name+': checksum or size mismatch; existing file preserved')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def assets_for(release, all_circuits=False, include_setup=False):
    for asset in release['assets']:
        if asset['circuit'] is None:
            if include_setup: yield asset
        elif (all_circuits or asset['circuit']==DEFAULT_CIRCUIT) and (include_setup or asset['path']!='main.r1cs'):
            yield asset


def destination(root, asset):
    # The checked-in release manifest is trusted, but fail closed on unexpected paths.
    circuit=asset['circuit']
    if circuit is None:
        if asset['path']!='ptau/pot18_final.ptau': raise ValueError('Unexpected setup asset path')
        return root/G16_REL/asset['path']
    if circuit not in ('r16_k1024','r16_k1536','r8_k2048','r8_k3072') or asset['path'] not in ('main_final.zkey','main_js/main.wasm','main.r1cs'):
        raise ValueError('Unexpected circuit asset path')
    return root/G16_REL/'build'/circuit/asset['path']


def run(*args):
    subprocess.run([str(a) for a in args],cwd=ROOT,check=True)


def native_state(release):
    native=ROOT/'code/llama.cpp'
    actual=subprocess.check_output(['git','-C',str(native),'rev-parse','HEAD'],text=True).strip()
    if actual!=release['fork_commit']:
        raise ValueError('The llama.cpp checkout differs from the release pin. Restore the recorded submodule revision before installation.')
    dirty=subprocess.check_output(['git','-C',str(native),'status','--porcelain','--untracked-files=no'],text=True)
    if dirty.strip(): raise ValueError('The llama.cpp checkout has local source edits; use a clean checkout for reproducible setup.')


def install_registered_model(release, model, target, asset_dir=None):
    # Quantization can differ across CPU architectures. Install authenticated bytes.
    asset=release['registered_model']
    if asset['sha256']!=model['file_sha256'] or asset['bytes']!=model['file_bytes']:
        raise ValueError('Published model asset does not match the trusted registration')
    if asset['name']!='qwen3-0.6b-q4_k_m.gguf':
        raise ValueError('Unexpected registered model asset name')
    fetch(release['base_url']+asset['name'],target,model['file_sha256'],model['file_bytes'],
          asset_dir/asset['name'] if asset_dir else None)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true',help='Check installed files without rebuilding or downloading assets')
    p.add_argument('--materials-only',action='store_true',help='Install/check proving materials and Node dependencies only')
    p.add_argument('--all-circuits',action='store_true')
    p.add_argument('--include-setup',action='store_true',help='Also install R1CS and the existing powers-of-tau file')
    p.add_argument('--asset-dir',type=Path,help='Install from an offline copy of the release assets')
    p.add_argument('--model',type=Path,help='Use an existing exact registered GGUF instead of downloading and quantizing')
    p.add_argument('--jobs',type=int,default=4)
    a=p.parse_args()
    if not 1<=a.jobs<=16: p.error('--jobs must be between 1 and 16')
    release=json.loads((ROOT/'releases/prover-materials-v1.json').read_text())
    required=['git','node','npm']+([] if a.materials_only else ['cmake'])
    missing=[name for name in required if not shutil.which(name)]
    if missing: raise ValueError('Install these tools first: '+', '.join(missing))
    if not (ROOT/'code/llama.cpp/include/llama.h').exists():
        if a.check: raise ValueError('Submodule missing. Run git submodule update --init --recursive.')
        run('git','submodule','update','--init','--recursive')
    native_state(release)
    problems=[]
    g16=ROOT/G16_REL
    node_cli=g16/'node_modules/snarkjs/build/cli.cjs'
    if a.check:
        if not node_cli.exists(): problems.append('Node verifier dependencies missing')
    else:
        run('npm','ci','--prefix',g16)
    for asset in assets_for(release,a.all_circuits,a.include_setup):
        target=destination(ROOT,asset)
        if a.check:
            if not matches(target,asset['sha256'],asset['bytes']): problems.append('Missing or mismatched: '+str(target.relative_to(ROOT)))
        else:
            fetch(release['base_url']+asset['name'],target,asset['sha256'],asset['bytes'],a.asset_dir/asset['name'] if a.asset_dir else None)
    circuits={asset['circuit'] for asset in assets_for(release,a.all_circuits,a.include_setup) if asset['circuit']}
    for circuit in sorted(circuits):
        source=ROOT/'registry/circuits'/circuit/'verification_key.json'
        target=g16/'build'/circuit/'verification_key.json'
        if a.check:
            if not target.exists() or json.loads(target.read_text())!=json.loads(source.read_text()): problems.append(circuit+': verification key mismatch')
        else:
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    if not a.materials_only:
        binary=ROOT/'code/llama.cpp/build/bin/llama-receipts'
        quantize=ROOT/'code/llama.cpp/build/bin/llama-quantize'
        if a.check:
            if not binary.exists(): problems.append('Native llama-receipts executable missing')
            if not quantize.exists(): problems.append('Native llama-quantize executable missing')
        else:
            run('cmake','-S','code/llama.cpp','-B','code/llama.cpp/build','-DLLAMA_BUILD_EXAMPLES=ON','-DCMAKE_BUILD_TYPE=Release')
            run('cmake','--build','code/llama.cpp/build','--target','llama-receipts','llama-quantize','-j',a.jobs)
        model=json.loads((ROOT/'registry/qwen3-0.6b-q4_k_m/manifest.json').read_text())['model']
        target=ROOT/'models/qwen3-0.6b-q4_k_m.gguf'
        if a.check:
            if not matches(target,model['file_sha256'],model['file_bytes']): problems.append('Registered model missing or checksum mismatch')
        elif not matches(target,model['file_sha256'],model['file_bytes']):
            if target.exists(): raise ValueError('The model at '+str(target)+' has a different checksum. Move it aside; setup will not overwrite it.')
            if a.model:
                fetch('',target,model['file_sha256'],model['file_bytes'],a.model.resolve())
            else:
                install_registered_model(release,model,target,a.asset_dir)
    if problems: raise ValueError('\n'.join(problems))
    print('Proving materials verified.' if a.materials_only else 'Workspace ready. Run ./start-workspace.sh',flush=True)
    return 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        print('Setup stopped: '+str(error),file=sys.stderr);raise SystemExit(1)
