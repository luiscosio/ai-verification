# Proof workspace: product and research plan

Updated September 13, 2026. This plan develops usability alongside the cryptographic stages in `PLAN.md`. An easier interface does not change what a proof establishes or satisfy a full-inference gate.

## First milestone

Choose the supported model, enter a short prompt, generate locally, download one file, and verify that file on a separate website without model weights. A new user must be able to explain the result's coverage and limitations without reading circuit documentation.

The first implementation uses the existing Groth16 integer row-group checkpoint. It runs two local generation steps to capture a supported operation; neither generated token is proven. Full-operation and full-token research remain separate unfinished gates.

## Journey and current implementation

| Task | Experience | Implementation |
|---|---|---|
| Try it | Verify a valid example or an invalid example without installation | Built static verifier page; both examples use real proof fixtures |
| Start locally | One launcher opens access to a local workspace with prerequisite messages | `start-workspace.sh`; user opens the printed local address |
| Generate | Choose Qwen3-0.6B, enter a prompt, run | `site/local_prover.py` coordinates the existing native executable and Groth16 helper; no manual tensor selection |
| Follow progress | Model check, inference/capture, witness, proving, checking, export; elapsed time | Actual process stages; no guessed percentage or completion estimate |
| Recover | Cancel the owned process tree, or correct a failure and retry | One active job, timeouts, cleanup of private temporary files; latest job recoverable on page reload while server remains running |
| Export | Download one `.llamaproof` JSON file | Strict versioned envelope containing public proof inputs and registry lookup hints |
| Verify | Choose or drop one file; click Verify | Browser selects the installed registration, tensor and key; the package cannot install its own trust anchor |
| Understand | Distinct verified, invalid, unknown-registration, unsupported and unavailable results | Exact operation coverage, registration trust, privacy boundary and experimental setup visible |
| Reproduce | Verify the same file offline | `node site/verify-file.cjs PROOF_FILE`; requires pinned npm dependencies and independently checked registry materials |

The public static page never discovers or contacts a local prover. Proving is enabled only in the separate loopback companion page, protected by an ephemeral session token and Host/Origin checks. The existing server-side Expander endpoint remains a different verification route, explicitly not zero-knowledge.

## File and trust contract

`llama-receipts/proof-package/v1` carries exactly `format`, `claim`, `registration_id`, `tensor`, `group`, `proof`, and `public`. Its supported claim is `q4k-integer-row-group/v1`. Files are capped at 2 MiB; unknown fields and unsupported claims are rejected. It carries no registration, verification key, trusted verdict, prompt text, generated text, private witness or trace.

Public activation values and arithmetic sums can still reveal information about a request. Omitting the prompt text does not prove prompt privacy. This checkpoint hides the weight witness relative to its public statement and uses experimental single-contributor setup materials.

The browser consumes the registry validated by the site builder. The offline verifier consumes operator-installed registry materials previously checked with `register.py`; it applies the same pinned-key, commitment, shape and range policy. Python registration-ID encoding must not be silently replaced with JavaScript JSON encoding: number serialization differs. Registrations must be obtained and checked independently, not copied from a prover's untrusted package.

A valid row-group proof is not a verified answer, complete operation, proof of physical execution on a particular machine, or proof of request freshness. Future complete-token packages need a separately reviewed claim version and explicit prompt/output binding. The interface must never promote metadata into authenticated output.

## Acceptance and validation

Implementation checks cover honest and adversarial proof acceptance, package version/claim boundaries, unknown registrations, malformed JSON, safe result rendering, key lookup, local access checks, bounded requests, one-job concurrency, cancellation, timeout, failure recovery and offline verification. Exercise a real local generation and verify its exported proof in the browser and offline. Check the layout at narrow and wide widths and the ordinary keyboard path.

The owner deferred the human usability study for this iteration and requested local tests. The comprehension gate remains unmeasured; a later study would ask at least three people unfamiliar with the project to try an example, generate a proof on a prepared machine, verify a file, and explain what passed. Record time, obstacles and mistaken interpretations. Target at most one file choice and one verification action; no tensor, group, JSON-field or key selection. Installation time and warm proving time are measured separately. Any participant interpreting the present result as proof of the answer triggers a copy/design revision.

The implementation checks and first real browser/offline round trip are recorded in `docs/workspace-validation-2026-09-13.md`.

`./setup-workspace.sh` now installs locked dependencies, builds the pinned native tools, downloads checksum-pinned matching proving materials and prepares the exact registered model. A fresh local checkout was compiled and exercised on macOS. A desktop installer and clean Linux-host validation remain future work. The installer reuses the existing setup; generating a new ceremony creates different keys and is not a way to install an existing registration.

## Research alongside the interface

1. Specify and prove one complete operation with private weights. Settle native versus candidate F20 semantics, activation privacy, boundary binding and resource budgets before a broad port.
2. Test whether the chosen construction composes into a complete token within the local memory/time budget. Publish evidence when it does not scale as well as when it does.
3. Capture reproducible experiments: hardware, model registration, source revisions and dirty state, statement version, setup, inputs/corpus, phase timings, peak memory, storage and proof sizes, cold/warm verification, and failure cases.
4. Compare equivalent claims and privacy guarantees. A faster partial proof is not evidence of a faster complete inference proof. Report witness capture separately from ordinary inference and setup separately from repeated proving.
5. Publish benchmark artifacts and negative cases with the exact verifier release. Keep measurements out of the proof's authenticated claim unless they are separately attested.

