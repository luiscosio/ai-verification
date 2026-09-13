# Complete F20 matrix-vector operation (research claim v1)

This is a separate, experimental claim: `experimental/f20-q4k-matvec/v1`. It does not alter the public site's row-group claim or assert equivalence to native llama.cpp floating-point execution. It implements the matmul rule in `docs/stage4/fixed_point_forward.py` for the entire 1024 x 1024 Q4_K tensor `blk.0.attn_k.weight` of the registered Qwen3-0.6B GGUF.

## Exact computation

Input X has 1024 signed 40-bit integers representing F20 activations. Each consecutive block of 256 selects the first value of greatest absolute magnitude, A. For nonzero A, `q[j] = round_even(-127 * X[j] / A)` and `da = round_even(-A / 127)`. A zero block has q=0 and da=0. These are integer divisions, not the native float quantizer.

For each of all 1024 output rows, compute the Q4_K integer sums s1 and s2 using the existing integer-core circuit. Private constants D and Dmin are the exact finite GGUF half scales converted to signed F24 integers (`round_even(scale * 2^24)`); conversion occurs during trusted registration. They are included in the weight commitment, unlike the earlier integer-only checkpoint. Then:

`Y[row] = round_even(sum_block da[block] * (D[row,block]*s1[row,block] - Dmin[row,block]*s2[row,block]) / 2^24)`.

Output Y must also fit signed 40 bits; overflowing requests are rejected, not wrapped. Private weight scales fit signed 41 bits. Integer-core bounds, 34-bit activation scales, and at most four blocks keep the absolute accumulator below 2^102; its signed 104-bit encoding and the bounded division constraints are well inside BN254. Each division proves a bounded quotient and remainder with `0 <= remainder < denominator`, including the half-even tie rule. Every q, weight bit, scale and output has a circuit-enforced range.

## Private boundaries and complete coverage

One `Quantize(1024)` proof establishes input-commitment to quantized-boundary-commitment correspondence. Exactly 64 `CompleteRows(16,1024)` proofs cover consecutive groups 0 through 63. Every row proof is checked against the operator's corresponding registered weight commitment, the same quantized-boundary commitment and the same request context. The verifier rejects missing, repeated, reordered, mixed-context or disconnected groups.

All weights, scales, X, q, da, Y, s1, s2 and commitment salts are private witnesses. Public data contains only the registration ID, a context field, commitments, group indices and proofs. Input and quantized-boundary commitments have fresh independently sampled salts per request; each output group has its own fresh salt. Salts are sampled across the BN254 scalar field with the OS cryptographic RNG. The same quantized-boundary salt is intentionally reused within one operation to identify exactly one shared vector.

Commitments use the existing circomlib Poseidon chain and fixed-length canonical packed encodings. Domains 3001/3002/3003/3004 distinguish scales, input, output and quantized boundaries. Context and vector length are committed; output commitments also include the group index. Weight commitments bind the integer-core commitment, all D/Dmin constants, group width and K. Weight salt is zero for this open-weight registration.

The composition argument is conditional: sound component proofs plus binding boundary commitments imply that every covered group consumes the vector constrained by the quantization proof. Poseidon collision resistance is required. Random-salted Poseidon commitments are used as computationally hiding commitments under the appropriate hash assumption; this is not an information-theoretic hiding claim. Groth16's witness zero knowledge is relative to the complete public statement. An independent application-specific cryptographic review is still required; tests do not prove the protocol secure.

## Trust and exclusions

The operator installs the registration and keys independently of the proof. Registration associates the name, exact GGUF and scale conversion with the commitments. The experimental local single-contributor setup remains a forgery risk and is not production assurance. Publishing release files does not repair that trust assumption.

A valid package proves one complete F20 matrix-vector relation between commitments. It does not prove how X was obtained, open X or Y, establish a prompt or token, hide public metadata, attest a machine or time, prove native float equivalence, or link operations across a complete model. Request context prevents accidental component mixing under the verifier policy; without a verifier-issued challenge it does not establish freshness.

## Resource decision for this experiment

Keep every component at or below the existing 2^18 setup capacity and run heavy jobs sequentially on the 24 GB development laptop. Record actual phase times and peak process RSS. The whole-token plan's 50 MiB / 10 s verification budgets remain provisional, not an adopted production promise. Compare this experiment with those reference thresholds explicitly; never substitute estimated full-token performance for a measured result.
