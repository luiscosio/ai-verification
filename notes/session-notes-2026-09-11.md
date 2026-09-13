# Session notes, Sep 11, 2026

Question of the day: how is the ZK proof implementation for llama.cpp? Answer: there isn't one, here or anywhere public. What existed in `llama-receipts/` was rungs 1 to 3 (signed receipts, recompute verification, attack matrix). The one upstream artifact, llama.cpp draft PR 21560 from April, hashes GGML node outputs into a Merkle root and checks membership of opened entries; it has no re-execution, no signing, no comments, and no activity since it opened. DeepProve reads GGUF but dequantizes to float32 and requantizes into its own scheme, so its proofs describe a different forward pass than llama.cpp's.

Then: "Build it." Built rung 4.

## What was built: rung 4, Merkle-committed activation trace with sampled openings

In `llama-receipts/`, wired into the existing prover and verifier. `receipts/ggml.py`, `trace.py`, `ops.py`, `qdot.py`, `verify_trace.py`, plus `testset/run_trace_matrix.py`. 40 unit tests, ruff clean.

- **Prover.** Hooks llama.cpp's `cb_eval` from Python through llama-cpp-python's ctypes bindings (no C changes, no fork). Every computing GGML node becomes a leaf: op, params, output shape and hash, and for every input its base-tensor hash plus a link to the leaf that produced it. Layout ops (reshape, view, permute) are resolved to what they view. One Merkle tree per generation; the root is signed in the receipt. Openings for a Fiat-Shamir sample of nodes carry the raw bytes of output and inputs. Two passes: generate and hash, then replay to capture the sampled bytes; the replay must reproduce the root, and it does on both Metal and CPU once the KV cache is zeroed.
- **Verifier, no model execution.** Recomputes the root, recomputes the challenge, checks every data edge (input hash equals producer's output hash), regenerates every graph input from the claimed tokens (tokens, positions, output row ids, K and V cache cell indices including the transposed V layout, causal mask) and compares hashes, ties each decode step's logits hash to the receipt's per-token logits hash, then re-executes each opened node in numpy against a per-op tolerance. Weights are never shipped; the verifier binds them by name and hash to its own GGUF commitment.
- **Arithmetic references.** Matmuls are judged against three: dequantized weight times float32 activation (Metal decode), both operands in half (Metal prefill), and ggml's CPU path, where the activation is quantized to Q8_K and the dot product is integer. The last one, `qdot.py`, mirrors `quantize_row_q8_K_ref` and `ggml_vec_dot_{q4,q6}_K_q8_K` and reproduces gguf-py's dequantization bit for bit in tests. It took CPU weight matmuls from a normalized error of 1e-2 to 4e-2 down to 7e-7, and the matmul limit from 8e-2 to 8e-3. This integer path is the arithmetic a proof system for llama.cpp would need to constrain.

## Numbers (qwen2.5 1.5B Q4_K_M, Apple M5)

- 1,098 GGML nodes per graph, 706 after resolving layout ops; 13 op types in the Qwen2.5 graph.
- Tracing overhead: about 60 microseconds of Python and hashing per node, but observing every node splits the graph into single-node dispatches with a sync each. A traced 32-token generation takes 10 to 12 seconds for both passes, against about a second untraced. Sidecar a few megabytes with compression (the KV cache is mostly zeros).
- Trace-only verification of a 32-token receipt with 32 openings: about 2.5 seconds, dominated by dequantizing the opened weights in numpy. Full replay of the same receipt on Metal: 1.6 seconds. At this model size replay is cheaper; the trace verifier's cost is fixed by the number of openings while replay grows with the model, so the crossover is at models where a forward pass is expensive. What the trace buys here is binding of every intermediate tensor and a verifier without a GPU.
- Rung-4 attack matrix (4 prompts, 32 tokens, 32 openings): 28 of 28 verdicts correct on the seven cases with an expected verdict; the single-node fabrication case (TA9) passed 4 of 4 times, as the sampling bound says it should. The Q2_K attack drives the worst matmul error to 0.23 to 0.40 against at most 2.4e-3 for honest Metal prefill and 9.4e-4 for honest CPU. Calibration table in `llama-receipts/README.md`, matrix in `llama-receipts/testset/results-trace.md`.

## What it catches and what it doesn't

Catches without running the model: cheaper quantization served (every weight matmul re-executes wrong), different model (weight binding fails), hidden system prompt (prefill token input hashes to the wrong tokens), token edits (decode token input or challenge mismatch), forged root. Does not catch: sampler tampering (activations are honest; rung 3 replay does that, and the trace's logits binding hands it the right logits), and a cheat confined to one node with consistent edges, which is caught only if the node or a consumer is sampled. The attack matrix includes that case (TA9) so the bound is on record rather than implied.

## What this is and isn't

Commit-and-open verification with a weights-holding verifier, in the shape of Anchuri et al.'s "Lightweight Cryptographic Proofs of Inference" (SaTML '26) but at GGML node granularity on the engine's real kernels. Not zero-knowledge. The structure is the one a ZK rung would keep: replace "re-execute node j in numpy" with "verify a proof for node j", with the Q8_K integer dot product as the statement. Nobody has that second part for llama.cpp.

## Things learned about llama.cpp on the way

- `Llama.reset()` in llama-cpp-python does not clear KV data for non-recurrent models; stale cells from a previous run leak into hashes of cache views. The engine now clears the cache on reset.
- The embedding lookup runs on the CPU even with every layer on Metal; the scheduler's backend copy shows up as an input named `MTL0#embd#0`, linked to its producer by hash equality.
- ggml's Metal `mul_mm` kernels (prefill) round both operands to half; the decode `mul_mv` kernels use float32 activations. The CPU's f16 dot for the KV cache accumulates in half on ARM. These three are where the remaining re-execution error comes from.
- Transposed V cache writes use one SET_ROWS index per element: `e * kv_size + cell`.

Sources: llama.cpp PR 21560 (github.com/ggml-org/llama.cpp/pull/21560), ggml `ggml-quants.c` and `ggml-cpu/quants.c` (github.com/ggml-org/ggml), Anchuri et al. (arXiv 2603.19025), DeepProve GGUF parser (github.com/Lagrange-Labs/deep-prove/blob/master/zkml/src/parser/gguf.rs).

## Later the same day: native port, formal spec, first proof

- **Native port.** The receipts work moved into a fork of llama.cpp (`luiscosio/llama.cpp`, level with upstream master) as `examples/receipts/`: a C++ tool (`llama-receipts`) that proves, traces and replays, and a Python verifier on gguf-py and numpy. Draft PR 1 in the fork. Validated on Metal and CPU; flash attention, both KV cache layouts, interactive challenge seed. Honest cases accept, the cheaper-quant claim fails on all sampled weight matmuls, wrong file and tampered token reject.
- **Formal spec.** `examples/receipts/spec/`, Lean 4.33.1, no Mathlib: byte-exact Q4_K, Q6_K, Q8_K formats, ggml's Q8_K quantization in Float32, the integer core and float rim, Merkle tree, Fiat-Shamir sample, canonical leaf bytes, edges and inputs, SHA-256. Proved sorry-free: bit fields in range; every s1 below 2^25 and s2 below 2,048,256 (so the M31 circuit never wraps); one- and two-leaf Merkle roots and paths; sampled indices valid and distinct. The `spec-check` executable recomputes a real trace's root, challenge, 10,621 edges and every token and position input in under half a second and matches the C++ prover exactly; arithmetic vectors from a real GGUF match the Python verifier bit for bit. Draft PR 2, stacked on PR 1.
- **First proof.** `examples/receipts/zk/`, Rust on Expander (GKR, Mersenne-31) via its circuit compiler: the Q4_K x Q8_K integer core of one opened matmul node, with model-derived weights exposed as public inputs so an independent verifier can bind them to its GGUF. The circuit enforces Q4_K/Q8_K ranges and integer bounds before field conversion. Kcur-13 (256 x 1536): compile 2.3 s, prove 0.19 s, proof 27.9 MB, verify 0.20 s. Tampered public sums reject; the float step matches the opened output to 2e-7. Private weights remain future work because they require a commitment cryptographically tied to the model. Expander needed two macOS build fixes, kept in a fork (`luiscosio/Expander`, branch `macos-build`). Draft PR 3, stacked on PR 1.
- **Deck** rebuilt to cover all of the above and the road to a proof of the whole forward pass.
