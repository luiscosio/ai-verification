# The statement, version stmt/v0

Date: 2026-09-13. What a proof in this project claims, fixed before backends are built around it. Changes need a new version and a new registration.

## Claim

For a registered model manifest `M`, a public prompt token sequence `P` of at most `L` tokens, and a public output token `t`: running the registered execution specification of `M` on `P` from an empty context produces logits whose greedy choice is `t`.

Public: `M`'s identifier, `P`, `t`, a request identifier. Private: the weights (bound to `M`'s commitments), every activation, every witness value. The proof says nothing about which machine ran it, when, or whether `t` is a good answer.

## Inputs

- Tokens are int32 ids of the tokenizer named in `M` (Qwen3-0.6B: `gpt2` byte-level BPE with the GGUF's vocabulary and merges). The verifier tokenizes the displayed prompt and detokenizes `t` with that material; both must match the proof's public values.
- `L` = 64 for stmt/v0. Chat-template text, if any, is part of `P` and therefore public.
- The context starts empty: no cache, no system state.

## Execution specification (Qwen3-0.6B, Q4_K_M)

- llama.cpp fork `luiscosio/llama.cpp`, branch `receipts-all` at `dce95937b`, CPU backend, 8 threads, one graph for the whole prompt, logits for the last position only.
- Tensor formats: `Q4_K`, `Q6_K` and `F32` blocks as laid out in `spec/ReceiptsSpec/Quant.lean` (`parseQ4K`, `parseQ6K`); no other type is allowed.
- Activation quantization to `Q8_K`, per 256-element block, as in `Quant.quantizeQ8K`: `amax` is the first occurrence of the largest magnitude, `iscale = -127 / amax`, `q = rint(iscale * x)` with round half to even, `d = 1 / iscale`, `bsums[j] = sum of 16 consecutive q`.
- Integer core, exact, per output row and block: `s1 = sum_j sc_j * sum_l q4 * q8` and `s2 = sum_j bsums_j * mn_{j/2}` for `Q4_K`; `dot = sum_j scale_j * sum_l q6 * q8` for `Q6_K`. Proven bounds: `|s1| <= 30,723,840`, `|s2| <= 2,048,256` (`s1_bound`, `s2_bound`).
- Float parts today, in the kernels' order: the per-block scales `d_a * (d * s1 - dmin * s2)` in float32 from f16 scales; `RMS_NORM` with the model's epsilon; `ROPE` neox with the GGUF's base frequency; flash attention in float32 with f16 keys and values; `SWIGLU`; residual `ADD` and norm-weight `MUL`.

### Decision on the float parts

The float parts will not be proven as float32. The circuit-friendly execution mode exists as a reference implementation (`../stage4/fixed_point_forward.py`): activations in fixed point with 20 fraction bits, constants with 24, ggml's Q8_K quantization and integer cores, integer square root, table exponential, round half to even everywhere. It matches llama.cpp's greedy token on 20 of 20 test prompts (`../stage4/report.md`). That mode is the registered execution specification of stmt/v1 once it is ported into the fork's kernels. Until it exists, the trace verifier's tolerances are the operational definition of "the same computation": 1e-5 for `ADD`, `MUL`, `RMS_NORM`, `SWIGLU`; 5e-5 for `ROPE`; 2e-4 for `SOFT_MAX`; 8e-3 for `MUL_MAT`; 2e-2 for `FLASH_ATTN_EXT`.

### Decision on the field

Whole-token circuits use BN254. Measured activations need 14 signed integer bits; with `f` fraction bits a fixed-point product needs `2 * (14 + f)` bits and a sum over `K = 3072` terms another 12. With `f = 16` that is 72 bits, beyond Goldilocks (64) and far beyond Mersenne-31. BN254 also carries Expander's Hyrax and KZG commitments, which the hiding requirement needs. Mersenne-31 stays for the exact integer-core checkpoints, where the proven bounds keep every value below 2^25.

## Output selection

The logits of the last prompt position; `t` is the index of the largest logit, and the lowest index wins a tie. llama.cpp's greedy sampler and the receipts tool agree on this.

## Overflow and ranges

No wraparound is accepted anywhere. Weight values are in range by construction of the registration encoding (nibbles below 16, six-bit scales and mins below 64). Everything derived from activations must be range-checked in the circuit: the `Q8_K` quants, the block sums against the proven bounds, and every fixed-point intermediate against its declared width.

## Rejected requests

Prompts longer than `L`; models or manifest versions not registered; any tensor type other than `Q4_K`, `Q6_K`, `F32`; any matmul with `K` not a multiple of 256; sampling other than greedy; more than one request per graph; a verifier-supplied registration that does not match the pinned one.

## Relation to the receipts

The receipt and its trace keep their meaning as the commit-and-open protocol (`trace/v2`). Under stmt/v0 no opening is published: the trace's leaf hashes remain useful as public boundary commitments if per-operation proofs are linked, and the receipt's `content_sha256` and tokens are what the proof's public inputs are compared against.
