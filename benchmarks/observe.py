#!/usr/bin/env python3
"""Observe an already-owned sequential runner, including its Python orchestration memory."""
import argparse,json,time
from pathlib import Path
import psutil

KNOWN={'benchmarks/run_matrix.py','benchmarks/run_extended.py','checks/check_live_workspace.py','research/complete-operation/check_witnesses.py'}
def phase(processes):
    for process in processes:
        try:args=process.cmdline()
        except psutil.Error:continue
        for name in KNOWN:
            if name in args:
                if '--suite' in args:return args[args.index('--suite')+1]
                if '--case-plan' in args:return 'unicode-regression'
                return Path(name).stem
    return 'between-suites'

def main():
    p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    parent=psutil.Process(a.pid);start=time.perf_counter()
    with a.out.open('x') as out:
        while parent.is_running():
            try:processes=[parent,*parent.children(recursive=True)]
            except psutil.NoSuchProcess:break
            label=phase(processes);rss=0;cpu=0;count=0
            for process in processes:
                try:
                    rss+=process.memory_info().rss;used=process.cpu_times();cpu+=used.user+used.system;count+=1
                except psutil.Error:pass
            out.write(json.dumps({'seconds':round(time.perf_counter()-start,3),'phase':label,'rss_bytes':rss,'live_cpu_seconds':round(cpu,3),'processes':count,'system_available_bytes':psutil.virtual_memory().available,'system_swap_bytes':psutil.swap_memory().used})+'\n');out.flush()
            time.sleep(.1)
if __name__=='__main__':main()
