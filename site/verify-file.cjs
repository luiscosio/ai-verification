#!/usr/bin/env node
// Registry paths come from the operator, never from the proof file.
const fs = require("node:fs"), path = require("node:path"), crypto = require("node:crypto");
const root = path.resolve(__dirname, ".."), g16 = root + "/code/llama.cpp/examples/receipts/zk/groth16";
const policy = require(g16 + "/verify.js"), pkg = require("./proof-package.js");
const snarkjs = require(g16 + "/node_modules/snarkjs");
function read(file, max) {
  if (fs.statSync(file).size > max) throw Error("File exceeds the size limit: " + file);
  return JSON.parse(fs.readFileSync(file, "utf8"));
}
(async () => {
  const args = process.argv.slice(2);
  if (![1, 3].includes(args.length) || (args.length === 3 && args[1] !== "--registry")) throw Error("Usage: node site/verify-file.cjs PROOF_FILE [--registry TRUSTED_DIRECTORY]");
  const registry = path.resolve(args[2] || root + "/registry");
  const proof = read(args[0], pkg.MAX_BYTES);
  const manifests = fs.readdirSync(registry, {withFileTypes: true}).filter(d => d.isDirectory())
    .map(d => path.join(registry, d.name, "manifest.json")).filter(f => fs.existsSync(f)).map(f => read(f, 16 * 1024 * 1024));
  const found = pkg.resolve(proof, manifests);
  const vkeys = {};
  if (found.manifest) {
    const {manifest, entry} = found;
    // These operator-installed registrations are checked with register.py before use.
    // Their IDs use Python JSON number encoding, not JavaScript's canonical key encoding.
    const hash = crypto.createHash("sha256").update(fs.readFileSync(g16 + "/verify.js")).digest("hex");
    if (manifest.proof_system?.groth16?.verifier_sha256 !== hash) throw Error("Verifier source does not match the trusted registration.");
    const circuit = entry.groth16.circuit;
    if (!/^r(8|16)_k(1024|1536|2048|3072)$/.test(circuit)) throw Error("Unsupported circuit.");
    vkeys[circuit] = read(path.join(registry, "circuits", circuit, "verification_key.json"), 2 * 1024 * 1024);
  }
  const result = await pkg.verify(proof, {manifests, vkeys}, policy, snarkjs);
  const {manifest, entry, ...verdict} = result;
  console.log(JSON.stringify({...verdict, coverage: "One Q4_K x Q8_K integer row group. Prompt, answer, scales and full inference are not proven.",
    setup: "Experimental single-contributor setup; not production assurance."}, null, 2));
  process.exit(result.accept ? 0 : 1);
})().catch(e => { console.error("Verification could not complete: " + String(e.message || e)); process.exit(2); });
