# AI verification

Notes, research and code on technical verification of AI compute agreements. Started Sep 10, 2026. Repository: https://github.com/luiscosio/ai-verification (public). The llama.cpp fork is a submodule pinned to its `receipts-all` branch:

```bash
git clone --recurse-submodules https://github.com/luiscosio/ai-verification
```

Model files, demo output and the built site are not tracked; `run-demo.sh` and `site/build_site.py` regenerate them. The Signal group material this work started from is kept outside the repository.

```
PLAN.md            the ZK inference PoC plan: objective, required properties, stages with exit gates, budgets, risks
TODO.md            scratch pad: what is done per stage, what is missing in priority order, the decisions still open
run-demo.sh        end-to-end demo: prove with a trace, verify without the model, replay, Lean checks, one integrity proof
demo/              separate run.* directories from run-demo.sh (receipt, trace, reports, proof)
code/              all code (see below)
docs/              the deck, the interactive explainer, the ZK PoC plan and its Stage 1 record, with the deck's sources
models/            GGUF files used for the plan's model selection (not tracked; digests in docs/stage1/backend-decision.md)
registry/          registration manifests (Stage 2): Qwen3-0.6B with digests, tensor table, tokenizer identity, execution specification, Orion and Groth16 commitments for all 168 Q4_K tensors
site/              the registry and verification page (Stage 6): static build with in-browser Groth16 verification, and a local server for Expander packages
notes/             session notes and the research sweep
```

## Code

`code/llama.cpp` is the fork `luiscosio/llama.cpp`, checked out on `receipts-all`, a local integration branch that merges the three draft pull requests open in the fork. It is built (`build/`, Metal) and the proof crate is built (`examples/receipts/zk/target/`). Everything new is under `examples/receipts/`:

| Piece | Where | PR |
|---|---|---|
| `llama-receipts` (C++): generate with a replayable sampler, write a receipt, trace every tensor into a Merkle tree, replay a receipt | `examples/receipts/receipts.cpp` | 1, branch `receipts-trace` |
| Trace verifier (Python, numpy, gguf-py and native vocabulary checker): format version, root, pinned topology, content commitments, challenge with a minimum-openings policy, graph order, edges, inputs, per-token records and logits binding, re-execution of sampled nodes with three arithmetic references | `examples/receipts/verify_trace.py` | 1 |
| Formal spec (Lean 4, no Mathlib): block formats, Q8_K quantization, integer core, Merkle tree, Fiat-Shamir sample, protocol; bound theorems; `spec-check` executable | `examples/receipts/spec/` | 2, branch `receipts-lean-spec` |
| GKR proof of one matmul node (Rust on Expander, Mersenne-31), private weights bound to a commitment registered from the GGUF, with Python glue and a circuit-versus-spec harness | `examples/receipts/zk/` | 3, branch `receipts-zk-poc` |

Each directory has its own README with formats, results and limits. Sync with upstream:

```bash
cd code/llama.cpp
gh repo sync luiscosio/llama.cpp --source ggml-org/llama.cpp --branch master
git fetch upstream && git rebase upstream/master receipts-trace && git push --force-with-lease
```

`code/llama-receipts` is the Python prototype the native port came from: rungs 1 to 3 on llama-cpp-python plus the first activation-trace implementation, 40 unit tests, two attack matrices with results (`testset/results.md`, `testset/results-trace.md`), and calibration data. `uv run pytest -q` runs the tests; `uv run python -m testset.run_matrix` and `run_trace_matrix` rerun the matrices (about ten minutes each; they need the Ollama `qwen2.5:1.5b` and `phi3:mini` blobs and the Q2_K requantization in `models/`).

Expander is used through a fork, `luiscosio/Expander` branch `macos-build`, pulled by Cargo at a pinned revision. It differs from upstream by two macOS build fixes. No local clone is kept.

## Docs

- `docs/stage1/`: Stage 1 feasibility work from Sep 13, 2026 (exit gate incomplete): the backend decision record (with the Groth16 addendum), the frozen statement stmt/v0, per-op activation ranges of three models and the script that measures them.
- `docs/stage4/`: the circuit-friendly execution mode as a reference implementation (integer-only forward pass), its agreement with llama.cpp on twenty prompts, measured bit widths, and what a whole-token proof costs.
- `docs/stage5/`: verification in isolation (sandboxed, no network, no model files) and the adversarial cases, with the script that runs them.
- [ZK inference PoC plan](PLAN.md): llama.cpp with local proof generation, open-model registration, and independent verification without model weights; stages and acceptance criteria through a full next-token proof and public verifier website.
- `docs/llama-receipts-activation-trace-secure-v2.pptx`: 17 slides. What exists, diagrams of the system, the trace, the proof pipeline and the stacked PRs, terminal screenshots of proving, verifying, the Lean spec and the one-node proof, and the road to a proof of the whole forward pass. It reflects the pinned-topology verifier and model-bound public proof inputs. `docs/deck-src/make-deck.py` regenerates it; `render-shots.py` re-renders the screenshots from the captured text in `shots/`.
- `docs/proving-the-forward-pass.html`: interactive nine-step explainer of zero-knowledge proofs for LLM inference; the demos run locally. Published copy: https://claude.ai/code/artifact/bdeefe2b-f6f3-4986-92bf-2a680b382e15

