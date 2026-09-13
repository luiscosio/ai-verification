# llama-receipts

Signed inference receipts, recompute verification, and a Merkle-committed activation trace for llama.cpp models, plus attack test sets to calibrate the verifiers.

Four pieces:

1. **Receipts.** Every generation produces a signed JSON document that commits to the model file (SHA-256 of the file and a Merkle root over its tensors), the exact prompt and response tokens, the sampler settings and seed, the uniform draw used at every position, and a hash of the logits at every position.
2. **Recompute verifier.** A second machine takes the receipt and the same GGUF, feeds the claimed tokens back through the model, re-runs the seeded sampler at every position, and reports how often it would have picked the same token and how far the claimed token sits from what it sees. This is Token-DiFR (Karvonen, Rinberg et al., 2025) ported to integer-quantized models on llama.cpp.
3. **Attack test set.** Twelve cases, four honest and eight adversarial (cheaper quantization served, different model served, hidden system prompt, temperature, greedy, and seed tampering, token edits with and without re-signing). Results in `testset/results.md`.
4. **Activation trace (rung 4).** With `--trace`, the prover hashes every tensor the forward pass computes, through llama.cpp's `cb_eval` hook, into one Merkle tree per generation and signs the root. A verifier that never runs the model checks the trace: every input is linked to the node that produced it, graph inputs are regenerated from the claimed tokens, the final logits of each step are tied to the receipt, and a Fiat-Shamir sample of nodes is opened and re-executed in numpy against three arithmetic references, one of them the exact integer path llama.cpp's CPU kernels use. Results in `testset/results-trace.md`.

## Why, and what is actually new

Rungs 1 to 3 are verification by re-execution with a trusted reference. Rung 4 is commit-and-open: the prover commits to the whole computation, and the verifier spot-checks it. Neither is a zero-knowledge proof: the verifier holds the weights and learns everything. See `PRIOR-ART.md` for the full sweep.

