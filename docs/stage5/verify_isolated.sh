#!/bin/bash
# Verify trusted KEY_DIR MANIFEST TENSOR GROUP PACKAGE_DIR with no model or network access.
set -euo pipefail
[ "$#" -eq 5 ] || { echo "usage: $0 KEY_DIR MANIFEST TENSOR GROUP PACKAGE_DIR" >&2; exit 2; }
BUILD="$1"; MANIFEST="$2"; TENSOR="$3"; GROUP="$4"; PKG="$5"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
G16="$ROOT/code/llama.cpp/examples/receipts/zk/groth16"
ISO="$(mktemp -d /tmp/receipts-isolated.XXXXXX)"
ISO="$(cd "$ISO" && pwd -P)"
trap 'rm -rf "$ISO"' EXIT
# Refuse oversized files before copying or parsing them.
node - "$PKG" <<'JS'
const fs = require("fs"), dir = process.argv[2];
for (const [name, limit] of [["proof.json", 8192], ["public.json", 2000000]]) {
    if (fs.statSync(dir + "/" + name).size > limit) throw Error("package exceeds size limits");
}
JS
cp "$BUILD/verification_key.json" "$ISO/verification_key.json"
cp "$MANIFEST" "$ISO/manifest.json"
cp "$PKG/proof.json" "$PKG/public.json" "$G16/verify.js" "$G16/verify_package.cjs" "$ISO/"
cp -R "$G16/node_modules" "$ISO/node_modules"
mkdir "$ISO/denied"
printf 'isolation control\n' > "$ISO/denied/sentinel"
cat > "$ISO/control.cjs" <<'JS'
const fs = require("fs"), net = require("net");
const denied = e => e && ["EPERM", "EACCES"].includes(e.code);
// A real read must work outside the sandbox and fail with a permission error inside it.
try { fs.readFileSync(process.argv[2]); throw Error("file control is readable"); }
catch (e) { if (!denied(e)) throw e; }
const server = net.createServer();
server.on("error", e => {
    if (!denied(e)) { console.error(e); process.exit(1); }
    console.log("controls passed: file and network operations denied by permissions");
});
server.listen(0, "127.0.0.1", () => { console.error("network control is reachable"); server.close(); process.exitCode = 1; });
JS
cat > "$ISO/profile.sb" <<'SB'
(version 1)
(allow default)
(deny network*)
(deny file-read* (subpath (param "PROJECT")) (subpath (param "OLLAMA")) (subpath (param "DENIED")))
SB
NODE="$(command -v node)"
"$NODE" -e 'require("fs").readFileSync(process.argv[1])' "$ISO/denied/sentinel"
cd "$ISO"
SANDBOX=(sandbox-exec -D "PROJECT=$ROOT" -D "OLLAMA=$HOME/.ollama" -D "DENIED=$ISO/denied" -f "$ISO/profile.sb")
# Any startup error or ineffective control fails the run before verification.
"${SANDBOX[@]}" "$NODE" control.cjs "$ISO/denied/sentinel"
"${SANDBOX[@]}" "$NODE" verify_package.cjs verification_key.json manifest.json "$TENSOR" "$GROUP" .
