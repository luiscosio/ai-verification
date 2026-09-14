# TODO

Scratch pad for the ZK inference PoC. `PLAN.md` holds the plan and its gates; this file holds what exists, what is missing, and the decisions still open. Updated Sep 13, 2026.

## Implemented components (not completed stage gates)

### Stage 1, freeze the statement and evaluate backends
- [x] Backend decision record: Expander has no zero-knowledge layer and no hiding commitment; DeepProve and EZKL run their own arithmetic. `docs/stage1/backend-decision.md`
- [x] Statement stmt/v0 frozen, with the float and field decisions (BN254 for whole-token circuits, Mersenne-31 for exact integer cores). `docs/stage1/statement.md`
- [x] Activation ranges of three models measured from fully opened traces. `docs/stage1/ranges-*.json`, `docs/stage1/trace_stats.py`
- [x] First model: Qwen3-0.6B requantized to Q4_K_M (all matmul dimensions multiples of 256). Qwen2.5-0.5B rejected (896 forces Q5_0 fallbacks). `models/`, digests in the record
- [ ] Adopt resource budgets explicitly. The plan retains provisional 50 MiB / 10 s limits; the 64 MB / 60 s values in the earlier decision record are proposals, not accepted limits.
- [x] Circuit checked against the Lean spec on the same vectors. `spec-check vectors --emit`, `zk/diff_spec.py`

### Stage 2, registration
- [x] `zk/register.py`: manifest with digests, tensor table, tokenizer identity, execution specification, proof-system identity, id over the canonical JSON; `--check` validates schema, complete tensor mapping, GGUF metadata and installed key/circuit/verifier identities; commitments are recomputed only with the named flags; `--augment` resumes
- [x] Orion commitment per Q4_K tensor through `receipts-zk commit-many` (one circuit compile per shape, about three minutes for the model)
- [x] Poseidon commitment per row group for the Groth16 circuit (`--groth16`), 22,400 groups
- [x] Qwen3-0.6B registered: `registry/qwen3-0.6b-q4_k_m/manifest.json`, 168 Q4_K tensors, both schemes; registration/v1 adds verification material digests and changes the manifest ID
- [x] Verification keys and circuit instantiations published in `registry/circuits/`, with the parameters' digest and the zkey digests

### Stage 3, one operation with private weights
- [x] Expander: weights private, bound to a registered Orion commitment; verifier holds no weights; not zero-knowledge. `receipts-zk commit|prove|verify --commitment`, `zk_node.py --manifest`
- [x] Groth16 (zero-knowledge): circom circuit for a row group, weights as private bits, Poseidon commitment public. 16 rows for K up to 1536, 8 for K = 2048 and 3072. `zk/groth16/`
- [x] Measured: about 3 s to prove a group, 0.16 s to verify, 805-byte proof; 256-row demo node as 16 groups in 67 s; registered Qwen3 tensors of all three shapes proven and verified against the manifest
- [x] Negatives: tampered sum, other group's commitment, other weights, other circuit's key, non-boolean weight bits and out-of-range public activations (including a valid pairing for an invalid activation)

- [x] Separate F20 complete-operation research claim: all 1,024 rows, constrained activation quantization/scales/accumulation/rounding and private boundary commitments. Actual 65-proof package, independent offline verifier, rejection tests and measurements in `research/complete-operation/`. Native semantics and independent cryptographic review remain open.

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
- [ ] Retire the old private Claude verifier artifact. It is stale and no longer recommended; remote removal/replacement is blocked on a signed-in owner session. AgentMetal is the single hosting target; its quota increase is pending.
- [x] Retire automatic Pages publishing; preserve all verification jobs on main pushes.
- [ ] Complete AgentMetal deployment after the server quota increase, validate the live service, then unpublish the existing Pages site.
- [x] Searchable catalogue: Qwen3-0.6B registered integer cores, Qwen2.5-1.5B one registered tensor, Qwen2.5-0.5B fingerprint-only identity. Coverage is explicit on each card.

