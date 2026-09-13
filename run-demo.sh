#!/bin/bash
# End-to-end demo of llama-receipts: prove with a trace, verify without the model, replay,
# check the Lean specification against the same trace, prove one matmul node with Expander against a
# registered commitment, and prove one row group of it in zero knowledge with Groth16.
#
#   ./run-demo.sh                # full run, writes into ./demo/run.XXXXXX/
#   ./run-demo.sh --fresh        # compatibility alias; every run uses a new directory
#
# Prerequisites (all present on this machine): the llama.cpp fork built at code/llama.cpp (branch
# receipts-all, with the receipts example, the Lean spec and the zk crate), elan in ~/.elan, uv, and
# the qwen2.5 1.5B Q4_K_M Ollama blob.

set -euo pipefail

MODEL="${MODEL:-$HOME/.ollama/models/blobs/sha256-183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
LLAMA="${LLAMA:-$ROOT/code/llama.cpp}"                     # fork, branch receipts-all: receipts, spec and zk together
LEAN="${LEAN:-$LLAMA}"
DEMO_ROOT="${DEMO_ROOT:-$ROOT/demo}"
PROMPT="${PROMPT:-Explain to a ten-year-old why the sky is blue.}"
N_PREDICT="${N_PREDICT:-12}"
OPENINGS="${OPENINGS:-32}"
export PATH="$HOME/.elan/bin:$PATH"

PY="${PYTHON_RUNNER:-uv run --quiet --with numpy --with pyyaml python3}"
# llama.cpp's loader is chatty; drop its progress lines, keep everything else
QUIET='^(load|print_info|llama_|ggml_|common|graph|sched|system_info|build|main:|\.\.\.\.|[0-9.]+ I (load|print_info|llama_|ggml|common|graph|sched))'

step=0
t_start=$(date +%s)
banner() {
    step=$((step + 1))
    printf '\n\033[1;36m━━━ %d. %s ━━━\033[0m\n' "$step" "$1"
}
show() {   # print the command, then run it
    printf '\033[1;32m$\033[0m %s\n' "$*"
    "$@"
}
elapsed() { printf '\033[2m   (%ss)\033[0m\n' "$(( $(date +%s) - t0 ))"; }

mkdir -p "$DEMO_ROOT"
DEMO=$(mktemp -d "$DEMO_ROOT/run.XXXXXX")
cd "$DEMO"
DEMO=$(pwd)

for f in "$MODEL" "$LLAMA/build/bin/llama-receipts" "$LLAMA/examples/receipts/verify_trace.py" \
         "$LLAMA/examples/receipts/zk/target/release/receipts-zk" "$LEAN/examples/receipts/spec/lakefile.toml"; do
    [ -e "$f" ] || { echo "missing: $f"; exit 1; }
done
command -v lake >/dev/null || { echo "lake not on PATH (elan install?)"; exit 1; }

banner "Prove: generate on CPU with a receipt and an activation trace"
t0=$(date +%s)
printf '\033[1;32m$\033[0m llama-receipts -m qwen2.5-1.5b-q4_k_m.gguf -p "%s" -n %s --seed 5 --temp 0.7 -ngl 0 -t 8 --trace --openings %s --out receipt.json\n' "$PROMPT" "$N_PREDICT" "$OPENINGS"
"$LLAMA/build/bin/llama-receipts" -m "$MODEL" -p "$PROMPT" -n "$N_PREDICT" --seed 5 --temp 0.7 --top-k 40 --top-p 0.95 \
    -ngl 0 -t 8 -c 1024 -b 512 --trace --openings "$OPENINGS" --out receipt.json 2>&1 | { grep -Ev "$QUIET" || [ "$?" -eq 1 ]; }
elapsed
ls -la receipt.json receipt.trace.json

banner "Verify the trace without running the model"
t0=$(date +%s)
# This local demo pins the topology produced above. A deployed verifier stores this digest from a separately trusted reference run.
TOPOLOGY=$($PY -c 'import json; print(json.load(open("receipt.json"))["trace"]["topology_sha256"])')
show $PY "$LLAMA/examples/receipts/verify_trace.py" receipt.json --model "$MODEL" --expected-topology-sha256 "$TOPOLOGY" --report verify-report.json
elapsed

