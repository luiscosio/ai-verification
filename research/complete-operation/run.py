#!/usr/bin/env python3
"""Prove all rows of one F20 matvec, keeping all activation openings local."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, platform, secrets, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
G16=ROOT/'code/llama.cpp/examples/receipts/zk/groth16'
SNARK=G16/'node_modules/snarkjs/build/cli.cjs'
spec=importlib.util.spec_from_file_location('reference',ROOT/'docs/stage4/fixed_point_forward.py')
ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
P=21888242871839275222246405745257275088548364400416034343698204186575808495617

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,separators=(',',':'))+'\n')
def field(v):return str(int(v)%P)
def bits(values,n):return [str((int(v)>>b)&1) for v in np.asarray(values).reshape(-1) for b in range(n)]
def strings(values):return [str(int(v)) for v in np.asarray(values).reshape(-1)]
def commit(value):return json.loads(subprocess.check_output(['node',str(HERE/'commit.cjs')],input=json.dumps(value),text=True))

def measured(cmd,timeout=600):
    with tempfile.TemporaryDirectory() as d:
        metric=Path(d)/'time.txt';start=time.perf_counter()
        wrapper=['/usr/bin/time','-l' if sys.platform=='darwin' else '-v','-o',str(metric)]
        with subprocess.Popen(wrapper+[str(x) for x in cmd],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True) as process:
            try:
                stdout,stderr=process.communicate(timeout=timeout)
            finally:
                # Killing only /usr/bin/time leaves the actual prover running.
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait()
        result=subprocess.CompletedProcess(cmd,process.returncode,stdout,stderr)
        elapsed=time.perf_counter()-start
        text=metric.read_text() if metric.exists() else ''
        rss=None
        for line in text.splitlines():
            if 'maximum resident set size' in line.lower():
                rss=int(line.strip().split()[0]) if sys.platform=='darwin' else int(line.rsplit(':',1)[1])*1024
        if result.returncode:raise RuntimeError('Command failed: '+str(cmd[0])+'\n'+result.stderr[-1200:]+result.stdout[-1200:])
        return {'seconds':round(elapsed,4),'peak_process_rss_bytes':rss},result.stdout

def prove(build,inputs,work):
    write(work/'input.json',inputs)
    witness,_=measured(['node',SNARK,'wtns','calculate',build/'main_js/main.wasm',work/'input.json',work/'witness.wtns'])
    proving,_=measured(['node',SNARK,'groth16','prove',build/'main_final.zkey',work/'witness.wtns',work/'proof.json',work/'public.json'])
    value={'proof':json.loads((work/'proof.json').read_text()),'public':json.loads((work/'public.json').read_text())}
    (work/'input.json').unlink();(work/'witness.wtns').unlink()
    return value,{'witness':witness,'proving':proving}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--model',type=Path,default=ROOT/'models/qwen3-0.6b-q4_k_m.gguf');p.add_argument('--token-id',type=int,default=0);a=p.parse_args()
    a.build=a.build.resolve();a.out=a.out.resolve()
    if a.out.exists() and any(a.out.iterdir()):raise ValueError('Use a fresh output directory; old results must not be reused.')
    a.out.mkdir(parents=True,exist_ok=True)
    canonical_model=json.loads((ROOT/'registry/qwen3-0.6b-q4_k_m/manifest.json').read_text())
    if sha(a.model)!=canonical_model['model']['file_sha256']:raise ValueError('Unexpected model file')
    model=ref.Model(str(a.model),20);tensor='blk.0.attn_k.weight';rows=16;k=1024;m=1024;nb=4
    if not 0 <= a.token_id < model.store.blocks('token_embd.weight').shape[0]:
        raise ValueError('Token ID is outside the registered vocabulary')
    x=model.rms_norm(model.embed(a.token_id),model.consts_vec('blk.0.attn_norm.weight'))
    start=time.perf_counter();y=model.matmul(tensor,x);reference_seconds=time.perf_counter()-start
    da,q8,bsums=model.quantize_q8k(x)
    dw,dmin,sc,mn,q4=ref.vt.unpack_q4_k(model.store.blocks(tensor))
    D=np.array([ref.const(float(v)) for v in dw.reshape(-1)],dtype=object).reshape(m,nb)
    Dmin=np.array([ref.const(float(v)) for v in dmin.reshape(-1)],dtype=object).reshape(m,nb)
    sub=np.einsum('mijl,ijl->mij',q4.reshape(m,nb,8,32).astype(np.int64),q8.reshape(nb,8,32))
    s1=np.einsum('mij,mij->mi',sub,sc.astype(np.int64));s2=np.einsum('ij,mij->mi',bsums,np.repeat(mn.astype(np.int64),2,axis=-1))
    weight_groups=[]
    for g in range(64):
        r=slice(g*rows,(g+1)*rows)
        weight_groups.append({key:strings(arr[r]) for key,arr in [('q4',q4),('sc',sc),('mn',mn),('D',D),('Dmin',Dmin)]})
    commitments=commit({'groups':weight_groups,'rows':rows,'k':k})
    registry=a.out/'registry';registry.mkdir();keys={}
    for name in ['quant_k1024','rows16_k1024']:
        key=registry/(name+'.json');shutil.copyfile(a.build/name/'verification_key.json',key);keys[name]=sha(key)
    registration={'claim':'experimental/f20-q4k-matvec/v1','model_file_sha256':sha(a.model),'tensor':tensor,'m':m,'k':k,'rows_per_group':rows,'weight_commitments':commitments,'keys':keys,'verifier_sha256':sha(HERE/'verify.cjs'),'circuit_sha256':sha(HERE/'full_matvec.circom'),'integer_core_sha256':sha(G16/'qdot_rows.circom'),'setup_sha256':sha(G16/'ptau/pot18_final.ptau'),'trust':'Local research registration and single-contributor setup; independent review pending.'}
    write(registry/'registration.json',registration);registration_id=sha(registry/'registration.json')
    context=secrets.randbelow(P);input_salt=secrets.randbelow(P);quant_salt=secrets.randbelow(P)
    input_commit=str(commit({'values':strings(x),'domain':3002,'context':str(context),'salt':str(input_salt)}))
    quant_commit=str(commit({'values':strings(list(q8)+list(da)),'domain':3004,'context':str(context),'salt':str(quant_salt)}))
    timings=[]
    with tempfile.TemporaryDirectory(prefix='private-matvec-') as folder:
        work=Path(folder)
        qinputs={'x':[field(v) for v in x],'context':str(context),'inputSalt':str(input_salt),'quantSalt':str(quant_salt)}
        quant,metric=prove(a.build/'quant_k1024',qinputs,work)
        assert quant['public']==[input_commit,quant_commit,str(context)]
        timings.append({'phase':'quantization',**metric});print('Quantization proved',metric,flush=True)
        groups=[]
        for g in range(64):
            r=slice(g*rows,(g+1)*rows);output_salt=secrets.randbelow(P)
            inputs={'q8':[field(v) for v in q8],'da':[field(v) for v in da],'y':[field(v) for v in y[r]],'q4bits':bits(q4[r],4),'scbits':bits(sc[r],6),'mnbits':bits(mn[r],6),'D':[field(v) for v in D[r].reshape(-1)],'Dmin':[field(v) for v in Dmin[r].reshape(-1)],'s1':[field(v) for v in s1[r].reshape(-1)],'s2':[field(v) for v in s2[r].reshape(-1)],'context':str(context),'group':str(g),'quantSalt':str(quant_salt),'outputSalt':str(output_salt)}
            item,metric=prove(a.build/'rows16_k1024',inputs,work)
            expected_output=str(commit({'values':strings(y[r]),'domain':3003,'context':str(context),'index':g,'salt':str(output_salt)}))
            assert item['public']==[commitments[g],quant_commit,expected_output,str(context),str(g)]
            groups.append(item);timings.append({'phase':'rows','group':g,**metric})
            print(f'Rows {(g+1)*rows}/{m} proved',metric,flush=True)
        package={'format':registration['claim'],'registration_id':registration_id,'context':str(context),'input_commitment':input_commit,'quant':quant,'groups':groups}
        write(a.out/'operation.proof.json',package)
    verify_metric,stdout=measured(['node',HERE/'verify.cjs',a.out/'operation.proof.json',registry]);verdict=json.loads(stdout)
    report={'claim':registration['claim'],'registration_id':registration_id,'input_source':f'F20 normalized embedding of registered token ID {a.token_id}; preparation itself outside this proof','reference_seconds':reference_seconds,'measurements':timings,'verification':verdict,'verification_process':verify_metric,'machine':{'platform':platform.platform(),'machine':platform.machine(),'python':platform.python_version()},'sources':{'root_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),'driver_sha256':sha(__file__),'circuit_sha256':sha(HERE/'full_matvec.circom')},'privacy':'No input/output openings, activation values or witnesses exported. Metadata and commitments are public.'}
    write(a.out/'report.json',report);print(json.dumps(verdict),flush=True)

if __name__=='__main__':main()
