#!/usr/bin/env python3
"""Archive public measurements and generate tables from completed runs only."""
import argparse,gzip,json,shutil,statistics
from pathlib import Path
from summarize import table,fmt

def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def compressed(source,target):target.write_bytes(gzip.compress(source.read_bytes(),mtime=0))
def copy(source,target):target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--rows',type=Path,required=True);p.add_argument('--throughput',type=Path,required=True);p.add_argument('--negatives',type=Path,required=True);p.add_argument('--operations',type=Path,required=True);p.add_argument('--tree',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    matrix=rows(a.rows/'results.jsonl');assert len(matrix)==6 and all(r['passed'] for r in matrix)
    for name in ['environment.json','plan.json','summary.json']:copy(a.rows/name,a.out/'rows'/name)
    compressed(a.rows/'results.jsonl',a.out/'rows/results.jsonl.gz')
    for proof in (a.rows/'proofs').glob('*.llamaproof'):copy(proof,a.out/'rows/proofs'/proof.name)
    rates=[];throughput=[]
    for file in sorted(a.throughput.glob('*-t*.json')):
        value=read(file);throughput.append(value)
        for result in value['results']:
            rates.append([value['model'],value['threads'],result['n_prompt'],result['n_gen'],fmt(result['avg_ts']),fmt(result['stddev_ts']),len(result['samples_ns'])])
    assert len(rates)==40 and sum(r[-1] for r in rates)==120
    copy(a.throughput/'environment.json',a.out/'throughput-environment.json')
    (a.out/'throughput.json.gz').write_bytes(gzip.compress(json.dumps(throughput).encode(),mtime=0))
    negative=read(a.negatives/'results.json');assert len(negative)==28 and all(r['passed'] for r in negative)
    compressed(a.negatives/'results.json',a.out/'native-negative-controls.json.gz');copy(a.negatives/'environment.json',a.out/'native-negative-environment.json')
    operation=[]
    for token in [0,198,512]:
        folder=a.operations/f'token-{token}';report=read(folder/'report.json');assert report['verification']['accept'] and report['verification']['proofs']==65
        metrics=read(folder/'resources.json');dest=a.out/'operations'/folder.name;dest.mkdir(parents=True,exist_ok=True)
        for name in ['report.json','operation.proof.json','negative-controls.json']:copy(folder/name,dest/name)
        for file in (folder/'registry').glob('*.json'):copy(file,dest/'registry'/file.name)
        compressed(folder/'resources.json',dest/'resources.json.gz')
        witness=sum(x['witness']['seconds'] for x in report['measurements']);proving=sum(x['proving']['seconds'] for x in report['measurements'])
        operation.append([token,fmt(metrics['seconds']),fmt((metrics['user_cpu_seconds'] or 0)+(metrics['system_cpu_seconds'] or 0)),fmt(witness),fmt(proving),report['verification']['verify_ms'],fmt(metrics['os_peak_process_rss_bytes']/2**30),fmt(metrics['sampled_peak_tree_rss_bytes']/2**30),report['verification']['bytes']])
    copy(a.operations/'environment.json',a.out/'operation-environment.json');compressed(a.tree,a.out/'process-tree.jsonl.gz')
    observed=rows(a.tree);memory=[]
    for phase in sorted({r['phase'] for r in observed}):
        subset=[r for r in observed if r['phase']==phase]
        memory.append([phase,len(subset),fmt(max(r['rss_bytes'] for r in subset)/2**30),fmt(min(r['system_available_bytes'] for r in subset)/2**30),fmt(min(r['system_swap_bytes'] for r in subset)/2**30)+'–'+fmt(max(r['system_swap_bytes'] for r in subset)/2**30)])
    cost=[]
    for record in matrix:
        groups=record['proof_summary']['groups'];cost.append([record['case']['model'],record['case']['prompt'],record['case']['k'],len(groups),fmt(record['metrics']['generation_without_trace']['seconds']),fmt(record['metrics']['generation']['seconds']),fmt(record['capture_overhead_seconds']),fmt(record['trace_bytes']/2**20),fmt(statistics.median(g['prove_seconds'] for g in groups)),fmt(statistics.median(g['verify_seconds']*1000 for g in groups))])
    cpu_rows=[]
    for value in throughput:
        m=value['metrics'];cpu=(m['user_cpu_seconds'] or 0)+(m['system_cpu_seconds'] or 0)
        cpu_rows.append([value['model'],value['threads'],fmt(m['seconds']),fmt(cpu),fmt(cpu/m['seconds']),fmt(m['os_peak_process_rss_bytes']/2**30)])
    lines=['# Extended measurements','', '## Inference throughput','', 'CPU-only llama-bench, three timed repeats per configuration after warmup. Loading, tokenization, sampling and receipt creation are excluded. A zero in either token column means that phase was not part of the timed test.','',table(['Model','Threads','Prompt tokens','Decode tokens','Mean tokens/s','Sample SD','Repeats'],rates),'','Each resource profile encloses five throughput configurations and their repeats, including loading and warmup. CPU seconds are user plus system CPU time; CPU seconds divided by elapsed time estimates average occupied CPU cores, not peak utilization.','',table(['Model','Threads','Profile elapsed s','OS CPU seconds','Average CPU cores','OS peak process GiB'],cpu_rows),'','## Evidence capture and registered row proofs','', 'Each pair uses the same two-step request. Tracing always ran second; the filesystem cache was uncontrolled. The difference is observed total overhead, including the second trace pass and serialization. Every paired token sequence matched. All 18 exported proof files passed the independent file verifier; all 18 changed-group packages were rejected. The prover also rejected 18 changed-sum pairing checks. Its own different-commitment comparisons are not counted as additional cryptographic verifications.','',table(['Model','Prompt','K','Proofs','No trace s','With trace s','Difference s','Trace MiB','Median prove s/group','Median cold policy verify ms'],cost),'','The individual subprocess RSS profiles exclude the benchmark parent. The separate process-tree observations below include that parent and its trace parsing. Trace files and witnesses were removed; exported packages contain public activations from the synthetic corpus, public arithmetic sums and proofs, not weights.','', '## Experimental complete F20 operations','', 'Each package proves all 1,024 rows of one matrix multiplication using 65 component proofs. Three input embeddings were used; their preparation is outside the proof. This is a separate experimental claim, not complete inference or the website row-group claim. Each package passed the verifier and 12 rejection controls.','',table(['Token ID','Full driver s','OS CPU seconds','Witness sum s','Proving sum s','In-process verification ms','OS peak process GiB','Sampled command tree GiB','Package bytes'],operation),'','Full driver time also includes model loading, registration/commitment work, process startup and final verification. The component time sums exclude these costs.','', '## Complete runner process tree','', '100 ms sampling includes the sequential orchestrator and its descendants, including trace parsing between measured subprocesses. Observation began partway through the Unicode regression; subsequent suites were observed from their start. RSS can double-count shared pages and miss brief peaks. Live CPU samples are not cumulative accounting. System swap/available memory include other applications; this is not evidence that the benchmark itself swapped.','',table(['Suite','Samples','Peak summed RSS GiB','Minimum system available GiB','System swap GiB'],memory),'','## Native negative controls','', 'All 28 controls passed: four honest content checks and 24 rejections covering changed text, prompt, version, token IDs, per-token records and a different model file. Cross-model checks use replay/model-hash validation; the vocabulary-only helper intentionally does not authenticate the model file.','']
    (a.out/'extended.md').write_text('\n'.join(lines))
if __name__=='__main__':main()
