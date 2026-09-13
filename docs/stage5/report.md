# Stage 5: verification in isolation and adversarial cases

Date: 2026-09-13. Script: `verify_isolated.sh`. Proof system under test: the Groth16 checkpoint of `code/llama.cpp/examples/receipts/zk/groth16` (zero-knowledge proof of ggml's Q4_K x Q8_K integer core for a group of weight rows, weights private under a Poseidon commitment). The Expander proofs (`receipts-zk`) are covered by the same negative cases in `zk_node.py`; they are binding but not zero-knowledge, and are verified offline only.

## Isolation

The verifier runs in a fresh directory that holds five files: `verification_key.json`, `manifest.json`, `proof.json`, `public.json` and the 30-line `check.js`, plus a copy of snarkjs. It runs under macOS `sandbox-exec` with a profile that denies all network access and denies reads of `~/.ollama`, `models/`, `code/`, `demo/` and `registry/`. Two controls run under the same profile every time: `cat` on the model file must fail, and `curl` to an external host must fail. Both fail on every run. The prover is a separate process that has already exited; nothing connects to it.

Run on a production package: `blk.0.attn_k.weight` of the registered Qwen3-0.6B, row group 0, proven with `r16_k1024` against the manifest `registry/qwen3-0.6b-q4_k_m/manifest.json`. Accepted in 100 ms inside the sandbox; the same package checked as group 5, with a tampered sum, and with the `r8_k2048` circuit's key: rejected, for the stated reason each time.

## Cases

Every case is a real package produced by the pipeline, then altered where the row says so. Verification key `r1_k1536` is the one-row circuit; `r16_k1536`, `r16_k1024` and `r8_k2048` the production ones.

| Case | What changes | Expected | Result |
|---|---|---|---|
| Honest package, registered group | nothing | accept | accept, 198 ms (test instance), 100 ms (production, Qwen3-0.6B) |
| Public sum changed by one | `public.json` | reject: pairing fails | reject, pairing false |
| Proof checked against another group's registration | manifest group index | reject: commitment differs | reject, bound false |
| Proof made from different weights (one nibble changed, sums recomputed) | prover's witness | reject: commitment differs from the registered one | reject (`groth16_node.py`, both proofs valid on their own, only one matches the registration) |
| Another circuit's verification key | `verification_key.json` | reject: verifier error or pairing false | reject, `Cannot read properties of undefined`, reported as a rejection |
| Out-of-range nibble or activation in the witness | prover input | witness generation fails, no proof | fails at `wtns calculate`: the bit constraints are unsatisfiable (range holds by construction of the bits) |
| Field wraparound | any value near the modulus | rejected or unrepresentable | values here are below 2^26; BN254's modulus is 2^254; a sum near the modulus fails the pairing check like any other wrong sum |
| Malformed or oversized package | file contents or size | refused before verification | the page refuses proofs over 8 KB and public inputs over 2 MB and non-JSON; the server caps Expander packages at 64 MB and 120 s |
| Public artefacts inspected for weights | `proof.json`, `public.json` | no weight values present | `proof.json` is three curve points (805 bytes); `public.json` is the commitment, 1536 activation quants and the sums; the private inputs are deleted after proving |

Cases the plan lists that do not apply to a one-node proof: changing the prompt, the displayed text or the execution policy (the public inputs of this proof are the activation quants and sums; a changed prompt is a different `q8` and the pairing check fails as for any changed public input), omitted operations and inconsistent links between operations (there is one operation).

## Measurements

Apple M5, 24 GB, Node 24. "Package" is `proof.json` plus `public.json`.

| Instance | Constraints | Witness | Prove | Verify | Package | Setup |
|---|---|---|---|---|---|---|
| 1 row of 1536 (`r1_k1536`, test) | 9,624 quadratic | 0.2 s | 0.7 to 1.2 s | 0.3 s (0.19 s in the browser) | 66 KB (proof 805 bytes) | 2^14 local |
| 16 rows of 1536 (`r16_k1536`, production) | 152,148 quadratic, 70,427 linear | 0.3 s | 2.9 to 3.4 s | 0.16 s | 72 KB (proof 805 bytes) | 2^18 local, 36 s; zkey 108 MB, verification key 319 KB |
| 16 rows of 1024 (`r16_k1024`, Qwen3-0.6B, registered) | 101,840 quadratic, 47,939 linear | 0.3 s | 2.5 to 2.7 s | 0.16 s | 45 KB | 2^18 local, 27 s; zkey 78 MB, key 214 KB |
| 8 rows of 2048 (`r8_k2048`, Qwen3-0.6B, registered) | 101,840 quadratic, 47,939 linear | 0.2 s | 2.5 to 2.7 s | 0.17 s | 94 KB | 2^18 local, 28 s; zkey 78 MB, key 401 KB |
| 8 rows of 3072 (`r8_k3072`, Qwen3-0.6B, registered) | 152,148 quadratic, 70,427 linear | 0.3 s | 2.9 to 3.1 s | 0.17 s | 142 KB | 2^18 local, 36 s; zkey 108 MB, key 600 KB |

The whole 256-row node `Vcur-22` of the 1.5B model was proven as 16 groups in 67 s wall time (about 3 s per group) and every group verified against its registered commitment, with the tampered-sum and other-group negatives rejected 16 times over. Compare with inference: llama.cpp produces the whole next token of the 0.6B model in 0.03 s. Verifying one row group takes 0.16 s and a 256-row node needs 16 such checks; a whole token would need about 200 nodes. Verification is not cheaper than inference here and is not meant to be: it needs no weights.

## What these tests are not

They are implementation tests. Zero knowledge rests on Groth16's construction (Groth 2016) and on snarkjs's implementation of it; the setup is proof-of-concept (a locally generated 2^20 powers of tau and one phase-2 contribution), so soundness against a prover who ran the setup is not established. A deployment would use a public ceremony's parameters and a multi-party phase 2, both of which snarkjs supports without code changes here.

## Exit gate

A second person can reproduce the offline verification from the public materials alone: the verification key, the manifest, the package, snarkjs, and `verify_isolated.sh`. No weights, no witness, no network.
