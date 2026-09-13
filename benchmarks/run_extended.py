#!/usr/bin/env python3
"""Sequential throughput, native negative controls and complete-operation profiles."""
import argparse,copy,json,subprocess,sys,tempfile
from pathlib import Path
from measure import measure,environment
from run_matrix import ROOT,BIN,MODELS,digest,write,resolve_models

def checked(command,cwd,timeout=900):
    metrics,out,err=measure(command,cwd,timeout)
    if metrics['returncode']:raise RuntimeError(f'Command failed ({metrics["returncode"]}): {err[-1000:]} {out[-500:]}')
    return metrics,out

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--suite',choices=['throughput','complete-operation','native-negatives'],required=True);parser.add_argument('--models',default=','.join(MODELS));parser.add_argument('--model',action='append',default=[],metavar='NAME=PATH');a=parser.parse_args();models=resolve_models(a.models,a.model)
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    write(a.out/'environment.json',environment(ROOT)|{'suite':a.suite,'driver_sha256':digest(Path(__file__)),'monitor_sha256':digest(ROOT/'benchmarks/measure.py')})
    if a.suite=='throughput':
        bench=ROOT/'code/llama.cpp/build/bin/llama-bench'
        if not bench.exists():subprocess.run(['cmake','--build',str(ROOT/'code/llama.cpp/build'),'--target','llama-bench','-j','2'],check=True)
        for name,(model,_) in models.items():
            for threads in [2,8]:
                metrics,out=checked([bench,'-m',model,'-ngl','0','-t',str(threads),'-p','32,128,512','-n','32,128','-r','3','-b','512','-ub','512','-o','json'],ROOT)
                rows=json.loads(out)
                assert len(rows)==5 and all(len(r['samples_ns'])==3 and r['avg_ts']>0 for r in rows)
                # Absolute model paths are irrelevant to public evidence.
                for r in rows:r['model_filename']=name
                value={'model':name,'model_sha256':digest(model),'threads':threads,'metrics':metrics,'results':rows}
                write(a.out/f'{name}-t{threads}.json',value);print(name,threads,'throughput PASS',flush=True)
    elif a.suite=='complete-operation':
        for token in [0,198,512]:
            folder=a.out/f'token-{token}'
            metrics,_=checked([sys.executable,ROOT/'research/complete-operation/run.py','--build',ROOT/'.receipts-research','--model',models['qwen3-0.6b'][0],'--token-id',str(token),'--out',folder],ROOT,1200)
            report=json.loads((folder/'report.json').read_text());assert report['verification']['accept']
            write(folder/'resources.json',metrics)
            check,output=checked(['node',ROOT/'research/complete-operation/check_package.cjs',folder/'operation.proof.json',folder/'registry'],ROOT)
            write(folder/'negative-controls.json',{'metrics':check,'output':output})
            print('Complete operation token',token,'PASS',metrics['seconds'],'seconds',flush=True)
    else:
        results=[]
        for name,(model,_) in models.items():
            with tempfile.TemporaryDirectory(prefix='private-native-negative-') as d:
                d=Path(d);file=d/'receipt.json'
                checked([BIN,'-m',model,'-p','The capital of France is','-n','4','--temp','0','--seed','17','-ngl','0','-t','8','-c','1024','-b','512','--out',file],d)
                original=json.loads(file.read_text())
                for change in ['honest','text','prompt','version','token-id','per-token-record','other-model']:
                    value=copy.deepcopy(original);selected=model
                    if change=='text':value['response']['text']='different answer'
                    if change=='prompt':value['request']['prompt_text']='different prompt'
                    if change=='version':value['receipt_version']='999'
                    if change=='token-id':value['response']['tokens'][0]=99999999
                    if change=='per-token-record':value['response']['per_token'][0]['token']+=1
                    if change=='other-model':selected=next(m for k,(m,_) in models.items() if k!=name)
                    file.write_text(json.dumps(value))
                    if change=='other-model':
                        report=d/'replay.json'
                        metrics,_,_=measure([BIN,'-m',selected,'-ngl','0','-t','8','-c','1024','-b','512','--replay',file,'--report',report],d)
                        accepted=metrics['returncode']==0 and report.exists() and json.loads(report.read_text()).get('verdict')=='accept'
                    else:
                        metrics,_,_=measure([BIN,'-m',selected,'--check-content',file],d)
                        accepted=metrics['returncode']==0
                    results.append({'model':name,'change':change,'accepted':accepted,'passed':accepted==(change=='honest'),'metrics':metrics})
                    print(name,change,'PASS' if results[-1]['passed'] else 'FAIL',flush=True)
        write(a.out/'results.json',results)
        if not all(r['passed'] for r in results):return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
