const assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const root = path.resolve(__dirname, ".."), g16 = root + "/code/llama.cpp/examples/receipts/zk/groth16";
const verifier = require(g16 + "/verify.js"), snarkjs = require(g16 + "/node_modules/snarkjs");
const read = p => JSON.parse(fs.readFileSync(p));
const manifest = read(root + "/registry/qwen3-0.6b-q4_k_m/manifest.json");
const entry = manifest.tensors.find(t => t.name === "blk.0.attn_k.weight");
const key = read(root + "/registry/circuits/r16_k1024/verification_key.json");
const fixture = name => read(__dirname + "/fixtures/groth16/" + name + ".json");
const copy = x => JSON.parse(JSON.stringify(x));
(async () => {
    let count = 0;
    const check = async (pub, proof, accept, m = manifest, group = 0, vk = key) => {
        const result = await verifier.verify(snarkjs, m, entry, group, vk, pub, proof);
        assert.equal(result.accept, accept, JSON.stringify(result)); count++;
    };
    const pub = fixture("honest-public"), proof = fixture("honest-proof");
    await check(pub, proof, true);
    // This invalid witness has a valid pairing and the honest weight commitment.
    const invalid = fixture("out-of-range-public"), invalidProof = fixture("out-of-range-proof");
    assert.equal(await snarkjs.groth16.verify(key, invalid, invalidProof), true);
    assert.equal(invalid[0], entry.groth16.groups[0]);
    await check(invalid, invalidProof, false);
    for (const value of ["128", "-1", "00", "1e2", 1, null, "<svg/onload=alert()>", "21888242871839275222246405745257275088548364400416034343698204186575808495617"]) {
        const bad = [...pub]; bad[1] = value; await check(bad, proof, false);
    }
    for (const [index, value] of [[0, "<svg/onload=alert()>"], [1025, "30723841"], [1089, "2048257"]]) {
        const bad = [...pub]; bad[index] = value; await check(bad, proof, false);
    }
    await check(pub.slice(1), proof, false); await check(pub, proof, false, manifest, -1);
    await check(pub, proof, false, manifest, 1);
    const wrongPin = copy(manifest); wrongPin.proof_system.groth16.verification_keys.r16_k1024 = "0".repeat(64);
    await check(pub, proof, false, wrongPin);
    const badKey = copy(key); badKey.nPublic++; await check(pub, proof, false, manifest, 0, badKey);
    await check(pub, null, false);
    const changed = [...pub]; changed[1025] = String(BigInt(changed[1025]) + 1n); await check(changed, proof, false);
    const packages = require(root + "/site/proof-package.js");
    const data = {manifests:[manifest], vkeys:{r16_k1024:key}};
    const honestPackage = packages.envelope({manifest_id:manifest.manifest_id, tensor:entry.name, group:0, proof, public:pub});
    assert.equal((await packages.verify(honestPackage, data, verifier, snarkjs)).status, "verified");
    for (const [change, expected] of [
      [{format:"future"}, "unsupported"], [{claim:"full-inference"}, "unsupported"],
      [{registration_id:"0".repeat(64)}, "unknown-model"], [{answer:"Paris"}, "invalid"],
      [{group:1}, "invalid"], [{tensor:"../../fake"}, "invalid"], [{public:invalid, proof:invalidProof}, "invalid"]
    ]) assert.equal((await packages.verify({...honestPackage, ...change}, data, verifier, snarkjs)).status, expected);
    assert.equal((await packages.verify(honestPackage, data, verifier, undefined)).status, "unavailable");
    const catalogue = fs.readdirSync(root + "/registry").map(name => root + "/registry/" + name + "/manifest.json")
      .filter(file => fs.existsSync(file)).map(read);
    for (const other of catalogue.filter(m => m.manifest_id !== manifest.manifest_id)) {
      const t = other.tensors.find(t => t.groth16) || other.tensors[0];
      const otherKeys = {...data.vkeys};
      if (t.groth16) otherKeys[t.groth16.circuit] = read(root + "/registry/circuits/" + t.groth16.circuit + "/verification_key.json");
      const result = await packages.verify({...honestPackage, registration_id:other.manifest_id, tensor:t.name},
        {manifests:catalogue, vkeys:otherKeys}, verifier, snarkjs);
      assert.equal(result.accept, false, "A different model or fingerprint-only entry must not accept the Qwen3 proof");
    }
    // Exercise actual application rendering with a DOM that refuses HTML interpolation.
    class Element {
        constructor() { this.children = []; this.dataset = {}; this.value = ""; this.disabled = false; this.text = ""; }
        set innerHTML(_) { throw Error("HTML interpolation is forbidden"); }
        set textContent(s) { this.text = String(s); this.children = []; }
        get textContent() { return this.text + this.children.map(c => c.textContent).join(" "); }
        append(...children) { this.children.push(...children); }
        replaceChildren(...children) { this.text = ""; this.children = children; }
        addEventListener() {}
        focus() {}
        scrollIntoView() {}
    }
    const elements = Object.fromEntries(["run", "status", "result-view", "package-file"].map(k => [k, new Element()]));
    const script = fs.readFileSync(root + "/site/app.js", "utf8").replace(/init\(\);\s*$/, "");
    const context = vm.createContext({DATA:data, LOCAL:null, ProofPackage:packages,
        document:{createElement:() => new Element(), getElementById:id => elements[id]},
        ReceiptsVerifier:verifier, snarkjs, performance});
    vm.runInContext(script, context);
    await context.verifyPackage(honestPackage, "honest");
    assert.equal(elements["result-view"].dataset.state, "verified");
    assert.match(elements["result-view"].textContent, /answer and complete inference are not verified/);
    const html = [...pub]; html[0] = "<svg/onload=alert()>";
    await context.verifyPackage({...honestPackage, public:html}, "<img src=x onerror=alert(1)>");
    assert.equal(elements["result-view"].dataset.state, "invalid");
    assert.equal(elements.run.disabled, false);
    await context.verifyPackage({...honestPackage, public:invalid, proof:invalidProof}, "invalid activation");
    assert.match(elements["result-view"].textContent, /activation value is outside the allowed range/);
    elements["package-file"].files = [{size:1, name:"broken", text:async () => "{"}];
    await context.verifySelected(); assert.equal(elements["result-view"].dataset.state, "invalid");
    assert.doesNotMatch(elements["result-view"].textContent, /Computation proof verified/);
    console.log(`${count} Groth16 regressions, 9 envelope cases and 4 application-renderer cases passed`);
    process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
