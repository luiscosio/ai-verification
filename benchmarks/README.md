# Measurements and regression tests

Completed results: [September 13 four-model report](results/2026-09-13/README.md), including original failures, repaired regressions, throughput charts, raw resource samples, public proofs and CI evidence.

Run the heavy suites sequentially on an otherwise idle machine. The corpus is public and synthetic; it contains factual, arithmetic, code, JSON, Spanish, Chinese, Arabic, combining characters and emoji, whitespace, HTML-like text, repetition and longer-context requests. This measures execution and verification, not answer quality, instruction following or structured-answer completeness.

Install the locked developer environment with `uv sync --project tools/workspace --locked --group dev`. Install the exact registered Qwen3 model and proving materials with `./setup-workspace.sh --all-circuits`. Native inference also supports the registered Qwen2.5 0.5B and 1.5B files and a local Phi-3 Mini file. The model paths and SHA-256 checks are in `run_matrix.py`; use `--models qwen3-0.6b` when only the default model is available. Supply `--model qwen2.5-1.5b=/path/to/model.gguf` to use a different local path for a selected model. The optional larger models are not downloaded automatically. Phi-3 has no trusted proof registration here.

```sh
uv run --project tools/workspace --locked --group dev python benchmarks/run_matrix.py --out /tmp/native-matrix
uv run --project tools/workspace --locked --group dev python benchmarks/run_matrix.py --suite row-proofs --models qwen3-0.6b,qwen2.5-1.5b --out /tmp/row-proofs
uv run --project tools/workspace --locked --group dev python benchmarks/run_extended.py --suite throughput --out /tmp/throughput
uv run --project tools/workspace --locked --group dev python benchmarks/run_extended.py --suite native-negatives --out /tmp/native-negatives
# Install the existing research materials first, following research/complete-operation/README.md.
uv run --project tools/workspace --locked --group dev python benchmarks/run_extended.py --suite complete-operation --out /tmp/complete-operations
```

Each output directory must be new. Commands stop unsuccessfully when checks fail; the native matrix retains completed cases and continues collecting failures. Private traces, inputs and witnesses live in temporary directories and are removed. Public metrics, token IDs from synthetic prompts, proofs and registrations may be retained. Do not benchmark personal prompts with this public reporting workflow.

The native matrix contains 208 fresh generation jobs, 208 vocabulary/content checks and 104 same-configuration CPU replays: four models, 12 prompts, two thread counts, two repeats, plus temperature 0.7 on two prompts. Repeated seed/configuration outputs are compared exactly. Replay explicitly pins CPU, thread, context and batch settings; the native replay command does not infer all of these settings from a receipt. Eight requested generation steps are a short-request benchmark, not sustained decoding throughput.

The row-proof matrix produces 18 proofs: three separated row groups per operation, across K=1024,1536,2048,3072 and two models. Each traced generation is paired with the same request without tracing; tokens are compared and elapsed capture overhead is recorded. It runs the shared registration/range policy and changed-sum/changed-group negative controls. The 1.5B path is a developer benchmark; it does not add that model to the local website picker. The 18 exported `.llamaproof` files are independently verified with the ordinary file verifier, and changed-group packages must be rejected. Exported activations come from the public synthetic corpus. These proofs cover integer row groups, not the generated answer.

`llama-bench` separately measures prompt processing at 32/128/512 tokens and decoding at 32/128 tokens, with three repeats and warmup, at two thread counts for four models (40 configurations, 120 timing samples). Its throughput excludes model loading, receipt generation, tokenization and sampling. Process resource measurements enclose the complete five-configuration invocation, so memory is attributable to the model/thread invocation, not to a particular prompt length.

The experimental complete-operation suite proves three different normalized token embeddings (IDs 0, 198 and 512). Each package contains all 65 component proofs for one F20 1024×1024 matrix operation. Input preparation and complete token generation remain outside that proof. Token ID selection is benchmark metadata, not a claim certified by the proof.

`measure.py` collects elapsed and CPU time, OS peak process RSS, 50 ms process-tree RSS samples, process counts, and system available memory/swap. Summed RSS can count shared pages more than once; sampling can miss brief peaks. Other applications affect system memory and cache state. These runs do not measure GPU allocations, unique physical memory, energy, or a cold filesystem cache. OS peak process RSS and sampled summed process-tree RSS are separate measures.

## Automated checks

- `bash checks/portable.sh`: model-free Python checks with branch coverage, seeded proof mutations, resource-monitor cleanup tests and the public complete-operation package.
- `API_PYTHON="$PWD/tools/workspace/.venv/bin/python" bash checks/run.sh`: the full existing local regression suite, including native model checks and the prototype's own environment.
- `uv run --project tools/workspace --locked --group dev python checks/check_live_workspace.py`: real local API generation, download and independent file verification.
- `node checks/check_adversarial.cjs 3000`: longer seeded malformed-proof stress test; 300 is the CI default.

CI runs portable and prototype checks on Linux/macOS with Node 22/24, real Qwen3 generation and fresh proofs on Linux, and Chromium/Firefox/WebKit plus mobile Chromium UI checks. A separate Linux job calculates real circuit witnesses at quantization and rounding boundaries and rejects invalid private values. All are required before Pages deployment. Report-only changes under `benchmarks/results/`, plus the root README/TODO and benchmark guide, do not redeploy the unchanged verifier; pull requests still run checks. Browser checks block non-local network requests and verify the actual bundled cryptography. Coverage reports, browser failure traces and public benchmark metrics are uploaded as CI artifacts. Large multi-model performance and experimental proving runs remain explicit local benchmarks; shared runners are not reliable performance baselines.

The saved `unicode-regression-plan.json` reruns all 12 prompts on all four models at eight threads, then repeats the Unicode cases at two/eight threads (60 jobs). Run it with `run_matrix.py --case-plan benchmarks/unicode-regression-plan.json --out /tmp/unicode-regression`.

For a complete process-tree memory profile, run `benchmarks/observe.py --pid YOUR_RUNNER_PID --out /tmp/job-tree.jsonl` in the locked developer environment. This read-only observer includes the benchmark driver and its children, at 100 ms intervals, including time spent parsing traces between measured subprocesses. It does not control or terminate the observed processes. Sampled CPU values cover live processes only; they are not cumulative CPU accounting.