banner "Verify by replay (re-runs the model; same backend, expect bit-exact)"
t0=$(date +%s)
printf '\033[1;32m$\033[0m llama-receipts -m qwen2.5-1.5b-q4_k_m.gguf --replay receipt.json -ngl 0 -t 8\n'
"$LLAMA/build/bin/llama-receipts" -m "$MODEL" --replay receipt.json -ngl 0 -t 8 -c 1024 -b 512 --report replay-report.json 2>&1 | { grep -Ev "$QUIET" || [ "$?" -eq 1 ]; }
elapsed

banner "Formal spec (Lean 4): build, SHA-256 self-test, check the same trace"
t0=$(date +%s)
pushd "$LEAN/examples/receipts/spec" >/dev/null
show lake build
show ./.lake/build/bin/spec-check sha256
show ./.lake/build/bin/spec-check trace "$DEMO/receipt.json" "$DEMO/receipt.trace.json" "$TOPOLOGY"
elapsed

banner "Formal spec: arithmetic vectors from the GGUF, checked by Lean"
t0=$(date +%s)
show $PY gen_vectors.py "$DEMO/receipt.json" --model "$MODEL" --out "$DEMO/vectors.json"
show ./.lake/build/bin/spec-check vectors "$DEMO/vectors.json" --emit "$DEMO/lean-vectors.json"
popd >/dev/null
elapsed

banner "The proof circuit against the Lean spec, on the same vectors"
t0=$(date +%s)
pushd "$LLAMA/examples/receipts/zk" >/dev/null
show $PY diff_spec.py "$DEMO/vectors.json" "$DEMO/lean-vectors.json"
popd >/dev/null
elapsed

banner "Integrity proof of one matmul node with a registered weight commitment (Expander, GKR over Mersenne-31)"
t0=$(date +%s)
# pick the smallest opened Q4_K weight matmul of a decode graph, so the demo stays quick
INDEX=$($PY - "$DEMO/receipt.trace.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1])); L = d["leaves"]
c = [(L[o["index"]]["srcs"][0]["base"]["ne"][0] * L[o["index"]]["srcs"][0]["base"]["ne"][1], o["index"]) for o in d["openings"]
     if L[o["index"]]["op"] == "MUL_MAT" and L[o["index"]]["srcs"][0].get("kind") == "weight"
     and L[o["index"]]["srcs"][0]["base"]["type"].lower() == "q4_k" and L[o["index"]]["g"] > 0 and L[o["index"]]["out"]["ne"][1] == 1]
print(min(c)[1] if c else "")
EOF
)
if [ -z "$INDEX" ]; then echo "no opened Q4_K decode matmul in this trace; try more openings"; exit 1; fi
pushd "$LLAMA/examples/receipts/zk" >/dev/null
show $PY zk_node.py "$DEMO/receipt.json" --model "$MODEL" --index "$INDEX" --config orion --out "$DEMO/zk-out"
popd >/dev/null
elapsed

banner "Zero-knowledge proof of one row group of the same node (Groth16, private weights under a Poseidon commitment)"
t0=$(date +%s)
pushd "$LLAMA/examples/receipts/zk/groth16" >/dev/null
if [ -f build/r16_k1536/main_final.zkey ] && [ -d node_modules ]; then
    show $PY groth16_node.py "$DEMO/receipt.json" --model "$MODEL" --index "$INDEX" --groups 0 --out "$DEMO/groth16-out"
else
    echo "missing Groth16 prerequisites: run npm install and ./setup.sh build/r16_k1536 ptau/pot18_final.ptau in $LLAMA/examples/receipts/zk/groth16 first (see its README)"
    exit 1
fi
popd >/dev/null
elapsed

printf '\n\033[1;36m━━━ done in %ss. Artifacts in %s ━━━\033[0m\n' "$(( $(date +%s) - t_start ))" "$DEMO"
ls -la "$DEMO" "$DEMO/zk-out" "$DEMO/groth16-out" 2>/dev/null | sed 's/^/   /'
