# Four-model native matrix

Machine: Apple M5; 10 logical CPUs; 24 GiB RAM. CPU backend only.

Completed 208 / 208 cases; 204 passed. Fresh processes; eight requested generation steps.

| Check | Passed | Executed |
|---|---|---|
| content | 204 | 204 |
| model_identity | 204 | 204 |
| repeat_tokens_match | 102 | 102 |
| replay | 102 | 102 |

| Model | Threads | Jobs | Median s | p95 s | Max OS RSS GiB | Max sampled tree RSS GiB |
|---|---|---|---|---|---|---|
| phi3-mini | 2 | 24 | 10.70 | 15.99 | 4.51 | 4.51 |
| phi3-mini | 8 | 28 | 10.42 | 12.25 | 4.51 | 4.51 |
| qwen2.5-0.5b | 2 | 24 | 2.75 | 3.17 | 0.78 | 0.78 |
| qwen2.5-0.5b | 8 | 28 | 2.68 | 3.03 | 0.79 | 0.78 |
| qwen2.5-1.5b | 2 | 24 | 5.25 | 7.66 | 2.03 | 2.03 |
| qwen2.5-1.5b | 8 | 28 | 5.15 | 6.17 | 2.03 | 2.03 |
| qwen3-0.6b | 2 | 24 | 2.35 | 3.33 | 0.98 | 0.98 |
| qwen3-0.6b | 8 | 28 | 2.33 | 2.75 | 0.98 | 0.98 |

Latency includes model loading, hashing, prompt processing, sampling and receipt creation. Prompts differ in length; p95 combines that workload variation with timing variation. RSS columns are peaks across jobs, not per-model steady-state requirements.

Greedy cross-thread token agreement: 46 / 47 prompt/model pairs. This is an observation, not a cross-backend guarantee.

## Per-prompt latency

| Model | Prompt | Input tokens | 2 threads median s | 8 threads median s |
|---|---|---|---|---|
| phi3-mini | adversarial-text | 22 | 11.02 | 10.42 |
| phi3-mini | arabic | 36 | 10.64 | 10.41 |
| phi3-mini | arithmetic | 15 | 10.43 | 10.35 |
| phi3-mini | chinese | 24 | 11.02 | 10.60 |
| phi3-mini | code | 22 | 10.92 | 10.33 |
| phi3-mini | fact | 5 | 10.70 | 11.08 |
| phi3-mini | json | 19 | 10.69 | 10.32 |
| phi3-mini | long-context | 460 | 16.87 | 13.29 |
| phi3-mini | repetition | 103 | 12.04 | 10.60 |
| phi3-mini | spanish | 14 | 10.68 | 10.29 |
| phi3-mini | unicode | unavailable | 10.58 | 10.92 |
| phi3-mini | whitespace | 17 | 10.32 | 10.25 |
| qwen2.5-0.5b | adversarial-text | 18 | 2.75 | 2.67 |
| qwen2.5-0.5b | arabic | 17 | 2.73 | 2.71 |
| qwen2.5-0.5b | arithmetic | 14 | 2.79 | 2.77 |
| qwen2.5-0.5b | chinese | 8 | 2.66 | 2.81 |
| qwen2.5-0.5b | code | 17 | 2.73 | 2.71 |
| qwen2.5-0.5b | fact | 5 | 2.71 | 2.68 |
| qwen2.5-0.5b | json | 18 | 2.76 | 2.68 |
| qwen2.5-0.5b | long-context | 459 | 3.24 | 3.11 |
| qwen2.5-0.5b | repetition | 102 | 2.80 | 2.86 |
| qwen2.5-0.5b | spanish | 13 | 2.72 | 2.67 |
| qwen2.5-0.5b | unicode | 24 | 2.84 | 2.64 |
| qwen2.5-0.5b | whitespace | 14 | 2.77 | 2.79 |
| qwen2.5-1.5b | adversarial-text | 18 | 5.24 | 5.18 |
| qwen2.5-1.5b | arabic | 17 | 5.14 | 5.53 |
| qwen2.5-1.5b | arithmetic | 14 | 5.27 | 5.17 |
| qwen2.5-1.5b | chinese | 8 | 5.21 | 5.13 |
| qwen2.5-1.5b | code | 17 | 5.20 | 5.08 |
| qwen2.5-1.5b | fact | 5 | 5.16 | 5.06 |
| qwen2.5-1.5b | json | 18 | 5.36 | 5.13 |
| qwen2.5-1.5b | long-context | 459 | 8.22 | 6.25 |
| qwen2.5-1.5b | repetition | 102 | 5.77 | 5.51 |
| qwen2.5-1.5b | spanish | 13 | 5.10 | 5.15 |
| qwen2.5-1.5b | unicode | 24 | 5.23 | 5.47 |
| qwen2.5-1.5b | whitespace | 14 | 5.13 | 5.32 |
| qwen3-0.6b | adversarial-text | 18 | 2.35 | 2.29 |
| qwen3-0.6b | arabic | 17 | 2.39 | 2.45 |
| qwen3-0.6b | arithmetic | 14 | 2.32 | 2.29 |
| qwen3-0.6b | chinese | 8 | 2.37 | 2.26 |
| qwen3-0.6b | code | 17 | 2.33 | 2.38 |
| qwen3-0.6b | fact | 5 | 2.40 | 2.33 |
| qwen3-0.6b | json | 18 | 2.33 | 2.35 |
| qwen3-0.6b | long-context | 459 | 3.53 | 2.86 |
| qwen3-0.6b | repetition | 102 | 2.58 | 2.38 |
| qwen3-0.6b | spanish | 13 | 2.37 | 2.29 |
| qwen3-0.6b | unicode | 24 | 2.35 | 2.43 |
| qwen3-0.6b | whitespace | 14 | 2.32 | 2.41 |

