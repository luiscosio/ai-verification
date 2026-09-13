"""Exercise resource observation and process cleanup using real child processes."""
import os,sys,tempfile,time,unittest
from pathlib import Path
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from measure import measure

class Measurements(unittest.TestCase):
    def test_memory_and_exit_status(self):
        with tempfile.TemporaryDirectory() as d:
            m,out,err=measure([sys.executable,'-c',"import time; x=bytearray(32*1024*1024); print('observed'); time.sleep(.2); raise SystemExit(7)"],d)
        self.assertEqual(m['returncode'],7);self.assertFalse(m['timed_out'])
        self.assertIn('observed',out);self.assertGreater(m['sampled_peak_tree_rss_bytes'],32*1024*1024)
        self.assertGreater(m['os_peak_process_rss_bytes'],32*1024*1024)
        self.assertIsNotNone(m['user_cpu_seconds'])

    def test_timeout_cleans_children(self):
        with tempfile.TemporaryDirectory() as d:
            child=Path(d)/'child'
            script="import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); pathlib.Path('child').write_text(str(p.pid)); time.sleep(60)"
            m,_,_=measure([sys.executable,'-c',script],d,timeout=.4)
            self.assertTrue(m['timed_out']);self.assertLess(m['seconds'],3)
            pid=int(child.read_text())
            for _ in range(20):
                if not psutil.pid_exists(pid) or psutil.Process(pid).status()==psutil.STATUS_ZOMBIE:break
                time.sleep(.05)
            else:self.fail('Timed-out descendant is still running')

if __name__=='__main__':unittest.main()
