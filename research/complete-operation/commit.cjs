const fs=require('node:fs'),path=require('node:path');
const {buildPoseidon}=require(path.resolve(__dirname,'../../code/llama.cpp/examples/receipts/zk/groth16/node_modules/circomlibjs'));
function pack(values,per,bits){const out=[];for(let i=0;i<values.length;i+=per){let v=0n;for(let j=0;j<per&&i+j<values.length;j++)v+=BigInt(values[i+j])<<BigInt(j*bits);out.push(v);}return out;}
async function main(){
 const data=JSON.parse(fs.readFileSync(0,'utf8')); const poseidon=await buildPoseidon();
 const hash=values=>poseidon.F.toObject(poseidon(values));
 const chain=values=>{const n=values.length<=16?16:16+15*Math.ceil((values.length-16)/15);while(values.length<n)values.push(0n);let h=hash(values.slice(0,16));for(let i=16;i<n;i+=15)h=hash([h,...values.slice(i,i+15)]);return h;};
 const vector=(values,domain,bits,context=0,index=0,salt=0)=>chain([BigInt(domain),BigInt(context),BigInt(index),BigInt(salt),BigInt(values.length),...pack(values,Math.floor(240/bits),bits)]);
 if(data.groups){console.log(JSON.stringify(data.groups.map(g=>{
  const core=chain([0n,...pack(g.q4,62,4),...pack(g.sc,41,6),...pack(g.mn,41,6)]);
  const scales=vector([...g.D,...g.Dmin].map(x=>BigInt(x)+(1n<<40n)),3001,41);
  return hash([core,scales,BigInt(data.rows),BigInt(data.k)]).toString();
 })));}else{console.log(vector(data.values.map(x=>BigInt(x)+(1n<<39n)),data.domain,40,data.context,data.index||0,data.salt).toString());}
}
main().catch(error=>{console.error(error.message);process.exit(1);});
