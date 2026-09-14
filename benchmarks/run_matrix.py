#!/usr/bin/env python3
"""Real native generation, replay and registered row proofs on a fixed public corpus."""
import argparse,hashlib,json,random,re,statistics,subprocess,sys,tempfile
from pathlib import Path
from measure import measure,environment
ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'code/llama.cpp/build/bin/llama-receipts'
G16=ROOT/'code/llama.cpp/examples/receipts/zk/groth16'
MODELS={
 'qwen3-0.6b':(ROOT/'models/qwen3-0.6b-q4_k_m.gguf','qwen3-0.6b-q4_k_m'),
 'qwen2.5-0.5b':(ROOT/'models/qwen2.5-0.5b-instruct-q4_k_m.gguf','qwen2.5-0.5b-q4_k_m'),
 'qwen2.5-1.5b':(Path.home()/'.ollama/models/blobs/sha256-183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4','qwen2.5-1.5b-q4_k_m'),
 'phi3-mini':(Path.home()/'.ollama/models/blobs/sha256-633fc5be925f9a484b61d6f9b9a78021eeb462100bd557309f01ba84cac26adf',None)}

def resolve_models(names, overrides=()):
    models={name:MODELS[name] for name in names.split(',')}
    for value in overrides:
        name,separator,file=value.partition('=')
        if not separator or name not in models or not file:
            raise ValueError('Use --model NAME=PATH for a selected model')
        models[name]=(Path(file).expanduser().resolve(),models[name][1])
    return models

def digest(file):
    with file.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(file,value):file.write_text(json.dumps(value,indent=2)+'\n')
