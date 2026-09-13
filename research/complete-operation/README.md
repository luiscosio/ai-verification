# One complete F20 matrix-vector proof

This experiment proves all 1,024 outputs of a 1,024-column Q4_K matrix-vector operation, including activation quantization, weight scales, accumulation and final rounding. Activations and outputs are private witnesses linked through salted commitments. It uses the registered Qwen3-0.6B tensor `blk.0.attn_k.weight`.

The claim is `experimental/f20-q4k-matvec/v1`. It proves the explicitly defined fixed-point relation in [STATEMENT.md](STATEMENT.md), not native llama.cpp floating-point equivalence or a model answer. It runs the existing Python arithmetic reference; this mode has not been integrated into llama.cpp. The public website continues to accept its narrower integer-row claim and rejects this research format.

## Measured result

One local run on an Apple M5 with 24 GiB RAM, September 13, 2026:

| Measurement | Result |
|---|---:|
| Complete operation | 1,024 × 1,024 |
| Proofs | 1 quantization + 64 row groups |
| Reference matrix-vector computation | 4.79 ms |
| Witness generation, summed | 23.67 s |
| Proving, summed | 266.71 s |
| Peak prover process RSS | 2.91 GiB |
| Public package | 69,685 bytes |
| Verification loop | 576 ms |
| Cold verifier process | 636 ms |
| Verifier process RSS | 201 MiB |
| Quantization circuit | 240,115 constraints |
| One 16-row circuit | 132,002 constraints |

Verification reads neither weights nor activation openings, but is still much slower than the 4.79 ms arithmetic reference for this operation. The reference timing excludes model loading and preparation. Witness/proving times exclude circuit compilation, ceremony, registration and independent commitment computation; 290.38 seconds is their sum, not the full driver runtime. This is one selected operation and input, not a timing corpus. RSS does not establish the plan's total-system memory or no-swap budget. [Raw timings](results/2026-09-13/report.json), [environment and material hashes](results/2026-09-13/environment.json), and [scaling calculation](results/2026-09-13/scaling.json) preserve these limits.

The current registration contains 381,681,664 Q4 weight values. Linear extrapolation from the measured 16 × 1,024 groups gives roughly **26.1 hours proving plus 2.3 hours witness generation** for that Q4 work per token. This is an estimate, not a measured token runtime or a lower-bound theorem. It excludes Q6, quantization at other layers, nonlinear operations, cache state, private links across operations, token selection and aggregation. Different K shapes also change circuit costs. The result argues against extending this serial Groth16 construction directly across the whole token.

The 50 MiB / 10 s planning thresholds are met by this one operation only. No full-inference stage gate or production security target is marked complete.

## Verify the published result without weights

From the repository root, install only the verifier dependencies:

```sh
git submodule update --init --recursive
npm ci --prefix code/llama.cpp/examples/receipts/zk/groth16
node research/complete-operation/verify.cjs \
  research/complete-operation/results/2026-09-13/operation.proof.json \
  research/complete-operation/results/2026-09-13/registry
node research/complete-operation/check_package.cjs \
  research/complete-operation/results/2026-09-13/operation.proof.json \
  research/complete-operation/results/2026-09-13/registry
```

The registry argument is an operator-installed trust anchor. Never install a replacement registry supplied with an untrusted proof. This project's registration and ceremony have not received independent review. `check_package.cjs` checks honest acceptance and 12 rejection cases. On macOS, run the isolation test with real permission-denial controls:

```sh
bash research/complete-operation/verify_isolated.sh \
  research/complete-operation/results/2026-09-13/operation.proof.json \
  research/complete-operation/results/2026-09-13/registry
```

The copied verifier has no model, proving key or witness. The sandbox denies network access and reads from the original project, and tests that both restrictions actually take effect. This is a local implementation check, not second-person reproduction or a cryptographic audit.

## Reproduce proving and arithmetic checks

Install the ordinary workspace and the existing setup file, then the separate measured research materials. They are published in the [complete-operation-v1 release](https://github.com/luiscosio/ai-verification/releases/tag/complete-operation-v1), with SHA-256 and byte-size checks in the installer. Existing website proving keys are a different circuit and cannot be substituted.

```sh
./setup-workspace.sh --include-setup
uv run --project tools/workspace --locked python research/complete-operation/install_materials.py
uv run --project tools/workspace --locked python research/complete-operation/check_registration.py \
  research/complete-operation/results/2026-09-13/registry
uv run --project tools/workspace --locked python research/complete-operation/check_witnesses.py \
  --build .receipts-research
uv run --project tools/workspace --locked python research/complete-operation/run.py \
  --build .receipts-research --out .receipts-research/run-1
python3 research/complete-operation/scaling.py \
  --build .receipts-research --run .receipts-research/run-1
```

Use a fresh output directory for each run. `--asset-dir` on the research installer supports a downloaded offline asset set. The registration check recomputes every weight-and-scale commitment from the exact GGUF; it does not audit key derivation or ceremony trust. The runner uses the normalized F20 embedding of token ID 0 as a reproducible input and compares all output commitments against the reference. That preparation is outside the proof. This benchmark input is publicly reconstructible from its documented source; a protocol-private witness declaration does not make already published information secret.

Private input and witness files stay in a temporary directory and are removed by the runner; only commitments, proofs, keys, registration and measurement metadata are exported. Fresh salts, request context and Groth16 randomness mean proof bytes differ across runs. An output consists of 64 private output commitments; this experiment does not disclose or prove a readable answer.

To compile from source with Circom 2.2.3 and create a **new experimental setup**, use a fresh directory:

```sh
bash research/complete-operation/build.sh .receipts-research-new
```

This intentionally creates different keys and therefore a different registration. The generated `integer_core.circom` only namespaces the pinned legacy `Bits2Num` helper to avoid a circomlib name collision. `build.sh` refuses to overwrite existing setup keys. Heavy setup/proving jobs should run sequentially on this machine. The measured R1CS/WASM hashes and wrapper source hashes are published so a fresh compilation can be compared independently.

## What the local checks establish

- Every actual output row's commitment matched the independent integer reference during proving; all 65 proofs passed.
- The verifier rejects omitted, duplicated or reordered rows, different weights, disconnected quantized inputs, mixed contexts, changed input/output commitments, noncanonical signals, unexpected top-level fields and an altered pairing proof.
- Witness checks exercise zero blocks, equal-magnitude sign selection, positive/negative rounding ties, the negative input boundary, out-of-range inputs, invalid q8 values, scales and non-boolean weight bits.
- Verification passed with the original project and network inaccessible. Registration commitments were recomputed from the GGUF. Both research zkeys were checked against their R1CS and the existing setup file before release; exported keys matched the checked-in verification keys.

These tests establish useful implementation evidence. They do not replace a constraint audit, an application-specific composition review, an independent registrar, or a trustworthy ceremony. The documented composition argument is conditional on sound component proofs and binding commitments. Setup remains experimental and single-contributor.

## Next research decision

Retain this exact operation, private interfaces and benchmark input as a comparison target. The next bounded experiment should test whether a different proof construction materially reduces the measured costs while preserving those semantics and privacy guarantees. Before a whole-token port, settle native versus separately registered F20 execution, review boundary composition, cover Q6 and nonlinear operations, and adopt the resource/security budgets. A faster partial claim is not a valid comparison.
