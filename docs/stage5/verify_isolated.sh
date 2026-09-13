#!/bin/bash
# Stage 5: verify a Groth16 proof package in isolation: a fresh directory holding only the
# verification key, the manifest and the package; no network; the model directories unreadable.
#
#   ./verify_isolated.sh <build dir with verification_key.json> <manifest.json> <tensor> <group> <package dir with proof.json public.json>
#
# Uses macOS sandbox-exec to deny network access and reads of the model files, and runs the
# check with a copy of snarkjs. Exit 0 only when the pairing check passes and the proof's
# commitment is the registered one.
set -euo pipefail
BUILD="$1"; MANIFEST="$2"; TENSOR="$3"; GROUP="$4"; PKG="$5"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SNARKJS_SRC="$ROOT/code/llama.cpp/examples/receipts/zk/groth16/node_modules"
ISO="$(mktemp -d /tmp/receipts-isolated.XXXXXX)"
cp "$BUILD/verification_key.json" "$MANIFEST" "$PKG/proof.json" "$PKG/public.json" "$ISO/"
cp -R "$SNARKJS_SRC" "$ISO/node_modules"
cat > "$ISO/check.js" <<'JS'
const fs = require("fs"); const snarkjs = require("snarkjs");
(async () => {
  const [tensor, group] = process.argv.slice(2);
  const vkey = JSON.parse(fs.readFileSync("verification_key.json")); const manifest = JSON.parse(fs.readFileSync("manifest.json"));
  const proof = JSON.parse(fs.readFileSync("proof.json")); const pub = JSON.parse(fs.readFileSync("public.json"));
  const t0 = Date.now();
  let pairing = false, error = null;
  try { pairing = await snarkjs.groth16.verify(vkey, pub, proof); } catch (e) { error = String(e.message || e); }
  const entry = manifest.tensors.find((t) => t.name === tensor);
  const registered = entry && entry.groth16 ? entry.groth16.groups[+group] : null;
  const bound = registered !== null && pub[0] === registered;
  console.log(JSON.stringify({ pairing, bound, error, registered_prefix: (registered || "").slice(0, 16), proof_prefix: String(pub[0]).slice(0, 16), ms: Date.now() - t0, files_in_dir: fs.readdirSync(".").filter((f) => f !== "node_modules") }));
  process.exit(pairing && bound ? 0 : 1);
})().catch((e) => { console.error(String(e)); process.exit(2); });
JS
PROFILE="(version 1)
(allow default)
(deny network*)
(deny file-read* (subpath \"$HOME/.ollama\") (subpath \"$ROOT/models\") (subpath \"$ROOT/code\") (subpath \"$ROOT/demo\") (subpath \"$ROOT/registry\"))"
echo "isolated dir: $ISO ($(ls "$ISO" | grep -v node_modules | tr '\n' ' '))"
echo "sandbox: no network; $HOME/.ollama, models/, code/, demo/, registry/ unreadable"
cd "$ISO"
set +e
sandbox-exec -p "$PROFILE" "$(command -v node)" check.js "$TENSOR" "$GROUP"; rc=$?
set -e
echo "exit $rc ($([ $rc = 0 ] && echo ACCEPT || echo REJECT))"
echo "--- control: the same sandbox cannot read the model file:"
sandbox-exec -p "$PROFILE" /bin/cat "$ROOT/models/qwen3-0.6b-q4_k_m.gguf" > /dev/null 2>&1 && echo "model READABLE (sandbox not effective)" || echo "model unreadable, as intended"
echo "--- control: the same sandbox has no network:"
sandbox-exec -p "$PROFILE" /usr/bin/curl -s -m 5 https://example.com > /dev/null 2>&1 && echo "network REACHABLE (sandbox not effective)" || echo "network unreachable, as intended"
rm -rf "$ISO"
exit $rc
