# Plan: llama.cpp inference proofs with verification without weights

Date: 2026-09-12

Status: Component proofs and registration tooling exist; no stage is a completed full-inference acceptance gate. The website remains an integer-core row-group checkpoint. A separate [complete F20 matrix-vector experiment](research/complete-operation/README.md) now covers all 1,024 rows with private boundaries; it does not adopt F20 as the default execution mode or complete the native/full-token gates. The 2026-09-13 review repairs are recorded in `docs/repairs-2026-09-13.md`; remaining work is in `TODO.md`.

## Objective

Run an open-weight model locally through llama.cpp with our proof integration, produce an answer and a zero-knowledge proof, and verify the result on a separate machine without downloading the model weights.

The first complete PoC will cover one full next-token computation for one registered model, a short prompt, and deterministic greedy decoding. A website will publish model registrations and make proof verification accessible. The same proof must also be verifiable offline.

Open weights make registration independently checkable. They do not change the requirement that the verifier receives no weights or private witness data.

## Required properties

- Zero knowledge: the proof reveals nothing about the weights, the activations or any other witness value beyond the declared public inputs and outputs. This is a hard requirement of the PoC, not only of the closed-model extension.
- Verification without weights: the verifier receives no model weights or private witness and meets explicit time, memory, and artifact-size limits. Succinct verification is the scaling objective, not an assumption: record how verification cost grows with model size, layer count, and prompt length. An unaggregated proof per operation may satisfy the first PoC budgets but must not be described as model-size-independent verification.
- Binding: the proof is bound to a weight commitment fixed at registration and to the request, so a different model or a different prompt cannot reuse it.
- Execution semantics: the proof constrains the computation of the pinned llama.cpp execution mode. Default to the existing CPU arithmetic. A modified arithmetic mode is a separately registered model-execution variant, with an explicit scope decision and compatibility measurements.

The public receipt design moves from sampled tensor disclosure to proving the computation: no private tensor values in any public sidecar, proof package, or verification material. Zero-knowledge commitment-opening proofs are permitted; disclosing private tensor values is not. The prover may keep a local private witness for proof generation, but it must not be included in exported artifacts.

## The prover is llama.cpp with the proof integration

The user runs one integrated application. Internally, llama.cpp performs inference and captures the witness, while a local proof backend constructs the proof from that witness. Together they form the prover.

The backend may be embedded or launched as a local helper. It must not require the user to manually export tensors, invoke a separate model runtime, or upload weights to a proving service.

The intended experience is one integrated application. This project currently uses a modified llama.cpp executable; it does not rely on a stock installable proof-plugin interface.

```text
Registration, once per supported model version:
  Open GGUF + tokenizer + execution specification
      -> reproducible registration procedure
      -> trusted public model manifest and verification materials

Proving, for each request:
  User's local llama.cpp + proof integration
      <- weights and prompt
      -> inference, private witness capture, local proof generation
      -> answer and portable proof package

Verification:
  Independent verifier
      <- trusted registration, request, answer, proof
      -> accept or reject, with explicit proof coverage
      No GGUF, private witness, model cache, or prover connection
```

## What acceptance means

The proof establishes that the claimed output satisfies the registered model's computation on the claimed input under the specified execution rules.

It does not establish the physical GPU used, the time at which inference occurred, or that the answer is factually correct or safe. Binding a request identifier can distinguish requests, but does not itself prove fresh physical execution.

Model identity has two parts: the proof binds computation to a commitment, and registration establishes which model that commitment represents. A prover-supplied label or verification key is not an independent model identity.

## Starting point

- The existing llama.cpp receipt generator captures execution traces.
- The trace verifier uses the verifier's GGUF, an expected topology digest, and sampled operation checks on published openings, which are raw activation bytes. It is not a full inference proof, and its openings are incompatible with zero knowledge.
- The existing GKR circuit proves a Q4_K x Q8_K integer core with weights private under an Orion commitment. Plain GKR as used there is not zero-knowledge. A separate Groth16 checkpoint proves row groups with private weights and public activation quants and sums.
- The remaining scaling and output comparison happen outside that circuit.
- The Lean specification and arithmetic references are useful for checking the intended computation. They do not establish zero knowledge or the soundness of the complete proof backend.

Relevant code lives under `code/llama.cpp/examples/receipts/`: `receipts.cpp`, `verify_trace.py`, `zk/` (Expander prover, `register.py`, `groth16/`), and `spec/`. Stage records are in `docs/stage1`, `docs/stage4`, `docs/stage5`; the registry in `registry/`; the site in `site/`.

