// The envelope contains lookup hints and public proof inputs, never trusted keys or a verdict.
(function (root) {
  "use strict";
  const FORMAT = "llama-receipts/proof-package/v1";
  const CLAIM = "q4k-integer-row-group/v1";
  const MAX_BYTES = 2 * 1024 * 1024;
  const fields = ["format", "claim", "registration_id", "tensor", "group", "proof", "public"].sort();
  function envelope(example) {
    return {format: FORMAT, claim: CLAIM, registration_id: example.manifest_id,
      tensor: example.tensor, group: example.group, proof: example.proof, public: example.public};
  }
  function resolve(pkg, manifests) {
    if (!pkg || typeof pkg !== "object" || Array.isArray(pkg)) return {status: "invalid", error: "This file is not a proof package."};
    if (pkg.format !== FORMAT || pkg.claim !== CLAIM) return {status: "unsupported", error: "This verifier does not support this proof format or computation claim. Use the matching verifier release."};
    if (Object.keys(pkg).sort().join("|") !== fields.join("|") ||
        typeof pkg.registration_id !== "string" || !/^[0-9a-f]{64}$/.test(pkg.registration_id) ||
        typeof pkg.tensor !== "string" || pkg.tensor.length > 256 || !Number.isSafeInteger(pkg.group) || pkg.group < 0 ||
        !Array.isArray(pkg.public) || JSON.stringify(pkg.public).length > 2000000 ||
        !pkg.proof || typeof pkg.proof !== "object" || JSON.stringify(pkg.proof).length > 8192) {
      return {status: "invalid", error: "The package has missing, extra, oversized or malformed fields."};
    }
    const manifest = manifests.find(m => m.manifest_id === pkg.registration_id);
    if (!manifest) return {status: "unknown-model", error: "This model registration is not in this verifier's trusted registry. Obtain a trusted registry update independently; the proof cannot approve its own registration."};
    const entry = manifest.tensors.find(t => t.name === pkg.tensor);
    if (!entry?.groth16) return {status: "invalid", error: "The selected computation is not registered for this model."};
    return {manifest, entry};
  }
  async function verify(pkg, data, policy, snarkjs) {
    const found = resolve(pkg, data.manifests);
    if (found.status) return {...found, accept: false};
    const {manifest, entry} = found;
    const key = data.vkeys[entry.groth16.circuit];
    if (!key || !snarkjs?.groth16?.verify) return {status: "unavailable", accept: false, error: "Verification materials could not load. Retry when the verifier is available, or use the offline verifier."};
    const checked = await policy.verify(snarkjs, manifest, entry, pkg.group, key, pkg.public, pkg.proof);
    return {...checked, status: checked.accept ? "verified" : "invalid", manifest, entry, group:pkg.group};
  }
  const api = {FORMAT, CLAIM, MAX_BYTES, envelope, resolve, verify};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ProofPackage = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
