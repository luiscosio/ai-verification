# TODO

Scratch pad for the ZK inference PoC. `PLAN.md` holds the plan and its gates; this file holds what exists, what is missing, and the decisions still open. Updated Sep 13, 2026.

## Done

### Stage 1, freeze the statement and evaluate backends
- [x] Backend decision record: Expander has no zero-knowledge layer and no hiding commitment; DeepProve and EZKL run their own arithmetic. `docs/stage1/backend-decision.md`
- [x] Statement stmt/v0 frozen, with the float and field decisions (BN254 for whole-token circuits, Mersenne-31 for exact integer cores). `docs/stage1/statement.md`
- [x] Activation ranges of three models measured from fully opened traces. `docs/stage1/ranges-*.json`, `docs/stage1/trace_stats.py`
- [x] First model: Qwen3-0.6B requantized to Q4_K_M (all matmul dimensions multiples of 256). Qwen2.5-0.5B rejected (896 forces Q5_0 fallbacks). `models/`, digests in the record
- [x] Budgets: 64 MB per next-token proof, 60 s cold verification
- [x] Circuit checked against the Lean spec on the same vectors. `spec-check vectors --emit`, `zk/diff_spec.py`

### Stage 2, registration
- [x] `zk/register.py`: manifest with digests, tensor table, tokenizer identity, execution specification, proof-system identity, id over the canonical JSON; `--check` recomputes and names what differs; `--augment` resumes
- [x] Orion commitment per Q4_K tensor through `receipts-zk commit-many` (one circuit compile per shape, about three minutes for the model)
- [x] Poseidon commitment per row group for the Groth16 circuit (`--groth16`), 22,400 groups
- [x] Qwen3-0.6B registered: `registry/qwen3-0.6b-q4_k_m/manifest.json`, 168 Q4_K tensors, both schemes, checked valid
- [x] Verification keys and circuit instantiations published in `registry/circuits/`, with the parameters' digest and the zkey digests

### Stage 3, one operation with private weights
- [x] Expander: weights private, bound to a registered Orion commitment; verifier holds no weights; not zero-knowledge. `receipts-zk commit|prove|verify --commitment`, `zk_node.py --manifest`
- [x] Groth16 (zero-knowledge): circom circuit for a row group, weights as private bits, Poseidon commitment public. 16 rows for K up to 1536, 8 for K = 2048 and 3072. `zk/groth16/`
- [x] Measured: about 3 s to prove a group, 0.16 s to verify, 805-byte proof; 256-row demo node as 16 groups in 67 s; registered Qwen3 tensors of all three shapes proven and verified against the manifest
- [x] Negatives: tampered sum, other group's commitment, other weights, other circuit's key, out-of-range witness

### Stage 4, one full next-token computation
- [x] Circuit-friendly execution mode as a reference implementation: integer-only forward pass of Qwen3-0.6B. `docs/stage4/fixed_point_forward.py`
- [x] Agreement with llama.cpp's greedy token: 19 of 20 prompts at 16 fraction bits, 20 of 20 at 20 bits (stmt/v1 choice). `docs/stage4/agreement-*.json`
- [x] Bit widths per op and the whole-token cost: 322 million weight nibbles per token, 1.6 billion R1CS constraints or 320 million multiplications with lookups. `docs/stage4/report.md`

### Stage 5, isolation and adversarial cases
- [x] `docs/stage5/verify_isolated.sh`: fresh directory, sandbox with no network and unreadable model files, two controls per run
- [x] Production package accepted in 0.1 s; wrong group, tampered sum, foreign key, different weights, malformed and oversized packages rejected. `docs/stage5/report.md`

### Stage 6, registry and verification site
- [x] `site/`: static page with the registered models, in-browser Groth16 verification against the pinned manifest, coverage stated on every result, offline reproduction commands, bundled honest and tampered packages, self-check on load
- [x] `site/serve.py`: local server, server-side verification of Expander packages with size and time limits; accepted a Qwen3 proof, rejected a tampered one
- [x] Published as a private artifact: https://claude.ai/code/artifact/687d9b99-421b-4075-a9e2-8ea32dcdccbe