Pieces of this exist elsewhere. Signed receipts with model hash, seed, and decode policy exist (EigenAI, INVAR for Ollama, xyntetik-runner, CommitLLM), paired with byte-equality replay. Tolerant recompute with a per-token draw metric exists (Rinberg et al., Token-DiFR, Amodo's prototype), without signatures or logits hashes and using a PRNG stream instead of hash-derived draws. Hashing GGML node outputs into a Merkle root with sampled openings exists as an unmerged llama.cpp draft (PR 21560), whose verifier checks that opened entries hash into the root and stops there.

What we did not find combined anywhere: per-position logits hashes in a signed receipt driving a two-regime decision (strict when the arithmetic is bit-identical, tolerant when it isn't); stateless hash-derived draws that make the draw gap exact rather than statistical; a trace whose leaves link every input to its producer, so the committed computation is one consistent graph rather than a bag of hashes; openings that are re-executed rather than only hash-checked, with weights bound by name to the GGUF commitment; graph inputs regenerated from the claimed tokens, which ties the trace to the receipt; and an integer-exact reference for llama.cpp's Q4_K and Q6_K dot products against Q8_K activations, which is also the arithmetic a proof system would constrain. Most local inference runs on llama.cpp with integer-quantized GGUF weights, so that is the engine. Next rungs: batch commitments, MoE routing capture, and replacing "re-execute node j" with "verify a proof for node j".

## Setup

Python 3.14 via `uv`. llama-cpp-python builds from source with Metal on Apple Silicon.

```bash
cd llama-receipts
CMAKE_ARGS="-DGGML_METAL=on" uv sync
uv run python -m pytest -q
```

Models: the test sets use the Ollama blobs for `qwen2.5:1.5b` (Q4_K_M) and `phi3:mini`, plus a Q2_K requantization of the Qwen blob as the "cheaper model served" case:

```bash
brew install llama.cpp
llama-quantize --allow-requantize ~/.ollama/models/blobs/sha256-183715c4… models/qwen2.5-1.5b-instruct-q2_k.gguf Q2_K
```

## Usage

Generate with a receipt:

```bash
uv run python -m receipts.prove --model <model.gguf> --prompt "The capital of France is" --n-predict 64 --seed 42 --out out/r1.json
```

Add `--trace` to commit to the activation trace as well. This writes `out/r1.trace.json.gz` next to the receipt with every leaf and the openings for the challenge (`--openings`, default 32):

```bash
uv run python -m receipts.prove --model <model.gguf> --prompt "The capital of France is" --n-predict 64 --seed 42 --trace --out out/r1.json
```

Verify by replay on the same or another machine (exit code 0 on accept). A trace sidecar next to the receipt is checked too, and a failing trace rejects the receipt:

```bash
uv run python -m receipts.verify out/r1.json --model <model.gguf> --mode incremental
```

Verify the trace alone, without running the model:

```bash
uv run python -m receipts.verify out/r1.json --model <model.gguf> --mode trace --expected-topology-sha256 HASH
uv run python -m receipts.verify_trace out/r1.json --model <model.gguf> --expected-topology-sha256 HASH   # same, with every check printed
```

`--mode batched` replays the whole sequence in one prefill pass, which is faster but uses different kernels than token-by-token decode; expect identical tokens with slightly different logits. `--full-model-check` also recomputes the tensor Merkle root.

Run the attack matrices (about ten minutes each on an M5):

```bash
uv run python -m testset.run_matrix          # rungs 1 to 3, testset/results.md
uv run python -m testset.run_trace_matrix    # rung 4, testset/results-trace.md
```

## Receipt format (v0.1)

```
receipt_version, created_at
engine:      llama-cpp-python version, ggml system info, backend, thread and layer settings, model metadata
model:       file name, size, file_sha256, tensor_merkle_root, n_tensors, GGUF metadata (arch, name, file type)
request:     prompt_text, prompt_tokens, sampler {type, temperature, top_k, top_p, seed}, n_predict
response:    tokens, text, per_token[]: position, token, logprob, logprob_full, u, boundary_distance, logits_sha256, top candidates
commitments: tokens_sha256, content_sha256
trace:       (with --trace) version, root, topology_sha256, n_leaves, n_graphs, leaf hash rule, layout ops resolved, tracer stats
signature:   ed25519 over the canonical JSON of everything above
```

The sampler is deterministic by construction: the uniform draw at position t is `SHA-256("llama-receipts/u/v1/" || seed || t)`, ties break by token id, and top-k then top-p truncation happens in float64. Any verifier can reproduce the draw without RNG state.

## Trace format (trace/v2)

One graph per `llama_decode` call: the prompt prefill, then one graph per generated token. The tracer observes every GGML node through `cb_eval`. Layout ops (RESHAPE, VIEW, PERMUTE, TRANSPOSE) compute nothing and are resolved to the tensor they view; every other node becomes a leaf:

```
g, i:      graph index, node index within the graph
name, op:  ggml node name and op (unary and GLU ops carry the specific function)
params:    op_params bytes (rope frequencies, softmax scale, norm eps, ...)
out:       type, ne, nb, offset into the base tensor; base {name, type, ne, nb, nbytes, sha256}
srcs[]:    kind "weight": name, type, ne, nb, sha256 from the GGUF commitment
           kind "data":   type, ne, nb, offset; base {..., sha256}; producer
```

`producer` is the leaf that last wrote the base tensor, `-1` for a graph input (tokens, positions, output row ids, KV cell indices, attention mask), or `-2` for persistent state before its first write (the KV cache, which llama.cpp zeroes). Sources are hashed over their whole base tensor, so a view of the KV cache and the SET_ROWS node that wrote it hash the same bytes and the edge check is a string comparison. Leaves are hashed as `sha256(0x00 || canonical_json(leaf))` into one binary Merkle tree over the whole generation.

The sidecar holds every leaf (a few hundred bytes each; 700 leaves per graph for Qwen2.5 1.5B), the challenge, and the openings. An opening carries the leaf's Merkle path and the raw bytes of its output and of every data input, compressed. Weights are not shipped: the verifier uses its own copy and checks the committed hash. The challenge is `k` distinct indices derived from `SHA-256(domain || root || tokens_sha256 || content_sha256 || model file sha256 || counter)`; an interactive verifier can supply a seed instead. Verification requires at least 32 openings and a topology digest supplied from a separately trusted policy or known-good run.

The prover runs twice. Pass one generates and hashes; the root goes into the receipt and is signed. Pass two replays the same tokens with the KV cache cleared, captures the bytes of the sampled leaves, and must reproduce the root bit for bit. It does on both backends: the trace is deterministic once the cache starts zeroed, which is why `Engine.reset()` now clears it.

## Trace verifier

Checks, cheapest first. All but the last two need no tensor bytes.

1. **Root and content.** The leaves hash to the root the receipt signed; leaf and graph counts match; the token and text commitments recompute. The hash-free graph structure must equal a topology digest the verifier pinned from a trusted reference run for the same model, engine and request shape; the value inside the receipt under review is not a check.
2. **Challenge.** The openings are exactly the indices the root and receipt imply, and there are at least as many as the verifier's policy demands (`--min-openings`, 32 by default).
3. **Structure.** The graph count fits the token sequence (prefill plus one graph per token, with or without the trailing feed after the last sampled token).
4. **Inputs.** Every graph's token and position inputs hash to what the claimed prompt and response say; the output row selection is the full batch. KV cell indices (including the transposed V layout) and the causal mask are regenerated too and reported.
5. **Edges.** Every data input's base hash equals the output hash of its producer leaf, which must come earlier; initial KV state hashes to zeros.
6. **Logits binding.** There is one well-formed per-token record per response token, and every graph that produced a sampled token has its final matmul output hash equal to that record's `logits_sha256`, so the trace and the sampler evidence describe the same run.
7. **Openings.** Each opening sits in the tree, its bytes hash to the leaf, its weight inputs match the verifier's own GGUF commitment by name, type, shape, and hash, and re-executing the op in numpy reproduces the output.

Re-execution compares a normalized error, `max|out - ref| / max|ref|`, against a per-op limit. CONT and SET_ROWS are compared bit for bit. MUL_MAT is judged against three references and takes the closest: dequantized weight times float32 activation (Metal decode kernels), both operands rounded to half (Metal prefill simdgroup kernels), and ggml's CPU path for quantized weights, where the activation row is quantized to Q8_K and the dot product is integer (`receipts/qdot.py`, following `quantize_row_q8_K_ref` and `ggml_vec_dot_q4_K_q8_K`). Weights with more than 16,384 output rows (the vocabulary projection) are checked on a challenge-chosen sample of 2,048 rows.

Calibration (Sep 11, 2026, qwen2.5 1.5B Q4_K_M, about 1,200 openings per backend, three prompts, 16 tokens):

| Op | Metal | CPU (8 threads) | Limit |
|---|---|---|---|
| ADD, MUL, RMS_NORM, SWIGLU | ≤ 1.6e-7 | ≤ 1.2e-7 | 1e-5 |
| ROPE | 6.2e-7 | 1.8e-6 | 5e-5 |
| SOFT_MAX | 1.9e-7 | 2.4e-5 | 2e-4 |
| GET_ROWS, CONT, SET_ROWS | exact | exact | exact |
| MUL_MAT, weights, decode | 6.0e-7 (f32 reference) | 7.3e-7 (Q8_K reference) | 8e-3 |
| MUL_MAT, weights, prefill | 2.9e-3 (half inputs) | 2.7e-7 (Q8_K reference) | 8e-3 |
| MUL_MAT, KV cache | 1.9e-7 decode, 5.5e-4 prefill | 1.2e-3 | 8e-3 |

Before the integer reference, CPU weight matmuls sat at 1e-2 to 3.8e-2 and the limit had to be 8e-2. What is left above float noise is half-precision accumulation the references cannot reproduce: Metal's prefill kernels feed half-precision operands to the simdgroup units, and the CPU's f16 dot product for the KV cache accumulates in half on ARM.

## Verifier output

Per position: claimed token, replayed token, match, logits-hash match, the claimed token's log-prob under the verifier's sampling distribution (minus infinity if truncated away), and the distance of the uniform draw from the nearest CDF boundary (small means a benign flip, large means the distributions differ). Summary: token match rate, logits-hash match rate, count of claimed tokens outside the verifier's support, mean and max absolute log-prob difference, first mismatch.

Decision rule. Reject on a bad signature, a malformed receipt, a model hash mismatch, or any claimed token outside the sampler's support. Then, if every logits hash matches (same backend), require every token to match. Otherwise accept only if the largest draw gap is at most 0.45, the mean draw gap over all positions is at most 0.03, token match is at least 0.75, and mean absolute log-prob difference is at most 0.25. Verdicts say which regime applied: "bit-exact replay" or "within backend drift". A trace sidecar, when present, must pass all hard checks as well. In `--mode trace` the decision is signature, structure, model hash, and trace only.

## Results, rungs 1 to 3 (Sep 10, 2026, Apple M5, qwen2.5 1.5B Q4_K_M, 8 prompts × 48 tokens)

95 of 96 verdicts correct. Full table in `testset/results.md`; earlier calibration passes are kept as `results-run1-old-thresholds.md` and `results-run2-gap-0.10.md`.

| Case | Correct | What the numbers show |
|---|---|---|
| H1 same backend (Metal), incremental replay | 8/8 | bit-exact: every logits hash matches, log-prob differences around 1e-7 |
| H2 same backend, batched replay | 8/8 | same tokens, different logits (prefill kernels differ from decode kernels); worst draw gap 0.07 |
| H3 Metal prove, CPU verify | 8/8 | real drift: token match 0.79 to 0.98, single-position draw gaps up to 0.43 |
| H4 CPU 8 threads prove, CPU 4 threads verify | 8/8 | bit-exact; thread count does not matter |
| A1 cheaper quant (Q2_K) served | 8/8 | 78 claimed tokens outside the sampler's support, log-prob gap ten times honest drift |
| A2 different model served | 8/8 | caught on the first tokens |
| A3 hidden system prompt | 7/8 | one mild case overlaps honest cross-backend drift at 48 tokens |
| A4 temperature 1.3 claimed as 0.7 | 8/8 | logits bit-identical, sampler disagrees; 38 truncated claims |
| A5 greedy claimed as seeded | 8/8 | logits bit-identical, sampler disagrees |
| A6 wrong seed claimed | 8/8 | logits bit-identical, log-prob gap zero, caught only by the draw gap |
| A7 token edited, not re-signed | 8/8 | signature |
| A8 token edited, re-signed | 8/8 | edit cascades into out-of-support claims |

Three lessons that shaped the verifier:

- **Same-backend replay is bit-exact**, across runs and thread counts. So the verifier uses two regimes. When every logits hash matches, any token mismatch is impossible for an honest prover and is judged as sampler tampering. When logits differ (other backend, or batched replay), it tolerates small draw gaps.
- **Logit hashes prove nothing about the sampler.** Temperature, greedy, and seed tampering leave the logits bit-identical. Only replaying the seeded sampler catches them, and the wrong-seed case is caught only by the draw gap (how far the uniform draw sits from the claimed token's interval), since its log-prob difference is exactly zero.
- **Cross-backend drift on quantized models is large.** Metal versus CPU on Q4_K_M moved single-position draw gaps as far as 0.43. The drift-regime limits (mean gap 0.03, max gap 0.45) are fitted to eight prompts and have thin margins. Verify on the same backend class when you can; it's exact. When you can't, use longer sequences so systematic shifts separate from symmetric noise.

## Results, rung 4 (Sep 11, 2026, Apple M5, qwen2.5 1.5B Q4_K_M, 4 prompts × 32 tokens, 32 openings)

28 of 28 verdicts correct on the seven cases with an expected verdict; the eighth case documents the sampling bound. Full table in `testset/results-trace.md`, every receipt, sidecar, and verification report under `testset/out/trace/`.

| Case | Expected | Verdicts | Leaves / graphs | Prove s | Verify s | Sidecar MB | Failed checks | Worst MUL_MAT error |
|---|---|---|---|---|---|---|---|---|
| TH1 honest / Metal prove, trace-only verify | accept | 4/4 correct | 23298 / 33 | 11.5 | 2.5 (replay 1.6 s) | 3.2 | none | 2.4e-03 |
| TH2 honest / CPU prove, trace-only verify | accept | 4/4 correct | 23298 / 33 | 10.8 | 2.6 | 3.2 | none | 9.4e-04 |
| TA1 cheaper quant served (Q2_K), claims Q4_K_M, leaf types forged | reject | 4/4 correct | 23298 / 33 | 11.9 | 2.5 | 4.6 | openings | 4.0e-01 |
| TA2 different model served (phi3), claims qwen | reject | 4/4 correct | 22374 / 33 | 21.2 | 2.3 | 5.3 | openings | 5.9e-04 |
| TA3 hidden system prompt | reject | 4/4 correct | 23298 / 33 | 11.5 | 2.7 | 3.8 | input_k_cells, input_mask, input_out_ids, input_positions, input_tokens, input_v_cells | 1.5e-03 |
| TA7 token edit, commitments and signature refreshed, trace untouched | reject | 4/4 correct | 23298 / 33 | 11.6 | 2.7 | 3.2 | challenge, input_tokens | 2.4e-03 |
| TA9 single fabricated activation, edges kept consistent | limitation | 0/4 caught | 23298 / 33 | 11.9 | 2.5 | 3.0 | none | 5.3e-04 |
| TA10 signed root differs from the leaves | reject | 4/4 correct | 23298 / 33 | 11.5 | 2.5 | 3.2 | challenge, openings, root | – |

Verify time is the trace-only verifier (no model execution). Prove time covers both passes with tracing; an untraced 32-token generation takes about a second.

What the trace adds over replay, and what it does not:

- **Model and quantization swaps are caught without running the model.** Every weight matmul re-executes wrong when the bytes came from Q2_K weights, so a handful of openings suffice. A different architecture fails at the weight binding before any arithmetic.
- **Hidden context and token edits are caught structurally.** The prefill graph's token input hashes to the tokens the model saw; a decode graph's token input hashes to the token it consumed. These checks cost nothing.
- **Sampler tampering is out of scope.** Temperature, greedy, and seed attacks leave every activation honest. The trace ties its logits to the receipt's logits hashes; rung 3 then judges the sampler.
- **A cheat confined to one node is caught only if that node or a consumer is sampled.** With k openings over N leaves, the miss probability is about 1 - (1 + consumers) k / N. TA9 fabricates one residual-stream activation with consistent edges to show this. Dense cheats (wrong weights, wrong model, wrong arithmetic everywhere) are the treaty-relevant class and the trace is built for those; targeted single-node fabrication needs full replay or a proof.
- **Verifier cost at this scale favors replay.** Trace-only verification of a 32-token receipt with 32 openings takes about 2.5 seconds, dominated by dequantizing the opened weights in numpy; replaying the same receipt on Metal takes 1.6 seconds. The trace verifier's cost is fixed by k and the model's layer width, while replay grows with model size, so the crossover sits at models large enough that a forward pass costs real money. For a 1.5B model on a laptop, the trace buys binding of every intermediate tensor and a verifier that needs no GPU, not speed.
- **Prover overhead.** Observing every node splits the graph into single-node dispatches with a sync each. Tracing a 32-token generation of this 1.5B model takes about 10 to 12 seconds for both passes on Metal or CPU, of which under 2 seconds is hashing and Python; the rest is per-node dispatch. The sidecar is a few megabytes.

## Threat model

The verifier holds the same model file. The prover may serve a different or cheaper model, hide part of the context, change sampler settings, edit tokens, steal the signing key, or (rung 4) commit to a trace it did not compute. Replay catches all but a re-signed edit that lands on a token the sampler could have produced. The trace catches wrong weights, wrong model, hidden context, and edits with a verifier that never runs the model, and binds every intermediate tensor to the receipt; it does not catch sampler tampering (rung 3 does) or sparse single-node fabrication (a proof system would).

Not covered: what else ran on the prover's hardware (completeness), and the case where the verifier must not see the weights. Those need a ZK backend or hardware attestation.

## Layout

```
receipts/   merkle, sampler, keys, receipt, model_commit, engine, prove, verify
            ggml (tensor struct access), trace (tracer, challenge, sidecar), ops (numpy re-execution),
            qdot (Q8_K integer references), verify_trace (trace verifier)
tests/      unit tests for the pure parts
testset/    run_matrix.py and results.md (rungs 1 to 3); run_trace_matrix.py and results-trace.md (rung 4); out/ (generated)
models/     local requantizations (gitignored)
```
