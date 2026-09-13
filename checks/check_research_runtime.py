"""A research timeout must stop its prover, not just the OS timing wrapper."""
import importlib.util,subprocess,sys,tempfile,time,unittest
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('operation',ROOT/'research/complete-operation/run.py')
operation=importlib.util.module_from_spec(spec);spec.loader.exec_module(operation)

class Runtime(unittest.TestCase):
    def test_timeout_stops_command_and_descendants(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'pid'
            script="import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); pathlib.Path("+repr(str(file))+").write_text(str(p.pid)); time.sleep(60)"
            with self.assertRaises(subprocess.TimeoutExpired):operation.measured([sys.executable,'-c',script],timeout=.4)
            pid=int(file.read_text())
            for _ in range(20):
                try:
                    if psutil.Process(pid).status()==psutil.STATUS_ZOMBIE:break
                except psutil.NoSuchProcess:break
                time.sleep(.05)
            else:self.fail('Research prover descendant survived timeout')

    def test_success_and_failure_are_reported(self):
        metric,stdout=operation.measured([sys.executable,'-c',"print('done')"])
        self.assertEqual(stdout.strip(),'done');self.assertGreater(metric['peak_process_rss_bytes'],0)
        with self.assertRaisesRegex(RuntimeError,'Command failed'):operation.measured([sys.executable,'-c','raise SystemExit(7)'])

if __name__=='__main__':unittest.main()