### Proof workspace, alongside the research stages
- [x] Local generation interface, actual stage progress, cancellation, prerequisite messages and one-file export; `start-workspace.sh` and `site/local_prover.py`.
- [x] Browser and offline verification of the same versioned file; automatic trusted-registry lookup; exact coverage and separate failure states.
- [x] Expandable model/research details and local run measurements; no prompt/answer fields in the row-group package.
- [x] First-time setup with locked dependencies, native build, authenticated exact model download and checksum-pinned matching proving materials; clean Linux CI also exercises generation and fresh proofs: `setup-workspace.sh`, `releases/prover-materials-v1.json`.
- [x] Local installation and generation/verification tests; research experiment exports include phase timing, process RSS, exact source/material digests and public proof fixtures.
- [ ] Three-person usability study deferred by the owner for this iteration; local tests are being used. This is not evidence of user comprehension. See `docs/ux-plan.md`.
- [x] First GitHub Pages deployment passed after the fork release and parent submodule-pin update. A real local proof passed on the hosted page (77 ms), and the adversarial example was rejected. The older private artifact is historical.

### Around the plan
- [x] Receipt 0.2 / trace v2 hardening after the security review (topology digest, opening policy, content commitments, per-token records); Lean canonical JSON fix; clean version rejection. `notes/session-notes-2026-09-12.md`
- [x] Demo: `run-demo.sh`, eight steps in about 47 s, ending with the zero-knowledge proof of a row group
- [x] Fork `luiscosio/llama.cpp`: three draft PRs rebased on upstream master, integration branch `receipts-all`; nothing sent to ggml-org
- [x] Deck regenerated: `docs/llama-receipts-activation-trace-secure-v2.pptx`
- [x] Public repository `luiscosio/ai-verification` (MIT), the llama.cpp fork as a submodule pinned to `receipts-all`; models, demo output and the built site untracked. The Signal group material and the unredacted Sep 10 note live outside the repository, in `~/Projects/ai-verification-signal-chat/`.

## Missing, in the order that unblocks the most

The usability work in `docs/ux-plan.md` proceeds alongside this cryptographic dependency order. An experimental preview can improve now; production assurance remains subject to the gates below.

1. [ ] **Real parameters, after circuit/interface stabilization.** Replace the locally generated 2^18 powers of tau and the single-contributor phase 2 with a public ceremony's file and a multi-party phase 2 (snarkjs supports both as-is). Until then a prover who ran the setup could forge, and every Stage 5 result is an implementation test. Then re-run `groth16_node.py` and `verify_isolated.sh`, republish the site.
2. [ ] **Second registrar.** Someone else runs `register.py --check --commit --groth16` against their own copy of the GGUF and signs the manifest; publish Expander's commitment parameters explicitly instead of its testing-only RNG. Stage 2 exit gate.
3. [ ] **Choose the execution track and next backend experiment.** The complete F20 operation is implemented and measured, with conditional private-boundary composition documented. Its Q4-only serial projection is about 28 hours/token, before other required operations. Keep native arithmetic as the default track and F20 as a candidate; obtain independent review and settle budgets before a broad kernel port. A future selected fixed-point track would port `docs/stage4/fixed_point_forward.py` into ggml's CPU backend as a selectable mode: matmul scale step and RMS norm first, measure token agreement after each op, register stmt/v1 when the whole pass is in. Then the trace verifier's tolerances become exact equalities.
4. [ ] **Whole-token prover spike.** Two one-week spikes: Libra-style masking on one sumcheck layer in the Expander fork, or a GKR-with-logup system that already has a zero-knowledge mode. Then the Q6_K circuit, the nonlinear ops of stmt/v1, and a specified, reviewed hiding-boundary composition. The Stage 4 sketches are not a soundness argument.
5. [ ] **Production-assurance website**, after item 1: reviewed setup, independent registration, prover signatures and a versioned verifier release. The website verifies Groth16 locally in the browser and stores no proof uploads. Expander server deployment, if added, needs deployment-level upload/rate limits and explicit labeling.
6. [x] Publish the existing matching prover material as `prover-materials-v1` GitHub release assets; full checksums and byte sizes are in `releases/prover-materials-v1.json`.
7. [ ] Extend Qwen2.5-1.5B beyond its registered `blk.0.ffn_gate.weight` checkpoint, and integrate supported registrations into the local model picker.
8. [ ] Cache compiled circuits per shape in `receipts-zk verify` (2 to 5 s per verification today).
9. [ ] Add the Groth16 circuit to the Lean differential harness; prove in Lean that the circuit's `s1`, `s2` are the spec's.
10. [ ] Remaining trace work: make the Lean checker's minimum openings a flag like Python's; derive the expected topology from the GGUF architecture instead of a pinned digest. Native replay and Python trace verification now check token/text correspondence through the native vocabulary loader.
11. [ ] Lean: the `(1 - f)^k` sampling bound with a probability model; general audit-path completeness.

