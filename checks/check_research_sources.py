"""Archived research proofs must not silently exercise an older circuit source."""
import hashlib,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class SourcePins(unittest.TestCase):
    def test_sources_match_the_published_operation_registration(self):
        registration=json.loads((ROOT/'research/complete-operation/results/2026-09-13/registry/registration.json').read_text())
        for field,path in [('circuit_sha256','research/complete-operation/full_matvec.circom'),('integer_core_sha256','code/llama.cpp/examples/receipts/zk/groth16/qdot_rows.circom'),('verifier_sha256','research/complete-operation/verify.cjs')]:
            with self.subTest(path=path):self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),registration[field],'Update the research registration and proof fixtures for changed semantics')
if __name__=='__main__':unittest.main()
