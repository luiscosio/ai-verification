#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
G16="$ROOT/code/llama.cpp/examples/receipts/zk/groth16"
DEST="${1:-$ROOT/.receipts-research}"
for name in quant_k1024 rows16_k1024; do
    if [ -e "$DEST/$name/main_final.zkey" ]; then
        echo 'Use a fresh build directory; existing research setup keys will not be replaced.' >&2
        exit 2
    fi
done
mkdir -p "$DEST"
DEST="$(cd "$DEST" && pwd)"
# Namespace the legacy helper to avoid circomlib's unrelated Bits2Num symbol.
python3 - "$G16/qdot_rows.circom" "$DEST/integer_core.circom" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[2]).write_text(Path(sys.argv[1]).read_text().replace('Bits2Num','WeightBits2Num'))
PY
for name in quant_k1024 rows16_k1024; do
    mkdir -p "$DEST/$name"
    if [ "$name" = quant_k1024 ]; then
        printf 'pragma circom 2.1.6;\ninclude "full_matvec.circom";\ncomponent main {public [context]} = Quantize(1024);\n' > "$DEST/$name/main.circom"
    else
        printf 'pragma circom 2.1.6;\ninclude "full_matvec.circom";\ncomponent main {public [context,group]} = CompleteRows(16,1024);\n' > "$DEST/$name/main.circom"
    fi
    circom "$DEST/$name/main.circom" --O2 --r1cs --wasm --sym -l "$ROOT/research/complete-operation" -l "$DEST" -l "$G16" -o "$DEST/$name"
    bash "$G16/setup.sh" "$DEST/$name" "$G16/ptau/pot18_final.ptau"
done
