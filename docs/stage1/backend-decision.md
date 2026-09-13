# Stage 1 decision record: backend, first model, budgets

Date: 2026-09-13. Plan: `../../PLAN.md`, Stage 1; progress in `../../TODO.md`. Statement: `statement.md`. Data: `ranges-*.json`, produced by `trace_stats.py`.

## Decision

Expander and its circuit compiler stay as the arithmetization and prover. No candidate demonstrates the zero-knowledge and hiding-commitment interface the plan requires today; the missing engineering is listed below and is the content of Stage 3. Model binding without zero knowledge already works: the proof carries a commitment to the private weights and the verifier, holding no weights, refuses any proof whose commitment is not the registered one (`../../code/llama.cpp/examples/receipts/zk`).

Stage 1's exit gate is met through its second clause: the missing engineering is identified explicitly.

## Candidates

| Backend | Zero knowledge | Weight commitment | Arithmetic | Licence | Verdict |
|---|---|---|---|---|---|
| Expander + ExpanderCompilerCollection (Rust; rev 096581e via fork `luiscosio/Expander` b07edf4) | No. No masking anywhere in the `sumcheck`, `gkr` or `gkr_engine` crates. Polyhedra's writing cites Libra's masking as the technique; the code does not implement it. | Orion (hash-based, deterministic, binding, not hiding), Hyrax (Pedersen, no blinding factor in `commit`), HyperKZG and BiKZG (no blinding). Parameters come from `expander_pcs_init_testing_only` with a fixed test RNG: reproducible, labelled testing-only. | Ours: the circuit is written against ggml's Q4_K x Q8_K integer kernel and checked against the Lean spec. | AGPL-3.0 | Keep as arithmetization and prover; add the ZK layer. |
| DeepProve (Lagrange) | Not claimed in the README beyond the name; the text emphasises succinctness. | Not documented. | Its own 12-bit quantization ("99.6% cosine similarity to the float baseline"). Fails the native-semantics rule. | Lagrange License, not open source | Reject as backend. Reference for lookup-based nonlinear ops. |
| EZKL | Yes (Halo2). | KZG or IPA, hiding possible. | ONNX import with its own fixed-point scale. Fails the native-semantics rule. | Apache-2.0 | Reject as backend. Reference for browser verification and lookups. |
| Halo2 with hand-written circuits | Yes by default. | KZG with blinding, hiding. | Would be ours. | MIT/Apache | Viable only per operation: a whole token of the 0.6B model is about 2^29 constraint rows, beyond a laptop's memory and hours of proving. Not chosen. |
| zkLLM (Sun et al., CCS 2024) | Yes, ZK sumcheck with private model commitments. | Yes. | Its own tensor arithmetic. | Research code, CUDA only | Reference design for masking and committed weights. Does not run here. |

## Findings from Expander's source

- The proof stream is: the public inputs (checked back by the verifier), the PCS commitment to the private input layer, the GKR transcript, then the PCS openings. The commitment is therefore extractable and comparable with a registered value, which is what `receipts-zk verify --commitment` does.
- Orion commits deterministically: the same private input layer gives the same 32-byte root on any machine with the same parameters. That makes registration reproducible from the open weights, and it means the commitment hides nothing.
- Hyrax and KZG exist for the BN254 field only. A hiding commitment therefore implies the BN254 configuration, which is also what the whole-token field decision needs (see `statement.md`).
- Witness from llama.cpp: done. `zk_node.py` builds the witness from the receipt's opened activation bytes and the GGUF, in the kernel's own read order, and the circuit accepts exactly the sums the Lean specification computes for the same bytes (`diff_spec.py`, 3 of 3 rows accepted, perturbations rejected).

## Missing engineering for zero knowledge, in order

