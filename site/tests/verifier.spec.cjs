const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../..');
const read=p=>JSON.parse(fs.readFileSync(root+'/'+p));
const manifest=read('registry/qwen3-0.6b-q4_k_m/manifest.json');
function proof(){return {format:'llama-receipts/proof-package/v1',claim:'q4k-integer-row-group/v1',registration_id:manifest.manifest_id,tensor:'blk.0.attn_k.weight',group:0,proof:read('checks/fixtures/groth16/honest-proof.json'),public:read('checks/fixtures/groth16/honest-public.json')};}
async function upload(page,value,name='proof.llamaproof'){
 await page.locator('#package-file').setInputFiles({name,mimeType:'application/json',buffer:Buffer.from(typeof value==='string'?value:JSON.stringify(value))});
 await page.locator('#run').click();
}
test.beforeEach(async({page})=>{await page.route('**/*',route=>new URL(route.request().url()).origin==='http://127.0.0.1:8790'?route.continue():route.abort());await page.goto('/');});

test('honest and invalid examples verify offline, then recover',async({page})=>{
 await page.getByRole('button',{name:'Try a valid proof',exact:true}).click();
 await expect(page.locator('#result-view')).toHaveAttribute('data-state','verified');
 await expect(page.locator('#result-view')).toContainText('complete inference are not verified');
 await page.getByRole('button',{name:'Try an invalid proof',exact:true}).click();
 await expect(page.locator('#result-view')).toHaveAttribute('data-state','invalid');
 await page.getByRole('button',{name:'Try a valid proof',exact:true}).click();
 await expect(page.locator('#result-view')).toHaveAttribute('data-state','verified');
});

test('uploaded honest proof and altered public value',async({page})=>{
 await upload(page,proof());await expect(page.locator('#result-view')).toHaveAttribute('data-state','verified');
 const bad=proof();bad.public[1]='128';await upload(page,bad);await expect(page.locator('#result-view')).toHaveAttribute('data-state','invalid');
});

test('malformed, oversized and unknown registrations fail clearly',async({page})=>{
 await upload(page,'{broken');await expect(page.locator('#result-view')).toContainText('could not be read');
 await upload(page,'x'.repeat(2*1024*1024+1));await expect(page.locator('#result-view')).toContainText('up to 2 MiB');
 const unknown=proof();unknown.registration_id='0'.repeat(64);await upload(page,unknown);await expect(page.locator('#result-view')).toHaveAttribute('data-state','unknown-model');
});

test('file names stay text and cannot create markup',async({page})=>{
 await upload(page,proof(),'<img src=x onerror=alert(1)>.llamaproof');
 await expect(page.locator('#result-view')).toHaveAttribute('data-state','verified');
 await expect(page.locator('#result-view img')).toHaveCount(0);
 await expect(page.locator('#file-label')).toContainText('<img');
});

test('catalogue search and local generation availability',async({page})=>{
 await page.locator('#model-search').fill('1.5B');
 await expect(page.locator('#models-view')).toContainText('Qwen2.5');
 await expect(page.locator('#models-view')).toContainText('Local generation unavailable');
 await expect(page.locator('#models-view')).not.toContainText('Qwen3-0.6B');
 await page.locator('#model-search').fill('no-model-matches-this');await expect(page.locator('#models-view')).toContainText('No registered models');
 await page.locator('#show-generate').click();await expect(page.locator('#local-unavailable')).toBeVisible();await expect(page.locator('#generate-form')).toBeHidden();
});

test('keyboard navigation and narrow layout',async({page})=>{
 await page.setViewportSize({width:375,height:812});
 await page.locator('#show-generate').focus();await page.keyboard.press('Enter');
 await expect(page.locator('#generate')).toBeVisible();
 await page.locator('#show-verify').focus();await page.keyboard.press('Enter');
 await expect(page.locator('#verify')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test('reduced motion and unavailable WebGL preserve verification',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){if(String(type).includes('webgl'))return null;return original.call(this,type,...args);};});
 await page.reload();await expect(page.locator('.jelly-fallback')).toBeVisible();
 await page.getByRole('button',{name:'Try a valid proof',exact:true}).click();await expect(page.locator('#result-view')).toHaveAttribute('data-state','verified');
});

test('downloaded example is a portable proof package',async({page})=>{
 const pending=page.waitForEvent('download');await page.locator('#download-example').click();const download=await pending;
 const value=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
 expect(Object.keys(value).sort()).toEqual(Object.keys(proof()).sort());expect(value.registration_id).toEqual(manifest.manifest_id);
});

test('repeated verification records latency and preserves the user pause',async({page},testInfo)=>{
 const toggle=page.locator('#motion-toggle');
 if(await toggle.isVisible())await toggle.click();
 const samples=[];
 for(let i=0;i<10;i++){
  const start=Date.now();
  await page.getByRole('button',{name:'Try a valid proof',exact:true}).click();
  await expect(page.locator('#result-view')).toHaveAttribute('data-state','verified');
  const interaction_ms=Date.now()-start;
  const displayed=await page.locator('#result-view .facts > div').filter({hasText:'Verification time'}).locator('dd').innerText();
  samples.push({interaction_ms,verifier_ms:parseInt(displayed,10)});
 }
 if(await toggle.isVisible())await expect(toggle).toHaveText('Play motion');
 await testInfo.attach('verification-latency-ms',{body:JSON.stringify({project:testInfo.project.name,samples,cold_first_sample:true,measurement:'interaction_ms includes scrolling and test assertions; verifier_ms is the page-reported policy and pairing time'}),contentType:'application/json'});
});

test('registered model and circuit shapes render their actual checked rows',async({page})=>{
 const directory=root+'/checks/fixtures/registered-proofs';
 const names=fs.readdirSync(directory).filter(n=>n.endsWith('.llamaproof')).sort();expect(names).toHaveLength(4);const widths=new Set();
 for(const name of names){
  const value=JSON.parse(fs.readFileSync(directory+'/'+name));
  const registration=read('registry/'+(name.startsWith('qwen2.5')?'qwen2.5-1.5b-q4_k_m':'qwen3-0.6b-q4_k_m')+'/manifest.json');
  const tensor=registration.tensors.find(t=>t.name===value.tensor),first=value.group*tensor.groth16.rows_per_group;
  widths.add(tensor.shape[0]);
  await upload(page,value,name);await expect(page.locator('#result-view')).toHaveAttribute('data-state','verified');
  await expect(page.locator('#result-view')).toContainText(registration.model.name);
  await expect(page.locator('#result-view')).toContainText(`Rows ${first}–${first+tensor.groth16.rows_per_group-1}`);
 }
 expect([...widths].sort((a,b)=>a-b)).toEqual([1024,1536,2048,3072]);
});
