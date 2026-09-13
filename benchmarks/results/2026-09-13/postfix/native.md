# Four-model native matrix

Machine: Apple M5; 10 logical CPUs; 24 GiB RAM. CPU backend only.

Completed 60 / 60 cases; 60 passed. Fresh processes; eight requested generation steps.

| Check | Passed | Executed |
|---|---|---|
| content | 60 | 60 |
| model_identity | 60 | 60 |
| repeat_tokens_match | 8 | 8 |
| replay | 52 | 52 |

| Model | Threads | Jobs | Median s | p95 s | Max OS RSS GiB | Max sampled tree RSS GiB |
|---|---|---|---|---|---|---|
| phi3-mini | 2 | 2 | 11.17 | 11.50 | 4.46 | 4.46 |
| phi3-mini | 8 | 13 | 10.71 | 12.13 | 4.51 | 4.51 |
| qwen2.5-0.5b | 2 | 2 | 2.79 | 2.81 | 0.78 | 0.68 |
| qwen2.5-0.5b | 8 | 13 | 2.72 | 2.98 | 0.78 | 0.74 |
| qwen2.5-1.5b | 2 | 2 | 5.27 | 5.31 | 1.98 | 1.98 |
| qwen2.5-1.5b | 8 | 13 | 5.21 | 5.81 | 2.03 | 2.03 |
| qwen3-0.6b | 2 | 2 | 2.35 | 2.36 | 0.96 | 0.96 |
| qwen3-0.6b | 8 | 13 | 2.32 | 2.58 | 0.98 | 0.98 |

Latency includes model loading, hashing, prompt processing, sampling and receipt creation. Prompts differ in length; p95 combines that workload variation with timing variation. RSS columns are peaks across jobs, not per-model steady-state requirements.

Greedy cross-thread token agreement: 4 / 4 prompt/model pairs. This is an observation, not a cross-backend guarantee.

## Per-prompt latency

| Model | Prompt | Input tokens | 2 threads median s | 8 threads median s |
|---|---|---|---|---|
| phi3-mini | adversarial-text | 22 | — | 10.50 |
| phi3-mini | arabic | 36 | — | 10.67 |
| phi3-mini | arithmetic | 15 | — | 10.51 |
| phi3-mini | chinese | 24 | — | 10.89 |
| phi3-mini | code | 22 | — | 10.72 |
| phi3-mini | fact | 5 | — | 11.01 |
| phi3-mini | json | 19 | — | 10.53 |
| phi3-mini | long-context | 460 | — | 12.93 |
| phi3-mini | repetition | 103 | — | 11.60 |
| phi3-mini | spanish | 14 | — | 10.51 |
| phi3-mini | unicode | 26 | 11.17 | 10.62 |
| phi3-mini | whitespace | 17 | — | 11.31 |
| qwen2.5-0.5b | adversarial-text | 18 | — | 2.82 |
| qwen2.5-0.5b | arabic | 17 | — | 2.75 |
| qwen2.5-0.5b | arithmetic | 14 | — | 2.67 |
| qwen2.5-0.5b | chinese | 8 | — | 2.65 |
| qwen2.5-0.5b | code | 17 | — | 2.68 |
| qwen2.5-0.5b | fact | 5 | — | 2.86 |
| qwen2.5-0.5b | json | 18 | — | 2.71 |
| qwen2.5-0.5b | long-context | 459 | — | 3.15 |
| qwen2.5-0.5b | repetition | 102 | — | 2.86 |
| qwen2.5-0.5b | spanish | 13 | — | 2.72 |
| qwen2.5-0.5b | unicode | 24 | 2.79 | 2.70 |
| qwen2.5-0.5b | whitespace | 14 | — | 2.77 |
| qwen2.5-1.5b | adversarial-text | 18 | — | 5.21 |
| qwen2.5-1.5b | arabic | 17 | — | 5.34 |
| qwen2.5-1.5b | arithmetic | 14 | — | 5.17 |
| qwen2.5-1.5b | chinese | 8 | — | 5.12 |
| qwen2.5-1.5b | code | 17 | — | 5.24 |
| qwen2.5-1.5b | fact | 5 | — | 5.24 |
| qwen2.5-1.5b | json | 18 | — | 5.26 |
| qwen2.5-1.5b | long-context | 459 | — | 6.46 |
| qwen2.5-1.5b | repetition | 102 | — | 5.37 |
| qwen2.5-1.5b | spanish | 13 | — | 5.10 |
| qwen2.5-1.5b | unicode | 24 | 5.27 | 5.18 |
| qwen2.5-1.5b | whitespace | 14 | — | 5.12 |
| qwen3-0.6b | adversarial-text | 18 | — | 2.30 |
| qwen3-0.6b | arabic | 17 | — | 2.31 |
| qwen3-0.6b | arithmetic | 14 | — | 2.33 |
| qwen3-0.6b | chinese | 8 | — | 2.30 |
| qwen3-0.6b | code | 17 | — | 2.31 |
| qwen3-0.6b | fact | 5 | — | 2.32 |
| qwen3-0.6b | json | 18 | — | 2.35 |
| qwen3-0.6b | long-context | 459 | — | 2.84 |
| qwen3-0.6b | repetition | 102 | — | 2.41 |
| qwen3-0.6b | spanish | 13 | — | 2.30 |
| qwen3-0.6b | unicode | 24 | 2.35 | 2.33 |
| qwen3-0.6b | whitespace | 14 | — | 2.35 |

## Measurement limits

- Fresh process for each measurement; filesystem cache is uncontrolled
- Summed RSS can double-count shared mappings; sampled peaks can miss short spikes
- CPU metrics from OS time cover its child command; sampled CPU is live processes only
- System available/swap values include other applications; changes are not attributed to this test
- CPU backend only; accelerator allocations and energy not measured
