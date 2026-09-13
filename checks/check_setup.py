"""Installer integrity and recovery checks without network or native rebuilds."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('setup_workspace',ROOT/'tools/setup_workspace.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


class SetupChecks(unittest.TestCase):
    def test_verified_atomic_install_and_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source';source.write_bytes(b'proof material')
            target=Path(d)/'target';digest=setup.sha(source)
            setup.fetch('',target,digest,len(source.read_bytes()),source)
            self.assertEqual(target.read_bytes(),source.read_bytes())
            # An already verified install does not need its download source.
            setup.fetch('',target,digest,14,Path(d)/'missing')

    def test_corruption_preserves_existing_and_cleans_partial(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source';source.write_bytes(b'bad')
            target=Path(d)/'target';target.write_bytes(b'existing')
            with self.assertRaises(ValueError): setup.fetch('',target,'0'*64,3,source)
            self.assertEqual(target.read_bytes(),b'existing')
            self.assertEqual(list(Path(d).glob('*.partial')),[])
            with self.assertRaises(ValueError): setup.fetch('',target,'0'*64,2,source)
            self.assertEqual(target.read_bytes(),b'existing')

    def test_paths_and_selection(self):
        import json
        release=json.loads((ROOT/'releases/prover-materials-v1.json').read_text())
        selected=list(setup.assets_for(release))
        self.assertEqual({a['path'] for a in selected},{'main_final.zkey','main_js/main.wasm'})
        self.assertEqual(len(list(setup.assets_for(release,True,True))),13)
        for asset in release['assets']: self.assertTrue(setup.destination(ROOT,asset).is_relative_to(ROOT))
        with self.assertRaises(ValueError): setup.destination(ROOT,{'circuit':'../escape','path':'main_final.zkey'})
        with self.assertRaises(ValueError): setup.destination(ROOT,{'circuit':'r16_k1024','path':'../../escape'})


if __name__=='__main__': unittest.main()