1. Zero-knowledge sumcheck: Libra-style masking polynomials in Expander's prover and verifier. Research-grade; a fork change.
2. Hiding commitment: blinding factors in Hyrax's commit and opening over BN254, or a hiding variant of Orion. Registration then needs the blinding to be reproducible or the correspondence to be proven once.
3. BN254 configuration for the whole-token circuit, or limb arithmetic in Mersenne-31. Expected cost: roughly an order of magnitude slower proving than M31 SIMD.
4. Published PCS parameters: replace the testing-only RNG by parameters shipped in the registration manifest.
5. Circuits for Q6_K matmuls and for the float operations under the fixed-point execution mode (Stage 4).

## What was measured

Apple M5, 24 GB, CPU backend, 8 threads. "One token" is an 8-token prompt plus one generated token.

| Model | Params | Layers, hidden, FFN | Types after Q4_K_M | Load and hash | One token | Nodes per decode graph | max abs activation |
|---|---|---|---|---|---|---|---|
| Qwen2.5-1.5B-Instruct (Ollama blob) | 1.5B | 28, 1536, 8960 | Q4_K, Q6_K, F32 | 4.7 s | 0.06 s | 622 | 5,968 (ADD) |
| Qwen2.5-0.5B-Instruct (Qwen GGUF, and our own requantization) | 0.5B | 24, 896, 4864 | Q5_0 for 133 tensors, Q8_0, Q6_K, Q4_K | 2.5 s | 0.05 s | 534 | 1,572 |
| Qwen3-0.6B (our Q4_K_M from unsloth bf16) | 0.6B | 28, 1024, 3072 | Q4_K 168, Q6_K 29, F32 113 | 1.7 s | 0.03 s | 650 | 6,557 (ADD) |

Activations need 14 signed integer bits in every model measured. `RMS_NORM` outputs stay below 32, attention outputs below 30, `ROPE` and KV writes below 415, `SWIGLU` up to 4,280.

One node, `Vcur-22` of the 1.5B model (256 x 1536, Q4_K), Orion, private weights: register 2.0 s, compile 1.8 s, prove 0.28 s, proof 6.5 MB, verify 0.04 s plus compile, float step error 3.8e-7. Rejected: a tampered public sum, a proof made with one changed nibble (different commitment), the honest proof against the next layer's registered commitment.

## First model and configuration

Qwen3-0.6B, requantized by us to Q4_K_M:

- source `unsloth/Qwen3-0.6B-GGUF` `Qwen3-0.6B-BF16.gguf`, SHA-256 `f9c9f1d3c1e21755b82d4e165f88dbbbd4355646d632fb5d6cef7c66ed4ee04e`
- `llama-quantize --allow-requantize <bf16> <out> Q4_K_M` from the fork at `dce95937b`
- result `models/qwen3-0.6b-q4_k_m.gguf`, SHA-256 `42d6e666a335641d99d74645baa076df60e9f18c50646a722469ca9d5c20f5bf`, 396,705,216 bytes
- 28 layers, hidden 1024, 16 heads and 8 KV heads of 128, FFN 3072, tokenizer `gpt2` BPE, output projection tied to `token_embd` (Q6_K)

Why this one: every matmul dimension (1024, 2048, 3072) is a multiple of the 256-element Q4_K block, so the whole model is Q4_K, Q6_K and F32, which is exactly what the Lean spec and the circuit cover. Qwen2.5-0.5B fails that test: its hidden size 896 forces llama.cpp to fall back to Q5_0 for 133 tensors, a format outside the statement, and requantizing does not change that. The existing receipts pipeline accepts the 0.6B unchanged (trace of 12 tokens: 8,450 leaves, 32 openings verified, no unclassified inputs). Fallback: Qwen2.5-1.5B, on which everything so far was validated.

## Budgets

Set from the measurements, to be enforced in Stage 5:

