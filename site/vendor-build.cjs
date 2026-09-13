// Explicit maintenance command, not a network dependency of the site builder.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '..');
const g16 = path.join(root, 'code/llama.cpp/examples/receipts/zk/groth16');
const dest = path.join(__dirname, 'vendor');
for (const [file, version] of [
  [path.join(g16,'node_modules/snarkjs/package.json'),'0.7.5'],
  [path.join(__dirname,'node_modules/three/package.json'),'0.180.0'],
  [path.join(__dirname,'node_modules/esbuild/package.json'),'0.25.10']
]) {
  if (JSON.parse(fs.readFileSync(file)).version !== version) throw Error('Unexpected installed vendor version: '+file);
}
fs.mkdirSync(dest, {recursive:true});
esbuild.buildSync({entryPoints:[path.join(__dirname,'three-entry.js')], outfile:path.join(dest,'three.min.js'),
  bundle:true, minify:true, format:'iife', globalName:'ReceiptsThree', platform:'browser', target:'es2022', legalComments:'inline'});
fs.copyFileSync(path.join(g16,'node_modules/snarkjs/build/snarkjs.min.js'),path.join(dest,'snarkjs.min.js'));
fs.copyFileSync(path.join(g16,'node_modules/snarkjs/COPYING'),path.join(dest,'snarkjs.LICENSE'));
fs.copyFileSync(path.join(__dirname,'node_modules/three/LICENSE'),path.join(dest,'three.LICENSE'));
const hashes = {};
for (const file of ['three.min.js','snarkjs.min.js','snarkjs.LICENSE','three.LICENSE']) {
  const bytes=fs.readFileSync(path.join(dest,file));
  hashes[file]={sha256:crypto.createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length};
}
fs.writeFileSync(path.join(dest,'manifest.json'),JSON.stringify({snarkjs:'0.7.5',three:'0.180.0',esbuild:'0.25.10',files:hashes},null,2)+'\n');
