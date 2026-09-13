#!/usr/bin/env python3
"""Summarize completed public benchmark evidence; do not infer missing runs."""
import argparse,gzip,json,math,statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def read(p):return json.loads(p.read_text())
def percentile(values,q):
    values=sorted(values);i=(len(values)-1)*q;lo=math.floor(i);hi=math.ceil(i)
    return values[lo]+(values[hi]-values[lo])*(i-lo)
def fmt(n):return f'{n:.2f}'
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,row))+' |' for row in rows])
def main():
    p=argparse.ArgumentParser();p.add_argument('--native',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    cases=[json.loads(s) for s in (a.native/'results.jsonl').read_text().splitlines()];env=read(a.native/'environment.json');plan=read(a.native/'plan.json')
    if len(cases)!=len(plan):raise ValueError('Matrix is incomplete')
    names=sorted({c['case']['model'] for c in cases});rows=[]
    for name in names:
        for t in [2,8]:
            selected=[c for c in cases if c['case']['model']==name and c['case']['threads']==t];metrics=[c['metrics']['generation'] for c in selected];times=[m['seconds'] for m in metrics]
            rows.append([name,t,len(selected),fmt(statistics.median(times)),fmt(percentile(times,.95)),fmt(max(m['os_peak_process_rss_bytes'] or 0 for m in metrics)/2**30),fmt(max(m['sampled_peak_tree_rss_bytes'] for m in metrics)/2**30)])
    checks={name:[c['checks'][name] for c in cases if name in c['checks']] for name in sorted({name for c in cases for name in c['checks']})}
    lines=['# Four-model native matrix','',f"Machine: {env['cpu']}; {env['logical_cpus']} logical CPUs; {env['physical_memory_bytes']/2**30:.0f} GiB RAM. CPU backend only.",'',f"Completed {len(cases)} / {len(plan)} cases; {sum(c['passed'] for c in cases)} passed. Fresh processes; eight requested generation steps.",'',table(['Check','Passed','Executed'],[[k,sum(v),len(v)] for k,v in checks.items()]),'',table(['Model','Threads','Jobs','Median s','p95 s','Max OS RSS GiB','Max sampled tree RSS GiB'],rows),'','Latency includes model loading, hashing, prompt processing, sampling and receipt creation. Prompts differ in length; p95 combines that workload variation with timing variation. RSS columns are peaks across jobs, not per-model steady-state requirements.','']
    per_prompt=[]
    for name in names:
        for prompt in sorted({c['case']['prompt'] for c in cases}):
            selected=[c for c in cases if c['case']['model']==name and c['case']['prompt']==prompt and c['case']['temperature']==0]
            per_prompt.append([name,prompt,min(c.get('prompt_tokens',0) for c in selected),*[fmt(statistics.median(c['metrics']['generation']['seconds'] for c in selected if c['case']['threads']==t)) for t in [2,8]]])
    pairs=[]
    for name in names:
        for prompt in sorted({c['case']['prompt'] for c in cases}):
            selected={c['case']['threads']:c.get('token_ids') for c in cases if c['case']['model']==name and c['case']['prompt']==prompt and c['case']['temperature']==0 and c['case']['repeat']==0}
            if len(selected)==2:pairs.append(selected[2]==selected[8])
    lines += [f'Greedy cross-thread token agreement: {sum(pairs)} / {len(pairs)} prompt/model pairs. This is an observation, not a cross-backend guarantee.','', '## Per-prompt latency','',table(['Model','Prompt','Input tokens','2 threads median s','8 threads median s'],per_prompt),'','## Measurement limits','',*['- '+s for s in env['limits']],'']
    failures=[c for c in cases if not c['passed']]
    if failures:lines+=['## Failures','',*['- '+str(c['case'])+': '+str(c.get('error',c['checks'])) for c in failures],'']
    (a.out/'native.md').write_text('\n'.join(lines))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    labels=[];times=[];memory=[]
    for name in names:
        for t in [2,8]:
            selected=[c['metrics']['generation'] for c in cases if c['case']['model']==name and c['case']['threads']==t]
            labels.append(name+' / '+str(t));times.append([m['seconds'] for m in selected]);memory.append([m['os_peak_process_rss_bytes']/2**30 for m in selected])
    for ax,data,title,xlabel in [(axes[0],times,'Fresh receipt generation','Seconds, including model loading'),(axes[1],memory,'OS peak process memory','GiB RSS')]:
        ax.boxplot(data,orientation='horizontal',tick_labels=labels,patch_artist=True,boxprops={'facecolor':'#d8b2a2'},medianprops={'color':'#48394f'});ax.set_title(title);ax.set_xlabel(xlabel);ax.grid(axis='x',alpha=.2)
    fig.savefig(a.out/'native.png',dpi=180);plt.close(fig)
    # Raw measurements are public, compressed without timestamps for stable archival.
    (a.out/'native-results.jsonl.gz').write_bytes(gzip.compress((a.native/'results.jsonl').read_bytes(),mtime=0))
    for name in ['environment.json','plan.json','summary.json']:(a.out/('native-'+name)).write_bytes((a.native/name).read_bytes())
if __name__=='__main__':main()
