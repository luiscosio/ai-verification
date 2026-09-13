"""Regression checks for registration, receipt content, quantization and demo failures."""
import argparse
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ZK = ROOT / "code/llama.cpp/examples/receipts/zk"
sys.path.insert(0, str(ZK))
import register
from registration_schema import validate_manifest, canonical


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fp = load("fixed_point", ROOT / "docs/stage4/fixed_point_forward.py")
site = load("build_site", ROOT / "site/build_site.py")
MANIFEST = ROOT / "registry/qwen3-0.6b-q4_k_m/manifest.json"
MODEL = ROOT / "models/qwen3-0.6b-q4_k_m.gguf"
BINARY = ROOT / "code/llama.cpp/build/bin/llama-receipts"


def resign(m):
    m.pop("manifest_id", None)
    m["manifest_id"] = hashlib.sha256(canonical(m)).hexdigest()
    return m


class CoreChecks(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text())

    def check_registration(self, manifest, commit=False, groth16=False, limit=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "manifest.json"
            p.write_text(json.dumps(manifest))
            args = argparse.Namespace(check=str(p), model=str(MODEL), commit=commit, groth16=groth16, limit=limit,
                                      circuits_dir=str(ROOT / "registry/circuits"), binary=str(ZK / "target/release/receipts-zk"))
            with contextlib.redirect_stdout(io.StringIO()):
                return register.check(args)

    def test_baseline_registration(self):
        self.assertEqual(self.check_registration(self.manifest), 0)

    def test_false_metadata(self):
        for key, value in [("hparams", {"block_count": 999}), ("file_bytes", 1), ("name", "Wrong model")]:
            with self.subTest(key=key):
                m = copy.deepcopy(self.manifest); m["model"][key] = value
                self.assertEqual(self.check_registration(resign(m)), 1)

    def test_bad_mapping_and_bytes(self):
        for change in ("duplicate", "order", "bytes"):
            with self.subTest(change=change):
                m = copy.deepcopy(self.manifest)
                if change == "duplicate": m["tensors"][0] = copy.deepcopy(m["tensors"][1])
                if change == "order": m["tensors"][0], m["tensors"][1] = m["tensors"][1], m["tensors"][0]
                if change == "bytes": m["tensors"][0]["n_bytes"] += 1
                self.assertEqual(self.check_registration(resign(m)), 1)

    def test_execution_and_shapes_fail_closed(self):
        for change in ("version", "execution", "groups", "circuit", "key"):
            m = copy.deepcopy(self.manifest); t = next(t for t in m["tensors"] if t.get("groth16"))
            if change == "version": m["manifest_version"] = "registration/v999"
            if change == "execution": m["execution"]["threads"] = 1
            if change == "groups": t["groth16"]["groups"].pop()
            if change == "circuit": t["groth16"]["circuit"] = "../wrong"
            if change == "key": m["proof_system"]["groth16"]["verification_keys"] = {}
            with self.subTest(change=change), self.assertRaises(ValueError): validate_manifest(resign(m))

    def test_independent_commitment_limits(self):
        by_name = {t["name"]: t for t in self.manifest["tensors"]}
        def g16(store, name, *args): return by_name[name]["groth16"]["groups"]
        def orion(binary, store, name, *args): return by_name[name]["commitment"]["value"], 0.0
        for include_orion in (False, True):
            with patch.object(register, "groth16_commitments", side_effect=g16) as g, patch.object(register, "commit_tensor", side_effect=orion) as o:
                self.assertEqual(self.check_registration(self.manifest, include_orion, True, 1), 0)
                self.assertEqual(g.call_count, 1); self.assertEqual(o.call_count, int(include_orion))

    def test_registry_only_site_and_missing_key(self):
        with tempfile.TemporaryDirectory() as d:
            args = ["build", "--out", d + "/index.html", "--artifact", d + "/artifact.html"]
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()): site.main()
            html = Path(d + "/index.html").read_text()
            self.assertNotIn("__VERIFIER__", html); self.assertIn('"r16_k1024"', html)
            original = Path.read_text
            def missing(p, *args, **kwargs):
                if p == ROOT / "registry/circuits/r16_k1024/verification_key.json": raise FileNotFoundError(p)
                return original(p, *args, **kwargs)
            with patch.object(sys, "argv", args), patch.object(Path, "read_text", missing), self.assertRaises(FileNotFoundError): site.main()

    def test_signed_max_and_zero_quantization(self):
        m = fp.Model.__new__(fp.Model); m.F = 20
        for block in ([0] * 256, [-1, 1] + [0] * 254, [1, -1] + [0] * 254):
            x = np.asarray(block, dtype=np.float32).reshape(1, 256)
            _, expected, sums = register.vt.quantize_q8_k(x)
            d, actual, got_sums = m.quantize_q8k(np.asarray(block, dtype=object) * (1 << 20))
            np.testing.assert_array_equal(actual, expected.reshape(-1))
            np.testing.assert_array_equal(got_sums, sums[0])
            if block[0]: self.assertEqual(np.sign(d[0]), -np.sign(block[0]))

    def test_content_and_version(self):
        # Use the vocabulary-only checker; no model inference is needed.
        receipt = json.loads((ROOT / "checks/fixtures/receipt.json").read_text())
        for change in (None, "text", "prompt", "version", "id", "record"):
            r = copy.deepcopy(receipt)
            if change == "text": r["response"]["text"] = "Berlin"
            if change == "prompt": r["request"]["prompt_text"] = "unrelated prompt"
            if change == "version": r["receipt_version"] = "999"
            if change == "id": r["response"]["tokens"][0] = 999999
            if change == "record": r["response"]["per_token"][0]["token"] += 1
            p = subprocess.run([str(BINARY), "-m", str(MODEL), "--check-content", "-"], input=json.dumps(r), capture_output=True, text=True)
            with self.subTest(change=change): self.assertEqual(p.returncode == 0, change is None, p.stderr[-400:])

    def test_demo_stops_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); fake = p / "llama"; (fake / "build/bin").mkdir(parents=True)
            (fake / "examples").symlink_to(ROOT / "code/llama.cpp/examples")
            binary = fake / "build/bin/llama-receipts"
            binary.write_text('#!/bin/sh\necho "injected failure" >&2\nexit 37\n'); binary.chmod(0o755)
            env = dict(os.environ, LLAMA=str(fake), LEAN=str(ROOT / "code/llama.cpp"), MODEL=str(MODEL),
                       DEMO_ROOT=str(p / "demo"), PYTHON_RUNNER=sys.executable)
            result = subprocess.run(["bash", str(ROOT / "run-demo.sh")], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
            self.assertNotIn("2. Verify", result.stdout)


if __name__ == "__main__": unittest.main()
