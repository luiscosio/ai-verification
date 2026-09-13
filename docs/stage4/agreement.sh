#!/bin/bash
# Ground truth from llama.cpp (greedy, CPU) for a prompt list, then the fixed-point reference on the same prompts.
#   ./agreement.sh models/qwen3-0.6b-q4_k_m.gguf prompts.txt out/
set -euo pipefail
MODEL="$1"; PROMPTS="$2"; OUT="$3"; ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$OUT"; i=0; files=()
while IFS= read -r prompt; do
  [ -z "$prompt" ] && continue
  i=$((i + 1)); f="$OUT/p$(printf %02d $i).json"
  "$ROOT/code/llama.cpp/build/bin/llama-receipts" -m "$MODEL" -p "$prompt" -n 1 --temp 0 -ngl 0 -t 8 -c 128 -b 128 --out "$f" >/dev/null 2>&1
  files+=("$f")
done < "$PROMPTS"
echo "${#files[@]} receipts"
uv run --quiet --with numpy --with pyyaml python3 "$ROOT/docs/stage4/fixed_point_forward.py" "$MODEL" "${files[@]}" --report "$OUT/agreement.json"
