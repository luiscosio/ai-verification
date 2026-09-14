"""No third-party executable fetches; changed vendor bytes must fail the build."""
import importlib.util,re,shutil,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_site',ROOT/'site/build_site.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class SupplyChecks(unittest.TestCase):
    def test_pinned_vendor_bytes_and_tampering(self):
        self.assertEqual(set(builder.vendor_sources()),{'snarkjs.min.js','three.min.js','snarkjs.LICENSE','three.LICENSE'})
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d);shutil.copytree(ROOT/'site/vendor',dest/'site/vendor')
            original=builder.ROOT
            try:
                builder.ROOT=dest
                file=dest/'site/vendor/snarkjs.min.js';file.write_bytes(file.read_bytes()+b' ')
                with self.assertRaisesRegex(ValueError,'pinned digest'):builder.vendor_sources()
            finally:builder.ROOT=original

    def test_no_external_script_or_import(self):
        template=(ROOT/'site/template.html').read_text()
        self.assertNotRegex(template,r'<script[^>]+src=')
        self.assertIn('__SNARKJS__',template);self.assertIn('__THREE__',template)
        self.assertNotRegex((ROOT/'site/figure.js').read_text(),r'\bimport\s*\(')

    def test_actions_use_full_commits(self):
        actions=[a for workflow in (ROOT/'.github/workflows').glob('*.yml') for a in re.findall(r'uses:\s*(\S+)',workflow.read_text())]
        self.assertGreaterEqual(len(actions),5)
        for action in actions:
            if action.startswith('./.github/workflows/'):
                self.assertTrue((ROOT/action).is_file())
            else:self.assertRegex(action,r'^[\w-]+/[\w-]+@[0-9a-f]{40}$')

if __name__=='__main__':unittest.main()