| Budget | Value | Why |
|---|---|---|
| Proof package for one next token | at most 64 MB | Loadable in a browser tab; forces aggregation, since 197 matmul proofs of today's 6.5 MB would be 1.3 GB. |
| Verification, cold, on this laptop | at most 60 s | An audit-grade check, not an interactive one. Direct inference of the same token is 0.03 s, so verification will be about three orders of magnitude slower; the value is that the verifier holds no weights. |
| Registration per model | at most one hour, reproducible | One-off. |

## Unsupported today, per decode graph of Qwen3-0.6B

| Op | Count | Status |
|---|---|---|
| MUL_MAT, Q4_K weight | 168 of 197 | Integer core proven per node; float scales outside the circuit. |
| MUL_MAT, Q6_K weight | 29 of 197 | Lean spec has the dot product; no circuit yet. |
| RMS_NORM (with q and k norms) | 113 | Float. Fixed-point execution mode needed. |
| MUL (norm weights, gating) | 113 | Float. |
| ROPE (neox) | 56 | Float, cos and sin tables. |
| SET_ROWS (KV cache writes) | 56 | Copies; f16 rounding of K and V. |
| ADD (residuals) | 56 | Float. |
| FLASH_ATTN_EXT | 28 | Float softmax and two matmuls with f16 KV. |
| SWIGLU | 28 | Float sigmoid. |
| GET_ROWS (embedding) | 3 | Lookup into a Q6_K tensor. |
| Greedy argmax | outside the graph | Lowest token id wins ties, in llama.cpp's sampler and in the receipts tool. |

## Addendum, Sep 13, 2026: the zero-knowledge checkpoint uses Groth16

Stage 3 needs an actual zero-knowledge construction, and Expander does not provide one. Rather than adding masking to Expander's prover, the one-node checkpoint is proven a second way with an established system: a circom circuit (`zk/groth16/qdot_rows.circom`) proven with Groth16 through snarkjs.

- Statement: the same integer core, for a group of weight rows (16 rows for K up to 1536, 8 rows for K = 2048, about 150k constraints per instance, so a setup takes minutes on the laptop; a 64-row instance of 890k constraints was compiled too, and its setup did not finish in the memory this machine had left). The weights enter as bits, so every nibble and six-bit field is in range by construction. A Poseidon chain over the packed weights and a salt is the public commitment; the activation quants and per-block sums are public inputs.
- Registration: `register.py --groth16` publishes one Poseidon commitment per row group per Q4_K tensor (Qwen3-0.6B: 168 tensors, 22,400 groups, four circuit shapes: `r16_k1024`, `r8_k2048`, `r8_k3072`, plus `r16_k1536` for the 1.5B demo node), computed in Node with circomlibjs by the same chain the circuit uses; `groth16_node.py` and the site compare the proof's commitment with the registered one.
- Zero knowledge: Groth16 proofs are randomized and reveal nothing about the witness beyond the public inputs. Proofs are about 800 bytes and verify in a browser with `snarkjs.groth16.verify` (190 ms measured in Chrome for the test instance).
- Parameters: the public Hermez powers-of-tau mirrors returned 403 on the day, so a 2^18 powers of tau was generated locally and the phase 2 has one contributor. These are proof-of-concept parameters; a deployment takes a public ceremony's file and a multi-party phase 2, with no code change.
- Cost: the one-row test instance has 9,624 quadratic constraints and proves in about one second; the 16-row instance has 152,148 quadratic and 70,427 linear constraints and proves a group in about 3 s (0.16 s to verify, 805-byte proof); the 64-row instance, 608,592 and 281,704, compiled but its setup did not fit the memory left on the machine. A 256-row node is 16 groups, 67 s of proving. Details in `../stage5/report.md`.
- Where this leaves Expander: the fast prover for the non-zero-knowledge, model-bound proof, and the candidate for whole-token proving if masking is added. Groth16 does not scale to a whole token on a laptop (about 200 nodes at 2^20 constraints each), so Stage 4 still depends on either masking in a GKR prover or recursive aggregation of per-node proofs.
