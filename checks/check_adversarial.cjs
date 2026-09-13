// Seeded valid-proof mutations exercise policy and pairing rejection together.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const ROOT=path.resolve(__dirname,'..'),G16=ROOT+'/code/llama.cpp/examples/receipts/zk/groth16';
const policy=require(G16+'/verify.js'),packages=require(ROOT+'/site/proof-package.js'),snarkjs=require(G16+'/node_modules/snarkjs');
const read=file=>JSON.parse(fs.readFileSync(file));
async function main(){
 const manifests=fs.readdirSync(ROOT+'/registry').map(n=>ROOT+'/registry/'+n+'/manifest.json').filter(fs.existsSync).map(read);
 const manifest=manifests.find(m=>m.model.name==='Qwen3-0.6B');
 const honest={format:'llama-receipts/proof-package/v1',claim:'q4k-integer-row-group/v1',registration_id:manifest.manifest_id,tensor:'blk.0.attn_k.weight',group:0,proof:read(__dirname+'/fixtures/groth16/honest-proof.json'),public:read(__dirname+'/fixtures/groth16/honest-public.json')};
 const data={manifests,vkeys:Object.fromEntries(fs.readdirSync(ROOT+'/registry/circuits').filter(n=>/^r\d+_k\d+$/.test(n)).map(n=>[n,read(ROOT+'/registry/circuits/'+n+'/verification_key.json')]))};
 let state=20260913;const random=()=>{state=(Math.imul(state,1664525)+1013904223)>>>0;return state;};
 const check=p=>packages.verify(p,data,policy,snarkjs);
 const metrics=[];const cpu=process.cpuUsage();const start=performance.now();
 const iterations=Number(process.argv[2]||300);assert.ok(Number.isSafeInteger(iterations)&&iterations>=1&&iterations<=10000);
 for(let i=0;i<iterations;i++){
  const p=structuredClone(honest);const category=i%6;
  if(category===0){const j=1+random()%(p.public.length-1);p.public[j]=String((BigInt(p.public[j])+1n)%21888242871839275222246405745257275088548364400416034343698204186575808495617n);}
  if(category===1)p.public[1+random()%1024]=['128','-1','01','1e2',' '+p.public[1],'9'.repeat(100)][random()%6];
  if(category===2)p.group=1+random()%63;
  if(category===3)p.proof.pi_a[random()%2]=String(BigInt(p.proof.pi_a[0])+1n);
  if(category===4)p.registration_id=manifests.filter(m=>m!==manifest)[random()%2].manifest_id;
  if(category===5)p.public.splice(random()%p.public.length,1);
  assert.equal((await check(p)).accept,false,'mutation '+i+' category '+category);
  if(i%25===0){const t=performance.now();assert.equal((await check(honest)).accept,true);metrics.push({after_mutations:i,verify_ms:performance.now()-t,...process.memoryUsage()});}
 }
 for(const malformed of [null,true,0,'text',[],{},Object.assign(structuredClone(honest),{witness:[1,2,3]})])assert.notEqual((await check(malformed)).accept,true);
 console.log(JSON.stringify({seed:20260913,mutations_rejected:iterations,malformed_rejected:7,honest_recovery_checks:metrics.length,seconds:(performance.now()-start)/1000,cpu:process.cpuUsage(cpu),memory_samples:metrics}));
}
main().then(()=>process.exit(0)).catch(e=>{console.error(e);process.exit(1);});