## Measurement limits

- Fresh process for each measurement; filesystem cache is uncontrolled
- Summed RSS can double-count shared mappings; sampled peaks can miss short spikes
- CPU metrics from OS time cover its child command; sampled CPU is live processes only
- System available/swap values include other applications; changes are not attributed to this test
- CPU backend only; accelerator allocations and energy not measured

## Failures

- {'model': 'phi3-mini', 'prompt': 'unicode', 'threads': 2, 'repeat': 1, 'temperature': 0}: Generation failed: W load_arch_hparams: Phi SWA is currently disabled - results might be suboptimal for some models (see https://github.com/ggml-org/llama.cpp/pull/13676)
0.09.382.485 W load: control-looking token:      2 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.09.705.112 I cmn          init: llama threadpool init, n_threads = 2
0.10.323.064 I generated 8 tokens in 0.62 s
0.10.325.993 E [json.exception.type_error.316] incomplete UTF-8 string; last byte: 0xAF

- {'model': 'phi3-mini', 'prompt': 'unicode', 'threads': 8, 'repeat': 1, 'temperature': 0}: Generation failed: W load_arch_hparams: Phi SWA is currently disabled - results might be suboptimal for some models (see https://github.com/ggml-org/llama.cpp/pull/13676)
0.09.463.218 W load: control-looking token:      2 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.09.879.394 I cmn          init: llama threadpool init, n_threads = 8
0.10.667.742 I generated 8 tokens in 0.79 s
0.10.668.387 E [json.exception.type_error.316] incomplete UTF-8 string; last byte: 0xAF

- {'model': 'phi3-mini', 'prompt': 'unicode', 'threads': 2, 'repeat': 0, 'temperature': 0}: Generation failed: W load_arch_hparams: Phi SWA is currently disabled - results might be suboptimal for some models (see https://github.com/ggml-org/llama.cpp/pull/13676)
0.09.634.924 W load: control-looking token:      2 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.10.003.652 I cmn          init: llama threadpool init, n_threads = 2
0.10.718.833 I generated 8 tokens in 0.72 s
0.10.719.724 E [json.exception.type_error.316] incomplete UTF-8 string; last byte: 0xAF

- {'model': 'phi3-mini', 'prompt': 'unicode', 'threads': 8, 'repeat': 0, 'temperature': 0}: Generation failed: W load_arch_hparams: Phi SWA is currently disabled - results might be suboptimal for some models (see https://github.com/ggml-org/llama.cpp/pull/13676)
0.09.599.850 W load: control-looking token:      2 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.10.144.291 I cmn          init: llama threadpool init, n_threads = 8
0.11.011.620 I generated 8 tokens in 0.86 s
0.11.012.575 E [json.exception.type_error.316] incomplete UTF-8 string; last byte: 0xAF

