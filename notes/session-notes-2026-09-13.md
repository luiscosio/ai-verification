# Session notes, Sep 13, 2026: Stage 1 of the ZK plan, and weights bound to a registered commitment

The plan (now `PLAN.md`; progress in `TODO.md`) was reviewed, amended with zero knowledge kept as a hard requirement, and its Stage 1 executed to the exit gate. Deliverables in `docs/stage1/`.

## What was established

- **Expander has no zero-knowledge layer.** Its `sumcheck`, `gkr` and `gkr_engine` crates contain no masking; the Polyhedra texts that call it a ZK system cite Libra's technique, which is not in the code. Its commitments (Orion, Hyrax, KZG) bind but do not hide, and their parameters come from a testing-only fixed RNG. DeepProve runs its own 12-bit quantization under a proprietary licence and does not claim hiding. EZKL is zero-knowledge but runs its own fixed point. Verdict: Expander stays as the arithmetization and prover, the ZK layer is the missing engineering (masking, blinded Hyrax over BN254, published parameters).
- **Activation ranges.** Fully opened one-token traces of three models: activations reach about 6,000, so 14 signed integer bits; fixed-point products and 3072-term sums need about 72 bits. Field decision: BN254 for whole-token circuits, Mersenne-31 kept for the exact integer-core checkpoints.
- **First model.** Qwen2.5-0.5B is out: its hidden size 896 is not a multiple of the Q4_K block, so llama.cpp falls back to Q5_0 for 133 tensors even when we quantize it ourselves. Qwen3-0.6B (1024, 2048, 3072) requantized by us to Q4_K_M is all Q4_K, Q6_K and F32, verifies with the receipts pipeline unchanged, and generates a token in 0.03 s. Digests in the record. The bf16 source came from `unsloth/Qwen3-0.6B-GGUF`; Qwen's own repo only ships Q8_0.
- **Budgets.** 64 MB per next-token proof, 60 s cold verification on the M5. Today's 6.5 MB per node times 197 matmuls would be 1.3 GB, so aggregation is forced.
- **Greedy tie-break.** llama.cpp's sampler and the receipts tool both take the lowest token id among equal logits.

## What was built

- `spec-check vectors --emit` writes what the Lean spec computed; `zk/diff_spec.py` feeds those sums to the circuit. Three rows accepted, one-off changes rejected: the circuit is now checked against the specification, not against Python.
- The weights are private inputs again, and bound: `receipts-zk commit` computes Orion's commitment to the circuit's private input layer from the weights alone (registration), the prover's proof carries the same commitment as its first item after the public inputs, and `receipts-zk verify --commitment` refuses a mismatch before any sumcheck. `zk_node.py` runs register, prove, verify and three negatives: tampered sum, a proof from one changed nibble with consistent sums (different commitment), the honest proof against the next layer's registration. All rejected; proof back to 6.5 MB, verify 0.04 s. The verifier holds no weights.
- `docs/stage1/trace_stats.py`: per-op inventory and value ranges from a fully opened trace.
- Deck: proof slide back to private weights with the commitment, roadmap slide now shows the plan's stages.

## Open

- Zero knowledge itself: nothing in the stack hides the weights or the witness yet. Stage 3.
- Expander's commitment parameters are "testing only"; a registration must ship them explicitly.
- The fixed-point execution mode for the float ops does not exist; the statement names it as stmt/v1.
- Q6_K matmuls (29 per graph in Qwen3-0.6B) have a Lean definition and no circuit.

## Later: Stage 2 started

- `zk/register.py` builds the registration manifest the plan's Stage 2 asks for and checks one against another copy of the GGUF. Tested on Qwen3-0.6B: valid against the file, and one flipped bit near the end of the file is reported both as the file digest and as `blk.27.ffn_up.weight`. Each Q4_K commitment takes 7 to 15 s (the circuit compile dominates), so the full registration of 168 tensors runs about half an hour.
- `zk_node.py --manifest` takes the registered commitment from the manifest instead of computing it, which is the real verifier flow: pin the manifest, never compute from weights.
- First registration: `registry/qwen3-0.6b-q4_k_m/manifest.json`.

## Later: Stages 3 to 6, on instruction to finish the plan

- **Zero knowledge, for real, with Groth16.** Expander cannot give it, so the same one-node statement was written as a circom circuit (`zk/groth16/qdot_rows.circom`): a group of weight rows as private bits, a Poseidon chain over the packed weights and a salt as the public commitment, the activation quants and per-block sums public. Groth16 through snarkjs. The one-row test instance proves in about a second; the production instances use 16-row groups (152,148 quadratic constraints) after a 64-row instance's setup was killed for memory 40 minutes in. Both public Hermez mirrors of the powers of tau returned 403, so the parameters were generated locally: proof-of-concept, one phase-2 contributor. Proofs are 805 bytes and verify in a browser in about 200 ms.
- **Registration carries both schemes.** `register.py --groth16` adds one Poseidon commitment per row group (16 rows for K up to 1536, 8 rows for K = 2048), computed in Node with circomlibjs by the same chain the circuit uses; `--check --groth16` recomputes them.
- **Isolation (Stage 5).** `docs/stage5/verify_isolated.sh` copies the verification key, manifest and package into a fresh directory and runs the check under `sandbox-exec` with no network and the model directories unreadable, with two controls proving the sandbox bites. Honest accepted; tampered sum, wrong group, foreign verification key, different weights all rejected.
- **Stage 4 measured.** `docs/stage4/fixed_point_forward.py` runs Qwen3-0.6B's whole next-token forward pass in integer arithmetic (16 fraction bits, Q8_K quantization and the integer cores exactly as ggml, integer square root, table exponential). At 16 fraction bits it matches llama.cpp's greedy token on 19 of 20 prompts; the miss is a pair llama.cpp had at 0.49 versus 0.33 that the mode moved by half a logit. At 20 fraction bits, 20 of 20; that is the stmt/v1 choice. Activations stay under 29 bits. A whole token is 322 million weight nibbles, so 1.6 billion R1CS constraints or 320 million multiplications with lookups: per-node Groth16 cannot scale to it, a GKR with lookups and masking can.
- **Site (Stage 6).** `site/template.html` and `build_site.py` produce a static page: registered models from `registry/`, a verify form (proof.json and public.json for one row group), in-page Groth16 verification with the registered circuit's key, the proof's commitment compared with the manifest, the coverage stated on every result, offline reproduction commands, and bundled example packages including a tampered one. It verifies the first bundled package on load and says so at the top. `serve.py` adds server-side verification of Expander packages with size and time limits. Published as a private claude.ai artifact; the self-check on load runs in about half a second there.
- **Machine load.** The Orion registration (one circuit compile per tensor), the snarkjs setups and the fixed-point reference ran at the same time on a 10-core, 24 GB laptop with 12 GB of swap held by other applications; load averages passed 150 and the harness killed every background job for memory, including a 64-row setup 40 minutes in. Two fixes: 16-row groups (a setup takes 36 s instead of an hour) and `receipts-zk commit-many`, one circuit compile per shape, which registers all 168 tensors in about a minute instead of well over an hour. Everything heavy now runs one job at a time.
- **Production numbers.** A 16-row group proves in about 3 s and verifies in 0.16 s (805-byte proof); the whole 256-row demo node took 67 s as 16 groups; registered Qwen3-0.6B tensors of all three shapes (K = 1024, 2048, 3072) prove and verify against the manifest; the isolated check accepts a production package in 0.1 s and rejects the wrong group, a tampered sum and a foreign key.
