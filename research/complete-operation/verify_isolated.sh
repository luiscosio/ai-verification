#!/bin/bash
# macOS isolation test: install only public proof, registration and verifier dependencies.
set -euo pipefail
[ "$#" -eq 2 ] || { echo "usage: $0 PROOF_FILE REGISTRY_DIR" >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ISO="$(mktemp -d /tmp/complete-operation-isolated.XXXXXX)"
ISO="$(cd "$ISO" && pwd -P)"
trap 'rm -rf "$ISO"' EXIT
mkdir -p "$ISO/research/complete-operation" "$ISO/code/llama.cpp/examples/receipts/zk/groth16" "$ISO/denied"
cp "$ROOT/research/complete-operation/verify.cjs" "$ISO/research/complete-operation/"
cp -R "$ROOT/code/llama.cpp/examples/receipts/zk/groth16/node_modules" "$ISO/code/llama.cpp/examples/receipts/zk/groth16/"
cp "$1" "$ISO/proof.json"
cp -R "$2" "$ISO/registry"
printf 'isolation control\n' > "$ISO/denied/sentinel"
cat > "$ISO/control.cjs" <<'JS'
const fs=require('fs'),net=require('net');
const denied=e=>e&&['EPERM','EACCES'].includes(e.code);
try { fs.readFileSync(process.argv[2]);throw Error('File control is readable'); }
catch(e){if(!denied(e))throw e;}
const server=net.createServer();
server.on('error',e=>{if(!denied(e)){console.error(e);process.exit(1);}console.log('File and network permission-denial controls passed');});
server.listen(0,'127.0.0.1',()=>{console.error('Network control is reachable');server.close();process.exitCode=1;});
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
"${SANDBOX[@]}" "$NODE" control.cjs "$ISO/denied/sentinel"
"${SANDBOX[@]}" "$NODE" research/complete-operation/verify.cjs proof.json registry