## Scope and initial decisions

| Item | Initial scope |
|---|---|
| Prover interface | One local llama.cpp invocation with proof generation enabled |
| Model | One small open-weight model in the 100M to 500M parameter range, selected after compatibility measurements; the 1.5B model used so far comes after the first full-token proof |
| Existing arithmetic test case | Current Q4_K x Q8_K operation and reference vectors |
| Runtime | One pinned llama.cpp build, CPU backend, thread count and execution configuration; a modified arithmetic mode requires the separate scope decision below |
| Request | Public prompt with explicit tokenization; initially 1 to 16 input tokens after all template and special-token processing |
| Generation | One next token, greedy decoding with specified tie-breaking |
| Private data | Model weights, witness, and internal values except explicitly declared public outputs |
| Verification | Separate local verifier first; browser verification where supported |
| Budgets | Provisional limits below are fixed before benchmarks; revisions must be explicit, and a run exceeding the adopted limits does not pass Stage 5 |
| Registration | Versioned manifest with independently checkable model provenance |
| Deployment | Public registration and verification interface after offline acceptance passes |

### Execution-semantics decision

The existing integer matmul core is an integration starting point, not a complete private-weight operation proof. Scaling, activation quantization, nonlinear operations, and accumulation behavior still need exact specifications. We have not demonstrated a backend that proves the required native floating-point behavior within the PoC budgets.

Stage 1 evaluates two distinct tracks:

1. Native track (default): prove the selected existing llama.cpp CPU computation, including its rounding, accumulation order, and special-value policy. A fixed thread count alone does not define all of these semantics.
2. Modified-mode track (fallback proposal): implement explicitly specified fixed-point or other proof-friendly arithmetic inside llama.cpp and prove that execution. This produces a separately named and registered model-execution variant; it does not establish equivalence to ordinary llama.cpp or a remote provider's execution.

If the native track misses feasibility limits, produce a scope decision for the project owner before adopting the modified-mode track. Report operator differences and token/logit differences on a fixed comparison corpus. Choose any quality-acceptance thresholds before measuring that corpus. Similar outputs are compatibility evidence, not proof of native equivalence. Do not silently substitute an external runtime or a differently quantized model.

### Provisional resource budgets

These are planning limits, not performance forecasts. Stage 1 records the exact local prover and verifier machines, runs pilot measurements, and confirms or explicitly revises the limits before full implementation. Local proving is required; meeting a target only on a remote server does not satisfy it.

| Measurement | Initial ceiling |
|---|---|
| Prover wall time per request, including inference, capture, and proving | 60 minutes |
| Peak prover memory, including child processes and accelerator allocations | 16 GiB; no reliance on swap to meet the target |
| Temporary private witness/storage per request | 10 GiB |
| Complete request proof package, including all component proofs and auxiliary public values | 50 MiB |
| Independent verifier wall time | 10 seconds from process start through parsing and acceptance, using locally installed registration materials |
| Peak verifier memory | 1 GiB |
| Model-specific registration and verification materials downloaded by the verifier | 256 MiB total, counted separately from generic verifier software; no embedded weights |
| One-time model registration and preprocessing | 8 hours and 16 GiB peak memory on the declared local prover machine |

Use at least five preselected distinct prompts spanning the supported input-length range for final timing checks. Report maxima as well as typical values; every supported acceptance run must meet the adopted limits. Record generic setup-material size, persistent prover storage, and verifier installation costs separately. Budget changes require a dated rationale and explicit project-owner acceptance; do not fit the budgets retrospectively to a failing full run.

## Stage 1: freeze the statement and evaluate backends

