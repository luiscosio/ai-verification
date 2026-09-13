# Stage 4: the circuit-friendly execution mode, measured

Date: 2026-09-13. Code: `fixed_point_forward.py` (the reference), `agreement.sh` (ground truth from llama.cpp and the comparison), `prompts.txt`, results in `agreement-qwen3-0.6b.json`.

Stage 4 asks for a proof of one full next-token computation. That proof is not built. What is built is the piece every later step depends on and that the statement (`../stage1/statement.md`) named as the decision to make first: a complete definition of the forward pass in integer arithmetic, run end to end on the first model, and measured against llama.cpp's float path.

## The execution mode

One next token of Qwen3-0.6B (28 layers, hidden 1024, 16 heads and 8 KV heads of 128, FFN 3072, Q4_K and Q6_K weights) computed with integers only:

- The proposed variant uses F = 20 fraction bits (F = 16 is the historical pilot). Constants (per-block scales `d`, `dmin`, norm weights, RoPE cosines and sines, `1/sqrt(128)`, `log2 e`) are integers with S = 24 fraction bits, derived once from the GGUF and published by a registration.
- Matmuls use ggml's signed-maximum Q8_K convention (`iscale = -127/amax`) with integer round-half-even division and fixed-point scales, run ggml's integer core (`s1`, `s2` for Q4_K, `dotQ6` for Q6_K, the Lean spec's definitions), and apply the block scales as integer products with one rounding per output element.
- RMS normalization uses an integer square root; RoPE uses the integer tables; softmax and SiLU use `exp(z) = 2^(z log2 e)` with a 4096-entry table of `2^(f/4096)` and shifts.
- Every division rounds half to even; the argmax takes the lowest token id on ties, as llama.cpp does.

The whole thing is 330 lines of Python and numpy. It is the specification the llama.cpp kernels of stmt/v1 must implement and the circuits must constrain; it is not fast (22 s per prompt in Python).

## Agreement with llama.cpp

Twenty short prompts (`prompts.txt`), greedy next token, llama.cpp CPU float path against the fixed-point mode:

| Fraction bits F | Same next token | Different |
|---|---|---|
| 16 | 19 of 20 | 1 (`The speed of light is approximately`: llama.cpp ` ` (220), fixed point ` 3` (400)) |
| 20 | 20 of 20 | none |

Decision for stmt/v1: F = 20. It costs four bits of width per activation and removes the one disagreement; the widths below are given for both.

At F = 16 the one disagreement is a pair llama.cpp had at probabilities 0.49 and 0.33 (a logit gap of about 0.4) that the fixed-point path put 0.11 apart the other way: about half a logit of drift over 28 layers, all of it precision, since F = 20 removes it (`agreement-qwen3-0.6b-f20.json`). Across the twenty prompts the median top-two margin at F = 16 is 1.0 and the smallest agreeing margin is 0.21. Under stmt/v1 the registered execution specification is the fixed-point one, so its token is the correct answer by definition and the float path is the approximation; what the agreement rate measures is how far the registered mode sits from the model people already run.

## Bit widths measured

Largest magnitudes over the twenty prompts, which inform candidate widths; these measured maxima do not prove bounds for every supported input:

| Op | Bits at F = 16 | Bits at F = 20 | Note |
|---|---|---|---|
| Embedding lookup | 13 | 17 | |
| RMS_NORM | 26 | 30 | after the norm weight |
| MUL_MAT | 29 | 33 | output, after scales; the integer core itself stays below 2^25 per block (proven) |
| ROPE | 25 | 29 | |
| Attention scores | 22 | 26 | |
| Attention output | 22 | 26 | |
| Residual ADD | 29 | 33 | |
| SWIGLU | 28 | 32 | |

Products of two 33-bit values with 3072-term sums reach about 78 bits before the final rounding, which confirms the field decision: BN254 for whole-token circuits, Mersenne-31 only for the exact integer cores.

## What a whole-token proof costs, from these counts

One decode graph of Qwen3-0.6B has 197 matmuls (168 Q4_K, 29 Q6_K), 113 RMS norms, 113 elementwise scalings, 56 RoPE, 56 KV writes, 56 residual adds, 28 attentions and 28 SwiGLU. The Q4_K weights alone are 322 million nibbles per token.

- In R1CS (Groth16, as in the Stage 3 checkpoint) each nibble costs 4 bit constraints and one product: about 1.6 billion constraints per token, 2^31. That is beyond any setup we can hold and beyond a laptop's memory, and it is why the Groth16 path stops at per-node proofs.
- With lookup arguments (a Plonkish system or a GKR with logup) the nibble range checks are one lookup each and the products remain: about 320 million multiplications per token. A GKR prover at tens of millions of gates per second is minutes per token on a laptop, and tens of seconds on a GPU. That is the Stage 4 prover shape: GKR with lookups, with the zero-knowledge masking Stage 1 identified as missing, or recursive aggregation of per-node proofs.
- The nonlinear operations are cheap by comparison: the norms, RoPE, softmax and SiLU of one token are under ten million constraints even in R1CS, because they touch activations (thousands of values) rather than weights (hundreds of millions).

## Linking

Activations stay private, so per-operation proofs link through commitments to the boundary vectors, or a whole layer goes into one circuit. The F20 measurements include 33-bit magnitudes, requiring an explicit signed encoding and bounds before packing. Boundary commitments must be randomized and hiding, bind context and tensor identity, and have a composition argument. Monolithic versus linked remains open and affects soundness, privacy and capacity; no complete composition is implemented.

## What is not done

- The llama.cpp kernels of this mode. The reference defines them; porting them into ggml's CPU backend as a selectable execution mode is the next engineering step, after which the trace verifier's tolerances become exact equalities.
- Circuits for anything but the Q4_K integer core.
- The whole-token prover. The counts above say what it needs.

Review repair: the reference now preserves the sign of the first maximum-magnitude element when quantizing Q8_K. This matches ggml's quant/scale sign convention; fixed-point rounding remains a distinct execution rule. `agreement.sh` explicitly selects F20. The 20-prompt corpus is compatibility/tuning evidence, not a held-out equivalence guarantee.

## September 13 complete-operation follow-up

The later [F20 complete-operation experiment](../../research/complete-operation/README.md) implements activation quantization, weight scales, accumulation and rounding for one entire 1,024 × 1,024 Q4_K tensor with private boundaries. It supersedes the earlier statement that only the integer core has a circuit. The current registration inventory is 381,681,664 Q4 values, correcting the earlier rough 322-million count above; the new scaling script derives its count directly from that inventory. A full-token circuit and native execution equivalence remain unimplemented.
