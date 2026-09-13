# Proof workspace validation — September 13, 2026

The first usable row-group proof workflow is implemented locally. No full-operation/full-token proof, production setup, independent registrar approval or new public deployment is claimed.

## Changes

- `checks/run.sh` uses temporary uv dependencies when the default Python lacks FastAPI or python-multipart. An explicit `API_PYTHON` override is honored and checked.
- The Groth16 driver invokes the shared registration/range policy when a manifest is supplied; unregistered runs explicitly identify their narrower pairing/local-commitment checks. It emits real progress stages for the local companion.
- Site build failures, including missing keys, print a concise error and exit nonzero.
- The local companion controls the native executable and proof helper, checks the model digest, picks the supported operation, offers cancellation and exports one public proof file. Temporary private traces and witness inputs are removed after the job.
- Browser and offline verification consume the same strict file envelope and trusted registry. The interface distinguishes coverage, privacy, setup and registration trust; it never marks generated text as proven.
- The documentation records the native vocabulary dependency and fixed registration/v1 execution policy. New execution semantics must be versioned; changed registration materials cannot silently replace the installed trust anchor.

## Automated validation

The final full `checks/run.sh` run passed: 40 prototype tests; 20 shared Groth16 regressions; 9 package-envelope cases; 3 application-renderer cases at that point; 9 core test methods; 5 Expander API methods; and 9 workspace/tool methods. After the final rejection-copy adjustment, the JavaScript suite was rerun and passed with 4 application-renderer cases. Both repositories pass whitespace/diff checks; Python and JavaScript syntax checks pass.

Workspace tests cover Host/Origin/session-token boundaries, malformed and oversized requests, unknown jobs, one-job concurrency, unavailable downloads, immediate cancellation, recovery, process timeout/failure, progress events, clear builder errors, uv fallback/explicit override selection and honest/adversarial one-file CLI verification.

The first complete test run caught a cross-language encoding error in an attempted registration-ID rehash: Python and JavaScript serialize some numeric metadata differently. The offline file verifier now consistently consumes the independently checked, operator-installed registry, checks the registered verifier-source digest, and applies the shared pinned-key policy. It does not invent a second registration-ID encoding. This is the same trust model as the validated static site bundle.

## Real run and browser checks

On the development machine, with registered Qwen3-0.6B Q4_K_M, prompt `The capital of France is`, two generated steps, one `r16_k1024` row group:

| Measurement | Observed |
|---|---:|
| Total local job | 29.0 s |
| Model digest check | 0.218 s |
| Inference and trace capture together | 17.867 s |
| Circuit witness generation | 0.33 s |
| Groth16 proving | 4.09 s |
| Driver verification | 0.20 s |
| Compact exported envelope | 43,932 bytes |
| Initial in-browser verification | 88 ms |
| Reopened file, same browser | 74 ms |
| Separate verifier-only page | 71 ms |

These are observations from one warm development-machine run, not benchmarks or performance guarantees. Phase times omit some orchestration/loading work and do not sum to total time. The download uses indented JSON and is larger than the compact envelope measurement. Peak memory and separate capture overhead were not measured.

The run produced unverified text ` Paris,`. The file was accepted by the offline CLI and by the independent static verifier preview through its file picker. The adversarial bundled proof was rejected for its invalid activation range. A second local run was cancelled from the interface; the controls recovered and allowed another run. Keyboard activation of the invalid example produced the intended plain-language rejection, with focus moved to the result.

Inspected the desktop two-column layout at 1200 pixels, the default narrow embedded pane, and a 390-pixel phone-width layout. Long technical identities stay in expandable content and wrap. This is a layout/interaction check, not a complete accessibility audit or a novice usability study.

Browser download event hooks timed out without console errors. Actual `.llamaproof` files nevertheless appeared in Downloads; a downloaded example passed independent CLI verification. File-picker reads and verification were checked directly in the browser. No externally hosted page was modified.

## Release handoff

The rebuilt `site/index.html` and `site/artifact.html` remain generated local outputs. The existing private preview is still stale. Commit and push the fork first, bump and commit the parent's submodule pin together with the registry and workspace, then rebuild from that checkout and republish the private artifact. See `docs/ux-plan.md` for the exact order and outstanding first-install, usability and research gates.
