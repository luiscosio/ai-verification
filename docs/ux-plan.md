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

The human usability gate is still pending: ask at least three people unfamiliar with the project to try an example, generate a proof on a prepared machine, verify a file, and explain what passed. Record time, obstacles and mistaken interpretations. Target at most one file choice and one verification action; no tensor, group, JSON-field or key selection. Installation time and warm proving time are measured separately. Any participant interpreting the present result as proof of the answer triggers a copy/design revision.

The implementation checks and first real browser/offline round trip are recorded in `docs/workspace-validation-2026-09-13.md`.

First-time installation is not yet one click. The exact registered model, native build, circuit build and matching proving key must be installed. Publishing matching proving materials and making installation reproducible are the next usability work, before packaging a desktop installer. Re-running setup generates different keys; it is not a way to install the existing registration.

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
