"""Exercise resource observation and process cleanup using real child processes."""
import os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from measure import measure,clean_revision

class Measurements(unittest.TestCase):
    def test_benchmark_requires_clean_root_and_submodules(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'root';child=Path(folder)/'child';root.mkdir();child.mkdir()
            def git(where,*args):return subprocess.check_output(['git','-c','user.name=Test','-c','user.email=test@example.invalid',*args],cwd=where,stderr=subprocess.PIPE,text=True).strip()
            for repo in [root,child]:
                git(repo,'init');(repo/'tracked').write_text('original');git(repo,'add','tracked');git(repo,'commit','-m','fixture')
            git(root,'-c','protocol.file.allow=always','submodule','add',str(child),'sub');git(root,'commit','-am','submodule fixture')
            revision=clean_revision(root);self.assertFalse(revision['dirty']);self.assertEqual(revision['commit'],git(root,'rev-parse','HEAD'));self.assertEqual(revision['tree'],git(root,'rev-parse','HEAD^{tree}'))
            (root/'tracked').write_text('changed')
            with self.assertRaisesRegex(RuntimeError,'tracked'):clean_revision(root)
            git(root,'add','tracked')
            with self.assertRaisesRegex(RuntimeError,'tracked'):clean_revision(root)
            git(root,'restore','--staged','--worktree','tracked')
            (root/'untracked').write_text('new')
            with self.assertRaisesRegex(RuntimeError,'untracked'):clean_revision(root)
            (root/'untracked').unlink();(root/'sub'/'untracked').write_text('new')
            with self.assertRaisesRegex(RuntimeError,'sub'):clean_revision(root)
            (root/'sub'/'untracked').unlink();(root/'sub'/'tracked').write_text('changed')
            with self.assertRaisesRegex(RuntimeError,'sub'):clean_revision(root)
            git(root/'sub','commit','-am','changed child revision')
            with self.assertRaisesRegex(RuntimeError,'sub'):clean_revision(root)

    def test_memory_and_exit_status(self):
        with tempfile.TemporaryDirectory() as d:
            m,out,err=measure([sys.executable,'-c',"import time; x=bytearray(32*1024*1024); print('observed'); time.sleep(.2); raise SystemExit(7)"],d)
        self.assertEqual(m['returncode'],7);self.assertFalse(m['timed_out'])
        self.assertIn('observed',out);self.assertGreater(m['sampled_peak_tree_rss_bytes'],32*1024*1024)
        self.assertGreater(m['os_peak_process_rss_bytes'],32*1024*1024)
        self.assertIsNotNone(m['user_cpu_seconds'])

    def test_fast_commands_do_not_race_process_inspection(self):
        with tempfile.TemporaryDirectory() as d:
            for _ in range(20):
                metrics,_,_=measure(['/usr/bin/true'],d)
                self.assertEqual(metrics['returncode'],0)
                self.assertFalse(metrics['timed_out'])

    def test_timeout_cleans_children(self):
        with tempfile.TemporaryDirectory() as d:
            child=Path(d)/'child'
            script="import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); pathlib.Path('child').write_text(str(p.pid)); time.sleep(60)"
            m,_,_=measure([sys.executable,'-c',script],d,timeout=.4)
            self.assertTrue(m['timed_out']);self.assertLess(m['seconds'],3)
            pid=int(child.read_text())
            for _ in range(20):
                try:
                    if psutil.Process(pid).status()==psutil.STATUS_ZOMBIE:break
                except psutil.NoSuchProcess:break
                time.sleep(.05)
            else:self.fail('Timed-out descendant is still running')

if __name__=='__main__':unittest.main()