The first workspace records model-check, combined inference/capture, witness, proving and verification times, package bytes, circuit and verifier identity. Peak memory, separate capture overhead, complete environment capture and a controlled comparison dashboard remain unfinished. Advancing the state of the art needs a precise hypothesis and reproducible comparative evidence; the interface helps people run and inspect those experiments.

## Release order

The older private artifact remains historical. The hosted experimental registry is deployed to GitHub Pages at `https://luiscosio.github.io/ai-verification/`. The generated files in `site/` remain local outputs; the workflow builds its own bundle from committed sources.

1. Review and commit the changes in the llama.cpp fork, then push that fork commit.
2. Update the parent repository's submodule pin to that available commit; commit the registration, shared-policy consumers, checks, workspace and documentation together, then push the parent.
3. Run `checks/run.sh` locally. A push to `main` triggers the Pages workflow, which runs the browser/offline acceptance regressions and builds the trusted-registry bundle.
4. Wait for the Pages deployment to finish. Verify both bundled examples and a freshly generated file on the hosted site; confirm the registration ID and scope labels.
5. Record the parent commit, fork commit and deployment URL. Publishing more model identities must not imply proof coverage for unsupported tensors or models.

Keep a private research preview distinct from a production-assurance release. Production still requires appropriate setup, independent registration/review, verified execution coverage and the security gates in `PLAN.md`.

September 13 hosted release: parent implementation commit `5273610b5894bfc3248141a433d1576679481931` pins fork commit `7b8c8181e` on `receipts-all`. The [Pages workflow](https://github.com/luiscosio/ai-verification/actions/runs/34775634028) passed. A real local `.llamaproof` file was accepted on the hosted site in 77 ms; the invalid-activation example was rejected. The catalogue contains Qwen3-0.6B (168 tensors with row-group commitments), Qwen2.5-1.5B (`blk.0.ffn_gate.weight` only, 560 groups), and Qwen2.5-0.5B (fingerprints only). The two added records were checked against their actual GGUF files; the 1.5B checkpoint commitments were recomputed during validation. These are project registrations, not provider-signed certificates or full-inference proofs.


## September 13 design revision

The public site now starts with verification, while the local companion starts with generation. Both use the same editorial layout, clear type hierarchy, and searchable model records instead of repeated rounded cards. Model records distinguish exact-file registration from integer-row proof support; unsupported models remain visible without an acceptance claim.

The result is the primary design surface: a verdict, explicit full-inference limitation, model identity, commitment match and measured verification time. Only accepted proofs show a coverage explorer. Its model view uses one square per registered tensor; its rows view uses one block per row in the accepted group. The operation view is explicitly a conceptual sequence, not a certified execution graph or progress measure.

The jelly illustration is a visual analogy for a small checked piece within a larger whole. It is decorative and never reflects acceptance. Three.js 0.180.0 creates fluted geometry, physical transmission, studio reflections and subtle elastic motion. It has a pause control, responds to reduced-motion preferences, stops drawing off-screen or in a background tab, caps resolution and frame rate, and leaves an inline SVG fallback when unavailable. No proof data is passed into the scene. CSS and the animation source are embedded by the existing static builder, keeping the public and local pages consistent.

Design references: [Distill](https://distill.pub/) for editorial hierarchy; [Are.na](https://www.are.na/) for restrained framing; [Bartosz Ciechanowski](https://ciechanow.ski/) and [Communicating with Interactive Articles](https://distill.pub/2020/communicating-with-interactive-articles/) for explanations grounded in interactions. The implementation uses [Three.js physical materials](https://threejs.org/docs/pages/MeshPhysicalMaterial.html).

Validation: the complete existing check suite passed, with coverage-navigation regressions added. Desktop 1280px and phone 390px layouts were inspected; the phone page has no horizontal overflow. A real locally generated proof was selected through the browser file picker and accepted by the public build (16 ms in that test). Invalid activation input was rejected without showing checked coverage. Search filtered the model catalogue. Reduced-motion emulation started the illustration paused. Blocking the Three.js CDN kept the SVG fallback visible and did not prevent proof verification. The three-person comprehension test remains outstanding.

The revised local UI also completed a fresh generation run in 36.5 seconds, then accepted that new proof through “Verify here” in 69 ms. Generation stages, completion controls and the unverified-answer label were inspected in the browser.

## Complete-operation research checkpoint

The separate [F20 experiment](../research/complete-operation/README.md) proves a full 1,024 × 1,024 matrix-vector operation with private activation boundaries. Its report includes phase timings, process RSS, constraints, package size, cold verification, public artifacts and local negative/isolation tests. It remains outside the website’s accepted claim. The measured scaling does not support a practical full-token claim. Native parity, full-token coverage, total system memory, full timing corpus and independent review remain open.
