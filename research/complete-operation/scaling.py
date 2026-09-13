#!/usr/bin/env python3
"""Measured one-operation costs and explicitly limited Q4-only scaling estimates."""
import argparse,json,statistics,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def r1cs_header(file):
    with file.open('rb') as f:
        assert f.read(4)==b'r1cs';version,sections=struct.unpack('<II',f.read(8));assert version==1
        for _ in range(sections):
            kind,size=struct.unpack('<IQ',f.read(12));data=f.read(size)
            if kind==1:
                field_bytes=struct.unpack('<I',data[:4])[0];offset=4+field_bytes
                wires,outputs,public,private=struct.unpack('<IIII',data[offset:offset+16])
                labels,constraints=struct.unpack('<QI',data[offset+16:offset+28])
                return {'constraints':constraints,'wires':wires,'public_signals':outputs+public}
    raise ValueError('Missing R1CS header')

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args()
    report=json.loads((a.run/'report.json').read_text());manifest=json.loads((ROOT/'registry/qwen3-0.6b-q4_k_m/manifest.json').read_text())
    measurements=report['measurements'];rows=[x for x in measurements if x['phase']=='rows']
    weights=sum(t['shape'][0]*t['shape'][1] for t in manifest['tensors'] if t['type']=='Q4_K')
    units=weights/(16*1024);prove=statistics.median(x['proving']['seconds'] for x in rows)
    witness=statistics.median(x['witness']['seconds'] for x in rows)
    operation={'rows':1024,'k':1024,'proofs':65,'witness_seconds':sum(x['witness']['seconds'] for x in measurements),'prove_seconds':sum(x['proving']['seconds'] for x in measurements),'peak_process_rss_bytes':max(x['proving']['peak_process_rss_bytes'] for x in measurements),'reference_seconds':report['reference_seconds'],'package_bytes':report['verification']['bytes'],'verify_seconds':report['verification']['verify_ms']/1000,'cold_verifier_process_seconds':report['verification_process']['seconds']}
    headers={name:r1cs_header(a.build/name/'main.r1cs') for name in ('quant_k1024','rows16_k1024')}
    result={'measured_operation':operation,'circuit_counts':headers,'q4_weight_values_per_token':weights,'q4_only_extrapolation':{'equivalent_16x1024_groups':units,'prove_hours':units*prove/3600,'witness_hours':units*witness/3600,'assumption':'Linear scaling of measured 16x1024 row proof work with Q4 weight count. Not a measured full-token runtime and not a lower-bound theorem. Other K shapes may require smaller groups or larger keys.','excludes':['Q6_K','quantization at every operation','nonlinear operations','KV state','private boundary repacking/link proofs','token selection','aggregation/compression','registration and setup']},'provisional_reference_thresholds':{'package_bytes':50*1024*1024,'verification_seconds':10,'operation_package_within':operation['package_bytes']<=50*1024*1024,'operation_verification_within':operation['verify_seconds']<=10},'conclusion':'Serial grouped Groth16 is a useful complete-operation checkpoint, but these measured costs do not support a practical whole-token claim. Compare a lookup-based prover with equivalent privacy and arithmetic semantics before porting the entire forward pass.'}
    (a.run/'scaling.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