1. Specify input encoding, tensor formats, supported shapes, rounding, overflow behavior, output selection, and rejection of unsupported cases. Evaluate the execution-semantics tracks above. Derive bounds per operation and representation: an extension of Mersenne-31 retains the same characteristic and does not automatically prevent integer wraparound. Choose bounded arithmetic with constrained rescaling, multi-limb integers with range/carry constraints, or a larger prime field as needed. Select extension fields for protocol soundness separately from integer encoding. Use a versioned execution specification, extending the Lean reference and recording its coverage explicitly.
2. Evaluate DeepProve for transformer coverage and EZKL as a smaller complete reference. Measure arithmetic compatibility rather than assuming either passes or fails. Compare with the existing Expander circuit and inspect the exact pinned implementation for a documented zero-knowledge construction, including any required masking or hiding wrapper. Treat their ML frontends separately from the underlying proof systems: Halo2 does not mandate a particular inference arithmetic, and framework names alone do not establish privacy of this application.
3. Require an established zero-knowledge construction, commitment binding, documented security assumptions and setup requirements, suitable licensing, and separately executable verification. Choose a hiding weight commitment from the start, even though open weights do not need hiding, so the closed-model extension does not force a redesign.
4. Test whether the backend can consume a witness derived from llama.cpp while constraining the same computation. A successful run in the backend's own runtime is insufficient.
5. Measure setup, inference/capture, proving time, memory, proof size, and verification cost on explicitly identified hardware against the provisional budgets. Record the overall soundness target, including composition and Fiat-Shamir assumptions; target at least 128-bit classical security unless an explicit scope decision adopts and labels a different target. Plan monolithic versus linked proofs now, because that choice affects both privacy and resource feasibility; Stage 4 confirms the choice with measurements.

Deliverable: a backend decision record with pinned dependencies, an exact first model/configuration, a reproducible experiment, a list of unsupported operations, adopted resource/security targets, a composition design, and a differential harness comparing llama.cpp, the constrained computation, and the specified Lean reference coverage on the same vectors. Reuse the existing vector pipeline. Agreement between tests does not substitute for complete constraints or a security argument. Do not assume that choosing Orion, declaring private variables, or wrapping an unbound proof establishes the required guarantees.

Exit gate: one candidate demonstrates the necessary privacy and model-binding interface for a small scoped example and has an evidenced feasibility path under the adopted execution rules and budgets. If none does, Stage 1 ends with a feasibility report and an explicit scope decision; listing missing engineering is not permission to proceed as though the gate passed.

## Stage 2: implement independently checkable registration

Produce a public manifest containing:

- Model source, revision, original GGUF digest, and quantization.
- Canonical tensor identities, ordering, shapes, interpretation rules, committed representation (packed bytes or decoded values), and registration-time validity checks.
- Commitments covering all relevant weight values and quantization parameters, including scales and offsets.
- Architecture, tokenizer identity, execution specification, and supported request limits.
- Proof system version, verification materials, security parameters, and exact coverage.
- Registration provenance and a stable identifier for the complete manifest.

Specify how the original GGUF is linked to the proof's weight commitment. For open weights, an independent registration process can check the correspondence once; the per-request verifier does not repeat it. If randomized commitments are used, document how registration is validated without assuming everyone can reproduce a commitment from weights alone.

Keep model and activation commitment randomness separate. Open-model registration may reveal model-opening data to an independent registrar or use a registration proof; document which party learns it and which statement that party validates. Do not publish activation blinding randomness. Closed-model registration will require a privacy-preserving registration proof or an explicitly trusted registrar rather than blindly copying an open-weight disclosure procedure.

The verifier pins an independently obtained registration. It must not accept a replacement registration merely because it accompanies a proof.

Deliverable: registration artifacts and reproduction/validation instructions.

Exit gate: independently validate the registration; changing a weight, tensor mapping, quantization parameter, or execution definition invalidates the old association.

## Stage 3: prove one complete operation with private weights

Use the current quantized operation as an integration checkpoint:

1. Bind its private weight data to the registered tensor commitment and tensor identity.
2. Move checks of private values into proof constraints unless their validity is already established by the registration relation. Repeated weight range checks can be omitted only when registration validated the exact committed decoded field values and the circuit provably uses those same values. A commitment to packed GGUF bytes does not by itself constrain a later nibble/scale decomposition: prove that decoding and its ranges wherever it occurs. Constrain activation quantization, derived values, and all bounds needed to rule out field aliasing. Record the justification for every omitted check.
3. Cover activation quantization, scaling, accumulation, and rounding required by the claimed operation. Proving only the integer sums remains an explicitly narrower checkpoint.
4. Use the selected backend's complete zero-knowledge mechanism. Avoid publishing private intermediate values through the proof package, trace sidecar, or verification materials.
5. Expose an independent verifier that receives no GGUF or private witness.

This checkpoint may declare its operation input and output public. It does not prove that the input activation came from the earlier model layers, and it must not be presented as a full inference proof.

Exit gate: the complete scoped operation verifies in an isolated environment without weights, and tampered commitments, inputs, outputs, and invalid arithmetic reject.

## Stage 4: cover one full next-token computation

Extend the proof relation to all operations actually used by the selected model:

