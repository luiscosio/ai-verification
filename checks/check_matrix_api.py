"""Public request boundaries across malformed values, Unicode and chunked bodies."""
import asyncio,json,unittest
from unittest.mock import patch
from check_workspace import local,request

class MatrixAPI(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_and_shape_matrix(self):
        app=local.create_app();headers={'host':'127.0.0.1:8789','x-prover-token':app.state.token}
        mid=local.manifest()['manifest_id']
        invalid=[None,False,0,[],{},'', '   ', 'x'*513, 'a\x00b','\ud800']
        for prompt in invalid:
            status,_=await request(app,'/api/local/jobs','POST',json.dumps({'model':mid,'prompt':prompt}).encode(),headers)
            self.assertEqual(status,400,repr(prompt)[:40])
        for body in [b'\xff',b'"x"',b'0',b'false',b'null',b'[]',b'{}',b'{"model":null,"prompt":"hi"}',b'x'*4097]:
            status,_=await request(app,'/api/local/jobs','POST',body,headers)
            self.assertIn(status,[400,413])
        async def fake(self,prompt,registration):
            self.job.update(status='complete',finished=self.job['started']);self.package={'test':True}
        with patch.object(local,'prerequisites',return_value=[]),patch.object(local.Prover,'run',fake):
            for prompt in ['x','x'*512,'中文日本語','Español café é','🌍🤖','\tcode\n  return x','<script>alert(1)</script>']:
                status,_=await request(app,'/api/local/jobs','POST',json.dumps({'model':mid,'prompt':prompt}).encode(),headers)
                self.assertEqual(status,200,repr(prompt)[:40]);await app.state.prover.task

    async def test_chunked_request_limit(self):
        app=local.create_app();headers={'host':'127.0.0.1:8789','x-prover-token':app.state.token}
        chunks=iter([b'a'*2048,b'b'*2048,b'c']);messages=[]
        async def receive():
            try:return {'type':'http.request','body':next(chunks),'more_body':True}
            except StopIteration:await asyncio.Event().wait()
        async def send(msg):messages.append(msg)
        scope={'type':'http','asgi':{'version':'3.0','spec_version':'2.4'},'http_version':'1.1','method':'POST','scheme':'http','path':'/api/local/jobs','raw_path':b'/api/local/jobs','query_string':b'','headers':[(k.encode(),v.encode()) for k,v in headers.items()],'client':('127.0.0.1',123),'server':('127.0.0.1',8789)}
        await asyncio.wait_for(app(scope,receive,send),5)
        self.assertEqual(next(m['status'] for m in messages if m['type']=='http.response.start'),413)

if __name__=='__main__':unittest.main()
