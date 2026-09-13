"""Exercise API rejection, concurrency, timeout and cancellation without expensive proofs."""
import asyncio
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

from fastapi import UploadFile, HTTPException

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("serve", ROOT / "site/serve.py")
server = importlib.util.module_from_spec(spec); spec.loader.exec_module(server)


class APIChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.binary, self.timeout = server.BIN, server.TIMEOUT
        server.BIN = Path(self.temp.name) / "verifier"
        server.BIN.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(0.3)\n")
        server.BIN.chmod(0o755)
        server.verification_slot = asyncio.Semaphore(1)
        self.manifest = next(m for m in server.manifests.values() if any(t.get("commitment") for t in m["tensors"]))
        self.entry = next(t for t in self.manifest["tensors"] if t.get("commitment"))
        k, m = self.entry["shape"]
        self.public = dict(k=k, m=m, config="orion", commitment=self.entry["commitment"]["value"], q8=[0]*k, s1=[0]*(m*k//256), s2=[0]*(m*k//256))

    def tearDown(self):
        server.BIN, server.TIMEOUT = self.binary, self.timeout
        self.temp.cleanup()

    async def call(self, value):
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        return await server.verify_expander(self.manifest["manifest_id"], self.entry["name"],
            UploadFile(filename="public.json", file=io.BytesIO(raw)), UploadFile(filename="proof.bin", file=io.BytesIO(b"fixture")))

    async def test_malformed_types_and_ranges(self):
        bad_range = copy.deepcopy(self.public); bad_range["q8"][0] = 128
        for value in ([], None, True, 5, {}, b"{", b"\xff", bad_range):
            with self.subTest(value=str(value)[:30]), self.assertRaises(HTTPException) as error:
                await self.call(value)
            self.assertEqual(error.exception.status_code, 400)

    async def test_event_loop_and_busy(self):
        task = asyncio.create_task(self.call(self.public))
        t0 = time.monotonic(); await asyncio.sleep(0.04)
        self.assertLess(time.monotonic()-t0, 0.2)
        with self.assertRaises(HTTPException) as error: await self.call(self.public)
        self.assertEqual(error.exception.status_code, 503)
        self.assertTrue((await task)["accept"])

    async def test_timeout_and_recovery(self):
        server.TIMEOUT = 0.03
        with self.assertRaises(HTTPException) as error: await self.call(self.public)
        self.assertEqual(error.exception.status_code, 504)
        self.assertFalse(server.verification_slot.locked())
        server.TIMEOUT = 3
        self.assertTrue((await self.call(self.public))["accept"])

    async def test_cancellation_releases_slot(self):
        task = asyncio.create_task(self.call(self.public)); await asyncio.sleep(0.04)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertFalse(server.verification_slot.locked())

    async def test_size_limit(self):
        with self.assertRaises(HTTPException) as error: await self.call(b"x" * (server.MAX_PUBLIC + 1))
        self.assertEqual(error.exception.status_code, 413)


if __name__ == "__main__": unittest.main()