def corpus():
    return [{**p,'prompt':p['prompt']*p.get('repeat',1)+p.get('suffix','')} for p in json.loads((ROOT/'benchmarks/corpus.json').read_text())]

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--suite',choices=['native','row-proofs'],default='native');p.add_argument('--models',default=','.join(MODELS));p.add_argument('--limit',type=int);p.add_argument('--model',action='append',default=[],metavar='NAME=PATH',help='Override a selected model path');p.add_argument('--case-plan',type=Path,help='Run a saved public case list instead of the default matrix');a=p.parse_args()
    if a.limit is not None and a.limit<1:p.error('--limit must be positive')
    env=environment(ROOT)
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    models=resolve_models(a.models,a.model);identities={}
    for name,(file,reg) in models.items():
        if not file.exists():raise ValueError('Missing model: '+name)
        value=digest(file)
        if reg:
            if value!=json.loads((ROOT/'registry'/reg/'manifest.json').read_text())['model']['file_sha256']:raise ValueError('Model does not match registration: '+name)
        identities[name]={'sha256':value,'bytes':file.stat().st_size,'registration':reg}
    write(a.out/'environment.json',env|{'models':identities,'suite':a.suite,'corpus_sha256':digest(ROOT/'benchmarks/corpus.json'),'driver_sha256':digest(Path(__file__)),'monitor_sha256':digest(ROOT/'benchmarks/measure.py'),'native_binary_sha256':digest(BIN),'native_source_sha256':digest(ROOT/'code/llama.cpp/examples/receipts/receipts.cpp'),'fork_commit':subprocess.check_output(['git','-C',str(ROOT/'code/llama.cpp'),'rev-parse','HEAD'],text=True).strip()})
    prompts=corpus();cases=[]
    if a.suite=='native':
        for name in models:
            for item in prompts:
                for threads in [2,8]:
                    for repeat in [0,1]:cases.append({'model':name,'prompt':item['id'],'threads':threads,'repeat':repeat,'temperature':0})
            for item in prompts[:2]:
                for repeat in [0,1]:cases.append({'model':name,'prompt':item['id'],'threads':8,'repeat':repeat,'temperature':.7})
        random.Random(20260913).shuffle(cases)
    else:
        for name in ['qwen3-0.6b','qwen2.5-1.5b']:
            if name in models:
                for i,item in enumerate(prompts[:3]):cases.append({'model':name,'prompt':item['id'],'threads':8,'repeat':0,'temperature':0,'k':([1024,2048,3072][i] if name=='qwen3-0.6b' else 1536)})
    if a.case_plan:cases=json.loads(a.case_plan.read_text())
    if a.limit:cases=cases[:a.limit]
    if not cases:p.error('No benchmark cases selected; choose a supported model for this suite')
    write(a.out/'plan.json',cases);outcomes=[];seen={}
    for number,case in enumerate(cases):
        name=case['model'];file,reg=models[name];prompt=next(x['prompt'] for x in prompts if x['id']==case['prompt']);record={'case':case,'checks':{},'metrics':{}}
        try:
            with tempfile.TemporaryDirectory(prefix='private-receipts-benchmark-') as directory:
                work=Path(directory);receipt=work/'receipt.json';n=2 if a.suite=='row-proofs' else 8
                args=[BIN,'-m',file,'-p',prompt,'-n',str(n),'--temp',str(case['temperature']),'--seed','17','-ngl','0','-t',str(case['threads']),'-c','1024','-b','512','--out',receipt]
                reference_tokens=None
                if a.suite=='row-proofs':
                    plain,_,error=measure(args,work);record['metrics']['generation_without_trace']=plain
                    if plain['returncode']:raise ValueError('Untraced generation failed: '+error[-500:])
                    reference_tokens=json.loads(receipt.read_text())['response']['tokens']
                    args+=['--trace','--openings','2048']
                metric,stdout,stderr=measure(args,work);record['metrics']['generation']=metric
                if metric['returncode']:raise ValueError('Generation failed: '+stderr[-500:])
                rec=json.loads(receipt.read_text());tokens=rec['response']['tokens'];record['engine']=rec['engine'];record.update(prompt_tokens=len(rec['request']['prompt_tokens']),output_tokens=len(tokens),token_ids=tokens,end_to_end_tokens_per_second=len(tokens)/metric['seconds'])
                if reference_tokens is not None:
                    record['checks']['trace_preserves_tokens']=tokens==reference_tokens
                    record['capture_overhead_seconds']=metric['seconds']-record['metrics']['generation_without_trace']['seconds']
                for label,pattern in [('native_generation',r'generated \d+ tokens in ([\d.]+) s'),('model_commitment',r'model committed: .*?, ([\d.]+) s')]:
                    found=re.search(pattern,stderr)
                    if found:record[label+'_seconds']=float(found[1])
                record['checks']['model_identity']=rec['model']['file_sha256']==identities[name]['sha256']
                for label,pattern in [('prompt',r'prompt eval time\s*=\s*([\d.]+) ms /\s*(\d+) tokens'),('decode',r'(?<!prompt )eval time\s*=\s*([\d.]+) ms /\s*(\d+) runs')]:
                    match=re.search(pattern,stderr)
                    if match:record[label+'_timing']={'milliseconds':float(match[1]),'tokens':int(match[2]),'tokens_per_second':int(match[2])*1000/float(match[1]) if float(match[1]) else None}
                identity=(name,case['prompt'],case['threads'],case['temperature'])
                if identity in seen:record['checks']['repeat_tokens_match']=tokens==seen[identity]
                else:seen[identity]=tokens
                metric,_,error=measure([BIN,'-m',file,'--check-content',receipt],work)
                record['metrics']['content_check']=metric;record['checks']['content']=metric['returncode']==0
                if a.suite=='native' and case['repeat']==0:
                    metric,_,error=measure([BIN,'-m',file,'-ngl','0','-t',str(case['threads']),'-c','1024','-b','512','--replay',receipt,'--report',work/'replay.json'],work)
                    record['metrics']['replay']=metric
                    replay=json.loads((work/'replay.json').read_text()) if (work/'replay.json').exists() else {}
                    record['replay_reason']=replay.get('reason');record['replay']=replay.get('summary',{});record['checks']['replay']=metric['returncode']==0 and replay.get('verdict')=='accept'
                if a.suite=='row-proofs':
                    manifest=json.loads((ROOT/'registry'/reg/'manifest.json').read_text());entries={t['name']:t for t in manifest['tensors'] if t.get('groth16') and t['shape'][0]==case['k']}
                    trace=json.loads((work/'receipt.trace.json').read_text());candidates=[]
                    record['trace_bytes']=(work/'receipt.trace.json').stat().st_size
                    for opening in trace['openings']:
                        leaf=trace['leaves'][opening['index']]
                        if leaf['op']=='MUL_MAT' and leaf['out']['ne'][1]==1 and leaf['srcs']:
                            tensor=leaf['srcs'][0].get('base',{}).get('name')
                            if tensor in entries:candidates.append((opening['index'],tensor))
                    if not candidates:raise ValueError('No opened registered operation for K='+str(case['k']))
                    index,tensor=min(candidates);entry=entries[tensor];groups=sorted({0,len(entry['groth16']['groups'])//2,len(entry['groth16']['groups'])-1});del trace
                    metric,_,error=measure([sys.executable,G16/'groth16_node.py',receipt,'--model',file,'--index',str(index),'--groups',','.join(map(str,groups)),'--manifest',ROOT/'registry'/reg/'manifest.json','--out',work/'proof'],work)
                    record['metrics']['row_proofs']=metric
                    if metric['returncode']:raise ValueError('Prover failed: '+error[-600:])
                    summary=json.loads((work/'proof/summary.json').read_text());record['proof_summary']=summary
                    record['checks']['registered_proofs']=all(g['accept'] and g['bound'] and not g['tampered_sum_accepted'] and not g['other_group_accepted'] for g in summary['groups'])
                    record['proof_files']=[];record['checks']['exported_proofs']=True;record['checks']['wrong_group_rejected']=True
                    public_dir=a.out/'proofs';public_dir.mkdir(exist_ok=True)
                    for group in groups:
                        private_dir=work/'proof'/f'group{group}'
                        package={'format':'llama-receipts/proof-package/v1','claim':'q4k-integer-row-group/v1','registration_id':manifest['manifest_id'],'tensor':tensor,'group':group,'proof':json.loads((private_dir/'proof.json').read_text()),'public':json.loads((private_dir/'public.json').read_text())}
                        public_file=public_dir/f'{name}-{case["prompt"]}-k{case["k"]}-g{group}.llamaproof'
                        write(public_file,package)
                        record['proof_files'].append({'file':str(public_file.relative_to(a.out)),'sha256':digest(public_file),'bytes':public_file.stat().st_size})
                        metric,stdout,_=measure(['node',ROOT/'site/verify-file.cjs',public_file],work)
                        record['metrics'][f'export_verification_{group}']=metric
                        record['checks']['exported_proofs'] &= metric['returncode']==0 and json.loads(stdout).get('accept') is True
                        package['group']=(group+1)%len(entry['groth16']['groups']);bad=work/'wrong-group.llamaproof';write(bad,package)
                        metric,stdout,_=measure(['node',ROOT/'site/verify-file.cjs',bad],work)
                        record['metrics'][f'wrong_group_{group}']=metric
                        record['checks']['wrong_group_rejected'] &= metric['returncode']==1 and json.loads(stdout).get('status')=='invalid'

                record['passed']=all(record['checks'].values())
        except Exception as error:record['passed']=False;record['error']=str(error)
        outcomes.append(record)
        with (a.out/'results.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
        print(f'{number+1}/{len(cases)} {case} '+('PASS' if record['passed'] else 'FAIL '+record.get('error',str(record['checks']))),flush=True)
    write(a.out/'summary.json',{'cases':len(outcomes),'passed':sum(r['passed'] for r in outcomes),'failed':sum(not r['passed'] for r in outcomes)})
    return int(any(not r['passed'] for r in outcomes))

if __name__=='__main__':raise SystemExit(main())
