#!/usr/bin/env python3
"""Install the exact measured research circuits; does not generate a ceremony."""
import argparse,importlib.util,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('setup_workspace',ROOT/'tools/setup_workspace.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,default=ROOT/'.receipts-research')
    p.add_argument('--asset-dir',type=Path)
    a=p.parse_args()
    results=HERE/'results/2026-09-13'
    environment=json.loads((results/'environment.json').read_text())
    for relative,asset in environment['artifacts'].items():
        item=Path(relative)
        if item.parts[0] not in ('quant_k1024','rows16_k1024') or str(Path(*item.parts[1:])) not in ('main.r1cs','main_final.zkey','main_js/main.wasm','main.circom'):
            raise ValueError('Unexpected research artifact path')
        name=item.parts[0]+'-'+item.name
        url='https://github.com/luiscosio/ai-verification/releases/download/complete-operation-v1/'+name
        setup.fetch(url,a.build/item,asset['sha256'],asset['bytes'],a.asset_dir/name if a.asset_dir else None)
    for name in ['quant_k1024','rows16_k1024']:
        shutil.copyfile(results/'registry'/(name+'.json'),a.build/name/'verification_key.json')
    print('Measured research materials installed. These are experimental single-contributor parameters.')

if __name__=='__main__':main()