- Token embeddings and position handling.
- Normalization, positional transformations, attention, and its nonlinear operations.
- Feed-forward layers, activations, and residual connections.
- Output projection and greedy token selection, including tie-breaking.
- Initial state and any cache behavior used by the selected execution.

Constrain connections between operations so that one operation's output is the next operation's input. Activations stay private, so per-operation proofs cannot be linked through public vectors. Confirm the Stage 1 composition choice before implementing full-token coverage:

- Monolithic proof: keep intermediate connections inside one constrained computation, subject to local memory limits.
- Linked proofs: each adjacent proof establishes consistency with the same hiding boundary commitment and canonical tensor representation. Include model/execution identity, request context, tensor identity, and shape in the binding design so unrelated proofs or differently interpreted tensors cannot be substituted. Specify blinding generation/reuse within each shared boundary and across requests as required by the selected construction.

A plain hash of an activation is not a hiding commitment. Use an established randomized commitment construction with a documented composition argument. Poseidon2 may be a component when suitable parameters and assumptions are justified; it is not mandatory, and changing SHA-256 to Poseidon2 alone does not provide privacy. The verifier checks that the complete expected graph and every required boundary are covered, accounting for the combined soundness error of all component proofs. Bind the architecture, layer count, and execution policy through the registered program or circuit; do not rely on a topology digest supplied by the prover.

The verifier can tokenize the public prompt and decode the public output using registered tokenizer material, without model weights. Those results must match the proof's token inputs and output.

Aggregation is optional only if complete linked verification meets the adopted budgets. Report the number of proofs and scaling with layer count; meeting a fixed-model budget does not establish asymptotically succinct verification. If unaggregated proofs exceed the limits, aggregate/compress them using a sound construction or revisit feasibility explicitly. No sampled-only acceptance may be labeled full inference verification. The old public-weight proof sizes are useful cautionary measurements, not forecasts for the new backend.

Exit gate: llama.cpp produces one token and a package proving every required step for the selected request, with no unresolved external weight-dependent check.

## Stage 5: isolate verification and test adversarial cases

Run the verifier in a clean environment with no GGUF, model cache, witness files, or network access. Disconnect the prover before verification.

Required checks:

- Honest proof acceptance.
- Rejection after changing the prompt, token, displayed text, commitment, circuit identity, or execution policy.
- Rejection when a proof for model X is checked against a separately registered model Y.
- Rejection of omitted operations, inconsistent intermediate links, invalid quantized values, and field-wraparound attempts.
- Rejection of substituted boundary commitments, reordered component proofs, mixed-request components, and alternative decodings of committed packed weights.
- Rejection of malformed or oversized proof packages within defined resource limits.
- Inspection of public artifacts for weights, private activations, and witness data.
- Verification of the declared setup and protocol assumptions against the selected implementation.

These tests check implementation behavior; they do not constitute a cryptographic proof of zero knowledge, and inspecting artifacts for leaked values is heuristic. Record the construction's security argument, the exact implementation and configuration, and the scope and version of any independent audit. Review application-specific constraints, registration, and composition separately; an upstream audit does not automatically cover them. Unreviewed cryptographic modifications fail the release gate rather than inheriting the backend's privacy claim.

Report registration/preprocessing cost, normal inference time, witness capture overhead, proving time, peak memory, package size, and cold/warm verification time separately. Compare verification with direct inference instead of assuming it is cheaper, and check every budgeted measurement against the adopted limits. Measure the cost of the actual zero-knowledge construction, commitment checks, and any wrapper/aggregation; do not assume the overhead is small.

Exit gate: a second person reproduces offline verification from public materials and the proof package alone; all acceptance cases meet the adopted limits and the construction/implementation review is documented.

## Stage 6: build the registry and verification website

Develop the local proof workspace and verification experience alongside Stages 1 through 5, starting with the honestly labeled row-group checkpoint. Public assurance claims remain gated on cryptographic coverage, setup and independent review. The product/research milestone, file contract, usability acceptance test and release order are in `docs/ux-plan.md`.

Provide these simple views:

1. Generate locally: supported model, prompt, one run action, actual progress, cancellation and a single downloadable proof file. Handle the native executable and proof helpers internally.
2. Verify: choose or drop one proof file; resolve its lookup hints against independently trusted registrations without asking for tensors, groups or keys.
3. Result: exact proof coverage, privacy, registration trust, setup and verification location. Distinguish invalid proof, unsupported format, unavailable verifier and unknown registration. Show request/output as authenticated only when the proof actually binds them.
4. Models and research: expandable registered identities, execution definitions, reproducibility materials and measurements.

