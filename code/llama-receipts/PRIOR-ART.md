# Prior art for llama-receipts (checked Sep 10 and 11, 2026)

Two sweeps: llama.cpp, ggml, llama-cpp-python, and Ollama themselves; and the wider field of receipts, replayable sampling, and recompute verification. This is verification by re-execution with a trusted reference. It is not zero-knowledge: the verifier holds the weights and learns everything.

## In llama.cpp, ggml, llama-cpp-python, Ollama

Nothing merged implements receipts, hash-derived sampling draws, a replay verifier, or logits hashing.

| Item | Where | What it is | Status |
|---|---|---|---|
| Draft PR "feat/verifiable inference" | ggml-org/llama.cpp #21560 (Apr 7, 2026) | Uses `cb_eval` to SHA-256 every GGML node output, Merkle root, reservoir-sampled openings; server `proof` field; a Python script recomputes the root. No token or seed receipt, no signing, no re-run | unmerged, 0 comments |
| `--attest` quantization provenance | llama.cpp #21261 | JSON attestation of source and output GGUF hashes at quantize time | closed, not built |
| Release artifact attestation | llama.cpp #25933, #27389 | GitHub build attestation for release binaries | merged Aug 2026, binaries only |
| `examples/eval-callback` | llama.cpp tree | Prints every tensor via `cb_eval`; no hashing | the hook rung 4 would use |
| Determinism bugs | llama.cpp #2838, #22224, discussions #12167, #2100 | Same seed differs across CUDA batch sizes, hardware, OS | open; matches our H2/H3 findings |
| Model signing | ollama #11573, #11526 | ed25519 signatures on model manifests | open since Jul 2025 |
| README link to INVAR | ollama #18268 (Sep 6, 2026) | External proxy, see below | open |

llama.cpp's sampler draws one `std::uniform_real_distribution` value per token from a `std::mt19937` seeded once; the default seed is `std::random_device`. GPU backend sampling pre-draws uniforms from the same stream. Nothing hashes (seed, position). Reproducing draws therefore requires the same libstdc++ or libc++ and the same number of RNG calls, which is why we sample outside the engine.

## Closest external systems

| System | Engine | Receipts | Hash-derived draws | Recompute | Tolerance metric | Two regimes | Adversarial suite |
|---|---|---|---|---|---|---|---|
| INVAR (anomly-labs/invar, Aug to Sep 2026) | Ollama, llama.cpp | yes: binary, manifest and GGUF digests, decode params, cert chain, hash-chained log | no | yes: re-asks Ollama, compares digests; "exact" profile via a llama.cpp fork with logits dump and spot-check | no | standard vs exact profiles | no |
| holo.cpp (Aug 2026) | llama.cpp fork (Tether qvac) | hashed, not signed: engine hash, model address, token ids, sampler and seed | no | yes: re-runs with `llama_sampler_init_dist(seed)`, diffs tokens | no | no | no |
| xyntetik-runner (Jul to Sep 2026) | own C engine reading GGUF | yes: Ed25519 and ML-DSA-44 signed, chained transcripts, seed, token ids | no | yes: VERIFIED, DIVERGED, UNVERIFIABLE | no | determinism tiers | no |
| EigenAI (arXiv 2602.00182, Jan 2026) | llama.cpp | yes: request and output hashes, container digest, GPU arch, driver, decode policy, seed, optional per-step logits | no | yes: byte-equality in a TEE | none, strict only | strict only | no |
| CommitLLM (lambdaclass, Mar to Jun 2026) | custom Rust plus Python sidecar | yes: checkpoint and quant, decode policy, precommitted randomness, captured logits, Merkle trace | partial | partial: Freivalds plus exact CPU replay | no | no | yes: 36 tamper scenarios |
| Lockstep (ptoggle/lockstep, Sep 10, 2026) | vLLM plugin plus CPU reference | partial: manifest, logprob bit patterns | no | yes | none, bit equality | strict only | negative controls |
| Rinberg et al. (arXiv 2511.02620, Nov 2025) | vLLM | no, logs only | in the paper's algorithms as `H(seed, i)`; the code uses a torch PRNG stream | yes | yes: Gumbel forgiveness; the IPT variant integrates over the token's CDF interval, the statistical cousin of our draw gap | no | steganographic exfiltration |
| DiFR / Token-DiFR (arXiv 2511.20621) | vLLM, HF | no, "tokens are the evidence" | seed-synced torch generator | yes | yes: clipped post-Gumbel logit margin with calibrated threshold | tolerant only | quantization, FP8 KV, temperature, wrong seed, sampling bug |
| Amodo Inference-Recomputation-Prototype (Sep 8, 2026) | vLLM | ledger, signing unverified | no | yes, async | DiFR margins with per-model thresholds | had to pin the vLLM runner so samplers matched | append attacks |
| Cankaya bit-exact (arXiv 2606.00279) | vLLM, HF | no | no | yes, via CPU emulation of GPU rounding | none, exact | strict side only | steganography, hidden batch elements |
| servseal (Sep 2026) | HF | no | no | distribution sketches | Hellinger distance, calibrated | no | quantization, substitution, top-p, template bug |
| A3S Power, ashaveri, Phala ACI, Tinfoil | TEE gateways | partial, attestation-bound | no | no | no | no | no |

