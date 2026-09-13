#!/usr/bin/env python3
"""Recompute the research weight registration from the operator's own GGUF."""
import argparse,json
from pathlib import Path
import numpy as np
from run import ROOT,HERE,G16,ref,sha,commit,strings

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('registry',type=Path)
    p.add_argument('--model',type=Path,default=ROOT/'models/qwen3-0.6b-q4_k_m.gguf')
    a=p.parse_args();r=json.loads((a.registry/'registration.json').read_text())
    expected=json.loads((ROOT/'registry/qwen3-0.6b-q4_k_m/manifest.json').read_text())['model']['file_sha256']
    assert r['model_file_sha256']==sha(a.model)==expected,'Model identity mismatch'
    assert (r['claim'],r['tensor'],r['m'],r['k'],r['rows_per_group'])==('experimental/f20-q4k-matvec/v1','blk.0.attn_k.weight',1024,1024,16)
    for name in ['quant_k1024','rows16_k1024']:
        assert sha(a.registry/(name+'.json'))==r['keys'][name],'Key digest mismatch'
    assert sha(HERE/'verify.cjs')==r['verifier_sha256'],'Verifier source mismatch'
    assert sha(HERE/'full_matvec.circom')==r['circuit_sha256'],'Circuit source mismatch'
    assert sha(G16/'qdot_rows.circom')==r['integer_core_sha256'],'Integer core mismatch'
    model=ref.Model(str(a.model),20)
    dw,dm,sc,mn,q4=ref.vt.unpack_q4_k(model.store.blocks(r['tensor']))
    assert np.isfinite(dw).all() and np.isfinite(dm).all(),'Nonfinite GGUF scales'
    scales=[np.array([ref.const(float(v)) for v in data.reshape(-1)],dtype=object).reshape(1024,4) for data in [dw,dm]]
    groups=[]
    for g in range(64):
        rows=slice(g*16,(g+1)*16)
        groups.append({key:strings(data[rows]) for key,data in [('q4',q4),('sc',sc),('mn',mn),('D',scales[0]),('Dmin',scales[1])]})
    assert commit({'groups':groups,'rows':16,'k':1024})==r['weight_commitments'],'Registered weights or scales differ from GGUF'
    print('All 64 weight-and-scale commitments match the exact GGUF. Key/source digests match. This does not audit the ceremony or prove that the keys were derived from this circuit.')

if __name__=='__main__':main()