## Site

Hosted registry and verifier: **https://luiscosio.github.io/ai-verification/**. Open a locally generated `.llamaproof` file there to check its registered weight commitment in your browser. The file is not uploaded to or stored by the hosting service. The catalogue distinguishes model fingerprints from actual proof coverage; these project registrations are not signatures from the model providers.

| Model file | Hosted verification coverage |
|---|---|
| Qwen3-0.6B Q4_K_M | Integer row groups for 168 tensors; current local workspace model |
| Qwen2.5-1.5B Q4_K_M | Integer row groups for `blk.0.ffn_gate.weight` only (560 groups); other tensors not covered |
| Qwen2.5-0.5B Q4_K_M | File/tokenizer/tensor fingerprints only; no proof acceptance |

None of these registrations establishes a complete inference proof. New entries are computed from the actual GGUF with `register.py`, checked against that file, and reviewed before being committed to `registry/`. Adding a fingerprint does not enable proof verification; matching circuit commitments and pinned keys are also required.

Run `./start-workspace.sh` and open the printed local address. Choose Qwen3-0.6B, enter a short prompt, and select **Run and generate proof**. The workspace shows actual progress and cancellation, then offers one `.llamaproof` file to download or verify immediately. It runs two local generation steps and proves one integer row group; the generated answer is visibly unverified. Prompt/answer text and private traces are excluded from export, but public activations may reveal information about the prompt.

The same file can be opened in the static website or verified offline with `node site/verify-file.cjs FILE.llamaproof`. Model, tensor and group selection is automatic against the independently trusted registry. The browser reads the file locally and applies the shared shape, range, commitment and pinned-key policy. It loads snarkjs 0.7.5 from a CDN. The optional Three.js 0.180.0 illustration loads separately from a CDN and receives no proof data; it respects reduced motion, can be paused, and falls back to a static image if unavailable. The Node verifier with installed dependencies needs no network or model weights. Obtain/check registrations independently with `register.py` before installing them for offline use.

### Local setup

The launcher supplies temporary Python dependencies through uv. The prepared machine also needs Node.js, the registered `models/qwen3-0.6b-q4_k_m.gguf`, and these installed tools/materials:

```sh
cmake -S code/llama.cpp -B code/llama.cpp/build -DLLAMA_BUILD_EXAMPLES=ON
cmake --build code/llama.cpp/build --target llama-receipts -j 4
npm ci --prefix code/llama.cpp/examples/receipts/zk/groth16
```

Install the matching `r16_k1024` circuit build (`main_js/main.wasm`), `main_final.zkey` and `verification_key.json` under `code/llama.cpp/examples/receipts/zk/groth16/build/r16_k1024/`. They are present on the development machine; publishing the proving-material release assets is still pending. See `registry/circuits/README.md`. Running a new setup creates different keys and will not reproduce the existing registration. The workspace reports missing prerequisites before allowing a run; first-time installation is not yet automated.

The local companion listens on `127.0.0.1:8789`, uses one active job and an ephemeral session token, and removes private temporary traces/witness files on completion, cancellation or failure. It keeps the latest prompt, unverified text and public package in memory until another run or shutdown. The published static page has no local proving connection. Restarting the companion loses the latest run, so download anything you want to keep.

### Build and publication

`python3 site/build_site.py` rebuilds `site/index.html` and `site/artifact.html` from the trusted registry and checked-in site sources. Missing keys or mismatched materials fail with a concise error. `uv run --with fastapi --with 'uvicorn[standard]' --with python-multipart python3 site/serve.py` still serves the static page and the separate server-side Expander verification endpoint.

The older [private artifact](https://claude.ai/code/artifact/687d9b99-421b-4075-a9e2-8ea32dcdccbe) remains historical. GitHub Pages is now the hosting target. `.github/workflows/pages.yml` checks the browser/offline acceptance policy, builds a static bundle from the pinned submodule and registry, and deploys it after each push to `main`. Only the generated HTML is published; local proving endpoints, models and private traces are excluded. No publication occurs when running the builder locally. The product/research plan and usability gate are in [docs/ux-plan.md](docs/ux-plan.md).

## Notes

- `notes/session-notes-2026-09-10.md`: what's open source in the software-only verification stack, and what Attestable is building.
- `notes/session-notes-2026-09-11.md`: the activation trace, the native port, the Lean spec, the first proof; numbers and what was learned about llama.cpp on the way.
- `notes/session-notes-2026-09-12.md`: the security review of the trace verifier and the one-node proof, what changed in receipt 0.2 and trace v2, and what is still open.
- `notes/session-notes-2026-09-13.md`: Stage 1 of the ZK plan executed: what Expander does and does not provide, the model selection, the budgets, and the weights bound to a registered commitment.
- `notes/research-sweep-2026-09-10.md`: arXiv and GitHub sweep across four areas (ZK inference, recomputation and determinism, hardware and datacenter mechanisms, attestation and audit tooling), about 60 papers and 40 repos with dates, links, and maturity.


Security repair status (2026-09-13): the row-group verifier now shares range and pinned-key checks across browser and offline use. Registration/v1 replaces the previous manifest ID without changing weight commitments or Groth16 keys. Run `checks/run.sh`; see `docs/repairs-2026-09-13.md` for validation and remaining scope. A complete operation or full next-token proof is not implemented.
