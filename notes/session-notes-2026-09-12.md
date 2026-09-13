# Session notes, Sep 12, 2026: security review of the trace verifier and the one-node proof

Six findings against `verify_trace.py` and the Expander proof of concept, all confirmed, all fixed the same day. Receipt format moved to `0.2`, trace sidecar to `trace/v2`; older receipts are rejected by version instead of failing part way.

## Findings

| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | P0 | The verifier checked the graph count and local edges but never that the graph was the model's forward pass. A three-node graph that skipped the transformer verified. | Every leaf array gets a topology digest: SHA-256 of the canonical leaves with every `sha256` field removed, so shapes, strides, op params, names and producer edges are covered and tensor contents are not. The prover records it; the verifier requires `--expected-topology-sha256` from its own policy and compares recorded, sidecar and recomputed values against it. |
| 2 | P0 | The prover controlled `k`. `k = 0` with no openings verified. | The sidecar's `k` is now the number of openings written; the verifier requires at least `--min-openings` (32 by default, capped by the leaf count) and the prover refuses `--openings <= 0`. |
| 3 | P1 | Logits binding looped over `min(n_graphs, len(per_token))`; an empty `per_token` passed. | One record per response token, each with the right token, position and a logits hash string; every sampled token's graph, prefill included, must bind. |
| 4 | P1 | The proof committed to private `q4`, `sc`, `mn` but its public statement carried no model or tensor binding; only the Python wrapper read the GGUF. | Weights are public inputs. `public.json` carries them and the verifier compares every public input with the values it derives from its own GGUF and the trace before running Expander's verifier (`zk_node.py --verify-only`). |
| 5 | P1 | `fe()` accepted `2^31 - 1`, which is zero in Mersenne-31; `s1 = 2147483647` verified against a true sum of zero. | `fe()` requires `|x| < p`; every public sum must satisfy the integer bounds the Lean spec proves (`|s1| <= 30,723,840`, `|s2| <= 2,048,256`). |
| 6 | P1 | No range constraints on `q4`, `sc`, `mn`, `q8`; `q4 = 16` proved. | Prover and verifier check `q4 < 16`, `sc, mn < 64`, `q8 in [-127, 127]` on every input before field conversion. Host checks suffice while the inputs are public. |

Also tightened: graph and node indices must be contiguous, every graph input must be classified, only tensors named `cache_*` may claim the zeroed initial state, `out_ids` must match, and the token and text commitments (`tokens_sha256`, new `content_sha256`) are recomputed and both feed the Fiat-Shamir challenge. The C++ replay checks both commitments too. The Lean checker recomputes the topology digest and both commitments and requires 32 openings.

## Found during the review of the fixes

- The Lean checker's canonical JSON used `Json.compress`, which writes a tab as `\u0009` where nlohmann and Python write `\t` (same for backspace and form feed). Harmless for leaves, wrong once the checker hashes prompt and response text: a prompt containing a tab was accepted by Python and rejected by Lean. `Protocol.canonicalBytes` now renders with the shared escaping rules, and `spec-check vectors` gets fourteen canonical-JSON documents from `json.dumps` to compare against, control characters and non-ASCII included.
- The Python verifier crashed with a `KeyError` on an old receipt instead of rejecting it. It now checks `receipt_version` and both trace versions first.

## Checked

- Demo end to end on CPU: prove, verify, replay, Lean build and checks, vectors, one-node proof. 34 seconds.
- Honest Metal run passes every hard check in both the Python and the Lean verifier (flash attention on, `MTL0#` copies present).
- Negatives: wrong expected topology, `k = 0`, 8 honest openings against a 32 policy (rejected; accepted with `--min-openings 8`), empty `per_token`, a record without a logits hash, old-format receipt, `q4 = 16` and `q8 = 128` witnesses, `s1 = 2^31 - 1`, one public nibble or scale changed, `--verify-only` against public weights that are not the GGUF's. All refused for the stated reason.
- Prototype: 40 tests pass with the same hardening applied to its verifier.
- The three PR branches were rebased onto upstream master of the same day (`3057bb66c`), each got its fix commit, `receipts-all` was rebuilt from them, everything was pushed to the fork and the PR descriptions were rewritten to match. The deck was regenerated with fresh screenshots.

## Consequences and what is still open

- Making the weights public binds the proof to the model but removes any weight privacy, and the verifier's work is linear in the statement (422,400 public inputs for a 256 x 1536 node), so this proof is not yet cheaper than recomputing the node. The intended next design keeps the weights private under a polynomial commitment that is published once per tensor and exposed as a public value.
- The topology digest is per model, engine build, backend and request shape (prompt length, response length). A deployed verifier needs a store of trusted digests from reference runs; copying the digest from the receipt under review is not a check. Deriving the expected graph from the GGUF architecture metadata would remove that dependency.
- Neither verifier checks that `response.text` is the detokenization of `response.tokens`; both are committed, but the link between them is the tokenizer. A verifier holding the GGUF could detokenize.
- The Lean checker's minimum of 32 openings is fixed in `Main.lean`; the Python verifier's is a flag.
- The sampling bound is unchanged: a fabrication confined to one unsampled node with consistent edges still passes.