Run verification in the browser if the selected backend supports it. Otherwise identify server verification explicitly and offer the independent offline verifier. A website badge alone is not verification evidence.

Publish downloadable manifests, verifier releases, and example accepted/rejected proof packages. Display whether coverage is an operation or a full next-token computation. Avoid publishing a user's prompt or proof package without an explicit sharing action.

Exit gate: a visitor can reproduce the website's result locally without the model weights or trust in the site's reported verdict.

## Definition of done

The complete PoC is done when:

- [ ] Model registration can be independently checked against the open weights.
- [ ] One local llama.cpp invocation produces the answer and proof package.
- [ ] The proof covers a full next-token computation under the registered rules.
- [ ] Private weights are bound to that registration by the proof.
- [ ] A separate verifier requires no weights or witness and works offline.
- [ ] Public prompt and displayed output agree with the verified tokens.
- [ ] Adversarial tests reject and measurements are published with reproducible commands.
- [ ] Prover time/memory/storage, proof package, verifier time/memory, and registration materials meet the adopted budgets.
- [ ] No exported inference or verifier artifact discloses private weights, activations, or witness values beyond the declared public statement; open source model availability is separate from this rule.
- [ ] The execution mode and any differences from standard llama.cpp are registered and displayed explicitly.
- [ ] The selected zero-knowledge construction, implementation review, registration trust, and composition assumptions are documented.
- [ ] The website and offline verifier expose the same explicit verification claim.

A successful single-operation demonstration is a milestone, not completion of this plan.

## Risks, ranked

1. Execution semantics. Exact native behavior may miss the budgets. A modified mode is a different model-execution variant and needs explicit scope acceptance; running it inside llama.cpp does not establish equivalence to other providers.
2. Prover memory and time for a whole token. The earlier approximately 0.2-second public-weight node proof excludes much of the new work, including full operation constraints and privacy. It cannot predict whole-token local feasibility; Stage 1 measures representative workloads.
3. Zero knowledge in the backend. If the chosen prover has no zero-knowledge mode, adding one (masking polynomials, or an outer proof) is research-grade work.
4. Backend maturity and licensing. Expander and its compiler are AGPL-3.0 and change quickly; the macOS build already needs a fork.
5. Registration trust. A wrong or replaced registration defeats every proof; the manifest process needs independent reproduction from day one.

## Later extensions

After the first complete PoC: multiple generated tokens with linked cache state; stochastic sampling with a specified randomness policy; larger models; additional quantizations and hardware; proof aggregation; and authenticated closed-model registrations.

A closed-model provider would run the prover with its private weights and publish compatible verification materials. The verifier-facing interface can remain the same, but establishing model identity then needs provider authentication or an agreed auditor/registration proof. The provider must participate; ordinary API responses do not supply the missing proof.

For an OpenRouter-style integration, the serving provider must generate a proof for the registered execution and return it through the router or a separately bound retrieval endpoint. The client verifies that proof against its chosen registration. Router metadata, a model label, or local installation of our verifier cannot replace provider-side proving.

## Research references

These are evaluation inputs, not endorsements or evidence that our implementation already has their advertised properties.

- [DeepProve repository](https://github.com/Lagrange-Labs/deep-prove): candidate transformer proving backend and local/remote proving interfaces.
- [EZKL repository](https://github.com/zkonduit/ezkl): ONNX-to-ZK tooling, independent verification, and documented quantization caveats.
- [Inference Labs model registration proposal](https://docs.inferencelabs.com/zk-ml/why-zk-ml): committed model identity linked to production inference proofs.
- [Libra paper](https://www.iacr.org/archive/crypto2019/116940229/116940229.pdf): zero-knowledge GKR construction using masking polynomials.
- [Halo2 commitment construction](https://zcash.github.io/halo2/background/pc-ipa.html) and [protocol](https://zcash.github.io/halo2/design/protocol.html): randomized commitments and explicit transcript blinding; privacy depends on the implemented protocol, not the framework name.
- [Finite-field reference](https://doc.sagemath.org/html/en/reference/finite_rings/sage/rings/finite_rings/finite_field_pari_ffelt.html): field characteristic and extension representation are distinct from integer range.
- [zkLLM paper](https://hongyanz.github.io/publications/CCS_zkLLM.pdf) and [implementation limitations](https://github.com/jvhs0706/zkllm-ccs2024#disclaimers): private model commitments, specialized tensor proofs, and the distinction between research code and separate production verification.