## Review repairs, 2026-09-13

- [x] Shared browser/offline range, shape and pinned-key checks; plain-text result rendering.
- [x] Registration/v1 schema and GGUF mapping validation; independent commitment-check limits.
- [x] Native receipt version, tokenization and detokenization checks; Python trace integration.
- [x] Registry-only site key lookup, fresh demo outputs and mandatory failure propagation.
- [x] Async verifier process, bounded concurrency, input validation and cleanup on timeout/cancellation.
- [x] Signed-maximum Q8 convention and explicit F20 corpus runner.
- [x] Isolation controls require permission-denial evidence and determine success.
- [x] Repeatable regression command: `checks/run.sh`.

Those repairs did not add full-operation coverage. The later separate F20 experiment adds one complete operation and private activation commitments; it does not add a full-token proof or production setup.

## Testing and measurements, 2026-09-13

- [x] Four-model/12-prompt native matrix (208 attempts); fixed four partial-UTF-8 receipt failures and passed 60 post-fix cases, 52 replays and 38 byte-boundary checks.
- [x] Sustained throughput at two/eight threads, 40 configurations and 120 samples; CPU time, process RSS, complete runner RSS and trace size measured.
- [x] Both registered proof models and all four circuit widths: 18 exported proofs accepted; three complete F20 operation packages containing 195 component proofs accepted.
- [x] 3,000 proof mutation attempts rejected with 120 honest recovery checks; native negative controls, actual circuit witnesses, timeout cleanup and isolated verification exercised.
- [x] Seven CI check jobs gate deployment: Linux/macOS × Node 22/24, native generation/API/proofs, circuit boundaries and 40 browser scenarios across four browser configurations.
- [x] Results, preserved failures, public proof fixtures and reproducible measurements: [testing report](benchmarks/results/2026-09-13/README.md).
- [ ] Reduce full-trace capture cost; measured Qwen3 traces reach 1.5 GiB and the runner reaches 6.22 GiB summed RSS.
- [ ] Run longer repeated-verification memory soaks and clean CPU/GPU baselines before adopting performance budgets.

## Decisions that are yours

- Which ceremony's parameters, and who contributes to phase 2.
- Who the second registrar is.
- Whether and when the site goes public, and under what name.
- Whether anything goes upstream to ggml-org, which needs an issue first, human-written PR text, and an AI-use disclosure.
- Whether the first public model stays Qwen3-0.6B or moves to the 1.5B.

## Notes for whoever runs this

- The laptop has 24 GB with about 12 GB of swap held by other applications; the harness killed every background job twice for memory. Run one heavy job at a time. The 64-row Groth16 instance compiled but its setup never fit; 16-row groups are the working size.
- `code/llama.cpp/examples/receipts/zk/groth16/build/` and `ptau/` are not tracked; install the matching existing files with `./setup-workspace.sh --all-circuits --include-setup`. Rebuilding setup produces different keys and requires a new registration. `pot18_final.ptau` is the file in use.
- Model files in `models/` are not tracked; digests are in `docs/stage1/backend-decision.md`.
