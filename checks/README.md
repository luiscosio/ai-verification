# Receipt and verifier regression checks

Run `checks/run.sh` after building `llama-receipts` and installing the Groth16 directory's pinned npm dependencies. `PYTHON` defaults to the prototype's virtual environment. If it lacks `fastapi` and `python-multipart`, the runner uses `uv run --with` to supply temporary API dependencies; the first run may download packages. Set `API_PYTHON` to use a prepared runtime instead, including for offline runs. An explicitly supplied but incomplete runtime fails clearly instead of being silently replaced. The core tests use the registered Qwen3 GGUF in `models/`. The JavaScript verifier tests require no model weights, setup file, proving key or local prover build.

The command runs the existing 40 prototype tests, shared browser/offline acceptance tests, page rendering checks, registration and native vocabulary checks, quantization edge cases, demo failure handling and API concurrency/timeout/cancellation tests. Python subtests cover several invalid inputs within each test method.

Workspace checks additionally cover one-file verification, local Host/Origin/session-token boundaries, malformed requests, job concurrency/cancellation/recovery, subprocess failure/timeout, builder error messages and uv fallback selection. `node site/verify-file.cjs PROOF_FILE` verifies a `.llamaproof` envelope using the checkout's independently checked registry. The UI plan and remaining human usability checks are in `docs/ux-plan.md`.

`fixtures/groth16` contains two public proof packages for group 0 of `blk.0.attn_k.weight`, under the checked-in `r16_k1024` verification key. The honest package uses activation quants spanning -127 through 127. The adversarial package uses a consistent witness with `q8[0] = 128`; its pairing is valid and its weight commitment matches, so only the application range policy rejects it. Neither package contains private weights or a witness. Both inherit the experimental setup's limitations. Key rotation requires regenerated fixtures.

`fixtures/receipt.json` supplies prompt/response tokens and their displayed text for native vocabulary checks. It is a test receipt, not a full inference proof package.

Additional integration checks:

```sh
# Full local demo; each invocation gets a fresh demo/run.* directory and fails on missing stages.
./run-demo.sh

# Independent verification with real sandbox controls (macOS; run outside another sandbox).
bash docs/stage5/verify_isolated.sh registry/circuits/r16_k1024 registry/qwen3-0.6b-q4_k_m/manifest.json blk.0.attn_k.weight 0 PACKAGE_DIR

# Whole F20 reference comparison, not a proof of inference.
bash docs/stage4/agreement.sh models/qwen3-0.6b-q4_k_m.gguf docs/stage4/prompts.txt /tmp/receipts-agreement
```

An offline verifier uses `code/llama.cpp/examples/receipts/zk/groth16/verify_package.cjs KEY MANIFEST TENSOR GROUP PACKAGE_DIR`. The manifest and key must come from an independently trusted registration. Calling snarkjs's pairing command alone is insufficient: it omits the application's shape, range and registration policies.
