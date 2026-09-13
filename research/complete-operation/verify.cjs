// Research-only complete-operation verifier. Its registry is supplied by the operator,
// never installed from a proof package. No GGUF or private openings are read here.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const snarkjs=require(path.resolve(__dirname,'../../code/llama.cpp/examples/receipts/zk/groth16/node_modules/snarkjs'));
const FIELD=21888242871839275222246405745257275088548364400416034343698204186575808495617n;
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const canonical=x=>JSON.stringify(x,Object.keys(x).sort());
function exact(value,keys){if(!value||Array.isArray(value)||typeof value!=='object'||Object.keys(value).sort().join('|')!==keys.sort().join('|'))throw Error('Unexpected package fields');}
function signals(values,n){if(!Array.isArray(values)||values.length!==n||values.some(v=>typeof v!=='string'||! /^(0|[1-9][0-9]{0,76})$/.test(v)||BigInt(v)>=FIELD))throw Error('Noncanonical public signals');}
function read(file,max){if(fs.statSync(file).size>max)throw Error('File exceeds size limit');return fs.readFileSync(file);}
async function verify(packageFile,registryDir){
 const raw=read(path.join(registryDir,'registration.json'),1024*1024);
 const registry=JSON.parse(raw);const id=sha(raw);
 if(registry.claim!=='experimental/f20-q4k-matvec/v1'||registry.rows_per_group!==16||registry.k!==1024||registry.m!==1024||registry.weight_commitments.length!==64)throw Error('Unsupported operator registration');
 const value=JSON.parse(read(packageFile,2*1024*1024));
 exact(value,['format','registration_id','context','input_commitment','quant','groups']);
 if(value.format!==registry.claim||value.registration_id!==id)throw Error('Registration identity mismatch');
 signals([value.context,value.input_commitment],2);
 exact(value.quant,['proof','public']);signals(value.quant.public,3);
 if(value.quant.public[0]!==value.input_commitment||value.quant.public[2]!==value.context)throw Error('Quantization context/input mismatch');
 if(!Array.isArray(value.groups)||value.groups.length!==64)throw Error('Incomplete operation: expected all 64 row groups');
 const keys={};for(const name of ['quant_k1024','rows16_k1024']){
  const bytes=read(path.join(registryDir,name+'.json'),1024*1024);
  if(sha(bytes)!==registry.keys[name])throw Error('Verification key pin mismatch');keys[name]=JSON.parse(bytes);
 }
 if(sha(fs.readFileSync(__filename))!==registry.verifier_sha256)throw Error('Verifier source pin mismatch');
 for(let g=0;g<64;g++){
  const item=value.groups[g];exact(item,['proof','public']);signals(item.public,5);
  if(item.public[0]!==registry.weight_commitments[g])throw Error('Weight commitment mismatch');
  if(item.public[1]!==value.quant.public[1])throw Error('Disconnected private activation');
  if(item.public[3]!==value.context||item.public[4]!==String(g))throw Error('Wrong context or row order');
 }
 const start=performance.now();
 if(!await snarkjs.groth16.verify(keys.quant_k1024,value.quant.public,value.quant.proof))throw Error('Quantization proof rejected');
 for(let g=0;g<64;g++)if(!await snarkjs.groth16.verify(keys.rows16_k1024,value.groups[g].public,value.groups[g].proof))throw Error('Row proof rejected at '+g);
 return {accept:true,claim:registry.claim,rows:1024,columns:1024,proofs:65,verify_ms:Math.round(performance.now()-start),bytes:fs.statSync(packageFile).size,
  scope:'Complete F20 Q4_K matrix-vector operation between private boundary commitments. No native float or token claim.'};
}
module.exports={verify};
if(require.main===module)verify(process.argv[2],process.argv[3]).then(r=>{console.log(JSON.stringify(r));process.exit(0);}).catch(error=>{console.log(JSON.stringify({accept:false,error:error.message}));process.exit(1);});