### Around the plan
- [x] Receipt 0.2 / trace v2 hardening after the security review (topology digest, opening policy, content commitments, per-token records); Lean canonical JSON fix; clean version rejection. `notes/session-notes-2026-09-12.md`
- [x] Demo: `run-demo.sh`, eight steps in about 47 s, ending with the zero-knowledge proof of a row group
- [x] Fork `luiscosio/llama.cpp`: three draft PRs rebased on upstream master, integration branch `receipts-all`; nothing sent to ggml-org
- [x] Deck regenerated: `docs/llama-receipts-activation-trace-secure-v2.pptx`
- [x] Public repository `luiscosio/ai-verification` (MIT), the llama.cpp fork as a submodule pinned to `receipts-all`; models, demo output and the built site untracked. The Signal group material and the unredacted Sep 10 note live outside the repository, in `~/Projects/ai-verification-signal-chat/`.

## Missing, in the order that unblocks the most

1. [ ] **Real parameters.** Replace the locally generated 2^18 powers of tau and the single-contributor phase 2 with a public ceremony's file and a multi-party phase 2 (snarkjs supports both as-is). Until then a prover who ran the setup could forge, and every Stage 5 result is an implementation test. Then re-run `groth16_node.py` and `verify_isolated.sh`, republish the site.
2. [ ] **Second registrar.** Someone else runs `register.py --check --commit --groth16` against their own copy of the GGUF and signs the manifest; publish Expander's commitment parameters explicitly instead of its testing-only RNG. Stage 2 exit gate.
3. [ ] **Fixed-point mode in llama.cpp.** Port `docs/stage4/fixed_point_forward.py` into ggml's CPU backend as a selectable mode: matmul scale step and RMS norm first, measure token agreement after each op, register stmt/v1 when the whole pass is in. Then the trace verifier's tolerances become exact equalities.
4. [ ] **Whole-token prover spike.** Two one-week spikes: Libra-style masking on one sumcheck layer in the Expander fork, or a GKR-with-logup system that already has a zero-knowledge mode. Then the Q6_K circuit, the nonlinear ops of stmt/v1, and the boundary-commitment linking from `docs/stage4/report.md`.
5. [ ] **Public site**, after item 1: request queueing and rate limits on the Expander endpoint, prover signatures on packages, an explicit consent step before an uploaded prompt is shown, downloadable manifests and a versioned verifier release. Expander proofs stay server-side (no MPI-free WASM build exists) and the page must say so.
6. [ ] Publish the prover material (zkeys, 78 to 108 MB each, and `pot18_final.ptau`) as GitHub release assets of `luiscosio/ai-verification`; their digests are in `registry/circuits/README.md`.
7. [ ] Register Qwen2.5-1.5B too, so the demo node's proofs appear on the site.
8. [ ] Cache compiled circuits per shape in `receipts-zk verify` (2 to 5 s per verification today).
9. [ ] Add the Groth16 circuit to the Lean differential harness; prove in Lean that the circuit's `s1`, `s2` are the spec's.
10. [ ] Trace verifier gaps left from the review: detokenize `response.tokens` with the GGUF vocabulary and compare with `response.text`; make the Lean checker's minimum openings a flag like Python's; derive the expected topology from the GGUF architecture instead of a pinned digest.
11. [ ] Lean: the `(1 - f)^k` sampling bound with a probability model; general audit-path completeness.

## Decisions that are yours

- Which ceremony's parameters, and who contributes to phase 2.
- Who the second registrar is.
- Whether and when the site goes public, and under what name.
- Whether anything goes upstream to ggml-org, which needs an issue first, human-written PR text, and an AI-use disclosure.
- Whether the first public model stays Qwen3-0.6B or moves to the 1.5B.

## Notes for whoever runs this

- The laptop has 24 GB with about 12 GB of swap held by other applications; the harness killed every background job twice for memory. Run one heavy job at a time. The 64-row Groth16 instance compiled but its setup never fit; 16-row groups are the working size.
- `code/llama.cpp/examples/receipts/zk/groth16/build/` and `ptau/` are not tracked; rebuild with `circom`, `setup.sh` and the README's commands. `pot18_final.ptau` is the file in use.
- Model files in `models/` are not tracked; digests are in `docs/stage1/backend-decision.md`.
