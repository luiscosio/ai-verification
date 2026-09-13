"""Real local API lifecycle through native inference, proving, download and verification.
Requires the authenticated model, binary and r16_k1024 proving materials.
"""
import asyncio,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from check_workspace import local,request

class LiveWorkspace(unittest.IsolatedAsyncioTestCase):
    async def test_real_generate_download_verify(self):
        app=local.create_app();headers={'host':'127.0.0.1:8789','x-prover-token':app.state.token}
        self.assertEqual(local.prerequisites(),[])
        body=json.dumps({'model':local.manifest()['manifest_id'],'prompt':'A short sentence about the moon.'}).encode()
        status,job=await request(app,'/api/local/jobs','POST',body,headers);self.assertEqual(status,200)
        try:
            await asyncio.wait_for(app.state.prover.task,600)
            self.assertEqual(app.state.prover.job['status'],'complete',app.state.prover.job)
            status,package=await request(app,f'/api/local/jobs/{job["id"]}/proof',headers=headers)
            self.assertEqual(status,200);self.assertEqual(package['format'],'llama-receipts/proof-package/v1')
            with tempfile.TemporaryDirectory() as d:
                file=Path(d)/'proof.llamaproof';file.write_text(json.dumps(package))
                result=subprocess.run(['node',str(local.ROOT/'site/verify-file.cjs'),str(file)],capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertTrue(json.loads(result.stdout)['accept'])
            self.assertNotIn('prompt',package);self.assertNotIn('witness',package)
        finally:await app.state.prover.cancel()

if __name__=='__main__':unittest.main()
