const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const {verify}=require('./verify.cjs');
async function main(){
 const packageFile=process.argv[2],registry=process.argv[3];const honest=JSON.parse(fs.readFileSync(packageFile));
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'operation-negatives-'));
 const cases=[
  ['omitted rows',p=>p.groups.pop()],
  ['reordered rows',p=>[p.groups[0],p.groups[1]]=[p.groups[1],p.groups[0]]],
  ['duplicate rows',p=>p.groups[1]=p.groups[0]],
  ['wrong registration',p=>p.registration_id='0'.repeat(64)],
  ['other weights',p=>p.groups[0].public[0]='1'],
  ['disconnected activation',p=>p.groups[0].public[1]='1'],
  ['mixed context',p=>p.groups[0].public[3]='1'],
  ['different input',p=>p.input_commitment='1'],
  ['noncanonical number',p=>p.groups[0].public[4]='00'],
  ['public witness injection',p=>p.x=[1,2]],
  ['altered output commitment',p=>p.groups[0].public[2]='1'],
  ['altered pairing',p=>p.groups[0].proof.pi_a[0]='1'],
 ];
 try {
  const result=await verify(packageFile,registry);assert.equal(result.accept,true);console.log('Honest complete operation accepted',result.verify_ms,'ms');
  for(const [name,edit] of cases){const value=structuredClone(honest);edit(value);const file=path.join(folder,'bad.json');fs.writeFileSync(file,JSON.stringify(value));await assert.rejects(()=>verify(file,registry),undefined,name);console.log(name,'rejected');}
 }finally{fs.rmSync(folder,{recursive:true,force:true});}
}
main().then(()=>process.exit(0)).catch(error=>{console.error(error);process.exit(1);});
