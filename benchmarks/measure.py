"""Sequential process-tree sampling plus OS process high-water measurements."""
import json,os,platform,re,signal,subprocess,tempfile,time
from pathlib import Path
import psutil

def measure(command, cwd, timeout=600):
    started=time.perf_counter();samples=[];timed_out=False
    swap_start=psutil.swap_memory().used
    with tempfile.TemporaryDirectory(prefix='receipts-metrics-') as folder:
        folder=Path(folder);metric=folder/'os-time.txt'
        with (folder/'stdout').open('wb') as out,(folder/'stderr').open('wb') as err:
            proc=subprocess.Popen(['/usr/bin/time','-l' if platform.system()=='Darwin' else '-v','-o',str(metric),*map(str,command)],cwd=cwd,stdout=out,stderr=err,start_new_session=True)
            try:
                try:parent=psutil.Process(proc.pid)
                except psutil.NoSuchProcess:parent=None
                while proc.poll() is None:
                    rss=0;cpu=0.;count=0
                    try:tree=[parent,*parent.children(recursive=True)] if parent else []
                    except psutil.Error:tree=[]
                    for child in tree:
                        try:
                            rss+=child.memory_info().rss;t=child.cpu_times();cpu+=t.user+t.system;count+=1
                        except psutil.Error:pass
                    samples.append({'t':round(time.perf_counter()-started,3),'rss_bytes':rss,'live_cpu_seconds':round(cpu,3),'processes':count,'available_bytes':psutil.virtual_memory().available,'swap_used_bytes':psutil.swap_memory().used})
                    if time.perf_counter()-started>timeout:
                        timed_out=True;break
                    try:proc.wait(timeout=.05)
                    except subprocess.TimeoutExpired:pass
            finally:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait()
        raw=metric.read_text() if metric.exists() else ''
        peak=None;user=system=None
        if platform.system()=='Darwin':
            match=re.search(r'(\d+)\s+maximum resident set size',raw)
            if match:peak=int(match[1])
            match=re.search(r'([\d.]+) user\s+([\d.]+) sys',raw)
            if match:user,system=map(float,match.groups())
        else:
            match=re.search(r'Maximum resident set size \(kbytes\): (\d+)',raw)
            if match:peak=int(match[1])*1024
            for label,key in [('User time','user'),('System time','system')]:
                match=re.search(label+r' \(seconds\): ([\d.]+)',raw)
                if match:
                    if key=='user':user=float(match[1])
                    else:system=float(match[1])
        result={'seconds':round(time.perf_counter()-started,4),'returncode':proc.returncode,'timed_out':timed_out,'os_peak_process_rss_bytes':peak,'user_cpu_seconds':user,'system_cpu_seconds':system,
                'sampled_peak_tree_rss_bytes':max((s['rss_bytes'] for s in samples),default=0),'min_system_available_bytes':min((s['available_bytes'] for s in samples),default=0),'system_swap_start_bytes':swap_start,'system_swap_end_bytes':psutil.swap_memory().used,'samples':samples}
        return result,(folder/'stdout').read_text(errors='replace'),(folder/'stderr').read_text(errors='replace')

def environment(root):
    def command(*args):return subprocess.check_output(args,cwd=root,text=True).strip()
    return {'platform':platform.platform(),'cpu':command('sysctl','-n','machdep.cpu.brand_string') if platform.system()=='Darwin' else platform.processor(),'logical_cpus':psutil.cpu_count(),'physical_memory_bytes':psutil.virtual_memory().total,'python':platform.python_version(),'node':command('node','--version'),'commit':command('git','rev-parse','HEAD'),'dirty':bool(command('git','status','--porcelain')),'sampling_interval_seconds':.05,
            'limits':['Fresh process for each measurement; filesystem cache is uncontrolled','Summed RSS can double-count shared mappings; sampled peaks can miss short spikes','CPU metrics from OS time cover its child command; sampled CPU is live processes only','System available/swap values include other applications; changes are not attributed to this test','CPU backend only; accelerator allocations and energy not measured']}