Adjacent ideas: Aaronson and Kirchner's Gumbel watermark and SynthID derive sampling randomness from a hash of prior tokens; "Seed Hijacking" (arXiv 2605.08313) and "Integer Alibi" (arXiv 2608.13756) study seed tampering and kernel flips.

## What is and isn't new here

Every ingredient exists somewhere. Signed receipts with model hash, seed, and decode policy exist (EigenAI, xyntetik-runner, INVAR, CommitLLM), paired with byte-equality replay. Tolerant recompute with a per-token draw metric exists (Rinberg, Token-DiFR, Amodo), with no signatures, no logits hashes, and a PRNG stream instead of hash(seed, position).

The combination is what we did not find elsewhere: per-position logits hashes inside a signed receipt driving a two-regime decision (strict when the arithmetic is bit-identical, tolerant when it isn't), stateless hash-derived draws that make the draw gap exact instead of statistical, and an attack matrix that includes the honest cross-backend case as a calibration control. The draw gap itself is a deterministic version of Rinberg's interval integration, not a new idea.

Correct name for this class: recomputation-based inference verification with a trusted, weights-holding verifier. Not zero-knowledge, not TEE attestation.

Unverified: whether Amodo's ledger is signed, EigenAI's code, IMMACULATE's code link, Gonka's seed-reveal validation. GitHub code search is partial; private forks could exist.

## Rung 4: committed activation traces with sampled openings (checked Sep 11, 2026)

| System | Commits to | Openings | Verifier does | Inputs bound to tokens | Edges checked |
|---|---|---|---|---|---|
| llama.cpp draft PR 21560 "feat/verifiable inference" (Apr 7, 2026, unmerged, 0 comments) | SHA-256 of every GGML node output via `cb_eval`, Merkle root, in callback order | reservoir sample chosen by the prover | recomputes the root from opened entries | no | no |
| Anchuri, Campanelli, Gennaro et al., "Lightweight Cryptographic Proofs of Inference" (SaTML '26, arXiv 2603.19025) | per-layer activations, Merkle committed | random layers | recomputes the opened layers from opened inputs; probabilistic soundness argument | yes (layer inputs) | by construction at layer granularity |
| CommitLLM (lambdaclass) | Merkle trace of captured logits and checkpoints | full | Freivalds check on matmuls plus exact CPU replay | yes | partial |
| Cankaya (MIRI) system overview | taps that capture and commit; air-gapped recompute of random challenges | random | recompute | yes | design only |
| This repo, rung 4 | every computing GGML node, with the base-tensor hash of every input and a `producer` link; layout ops resolved | Fiat-Shamir from the signed root and receipt, or a verifier seed | all edges, all graph inputs regenerated from the claimed tokens, logits bound to the receipt, then re-executes each opening against three arithmetic references including ggml's Q8_K integer path | yes (tokens, positions, out ids, KV cells, mask) | every edge, hash equality |

What the draft PR and this rung share: the hook (`cb_eval`), SHA-256 per node, one Merkle root, sampled openings. What differs: the PR's leaves are output hashes only and its verifier checks membership; here each leaf names its inputs by hash and producer, so the committed object is a consistent computation graph, the openings are re-executed rather than only located in the tree, weights are bound by name to the GGUF commitment instead of being hashed from GPU memory, and graph inputs are regenerated from the receipt. The soundness shape is Anchuri et al.'s (a dense cheat is caught with probability 1 - (1 - f)^k), at node granularity and on the engine's real kernels rather than a reference implementation.

The integer reference in `receipts/qdot.py` mirrors `quantize_row_q8_K_ref` and `ggml_vec_dot_{q4,q6}_K_q8_K_generic` from ggml. No published zkML system found here proves llama.cpp's block-quantized arithmetic natively: DeepProve ingests GGUF but dequantizes to float32 and requantizes into its own fixed-point scheme (`zkml/src/parser/gguf.rs`), so its proofs describe a different forward pass than the one llama.cpp runs.
