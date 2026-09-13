# Attack test set results

Model under test: qwen2.5 1.5B instruct (Ollama Q4_K_M blob). Prompts: 8. Tokens per prompt: up to 48. Sampler: T=0.7, top_k=40, top_p=0.95, seed=1234. Machine: arm64 macOS-26.6.2-arm64-arm-64bit-Mach-O. Generated 2026-09-10.

| Case | Expected | Correct | Token match (mean / min / max) | Logits hash match | Mean abs dlogprob | Truncated | Verdict reasons | s |
|---|---|---|---|---|---|---|---|---|
| H1 honest / gpu prove, gpu verify, incremental | accept | 8/8 | 1.000 / 1.000 / 1.000 | 1.000 | 0.0000 | 0 | ok | 26.2 |
| H2 honest / gpu prove, gpu verify, batched replay | accept | 6/8 | 0.984 / 0.958 / 1.000 | 0.018 | 0.0047 | 0 | ok; token match 0.958 < 0.97 | 18.7 |
| H3 honest / gpu prove, cpu verify | accept | 1/8 | 0.904 / 0.792 / 0.979 | 0.000 | 0.0679 | 0 | ok; token match 0.792 < 0.97; token match 0.875 < 0.97; token match 0.896 < 0.97; token match 0.938 < 0.97; token match 0.958 < 0.97 | 24.9 |
| H4 honest / cpu 8 threads prove, cpu 4 threads verify | accept | 8/8 | 1.000 / 1.000 / 1.000 | 1.000 | 0.0000 | 0 | ok | 27.2 |
| A1 cheaper quant served (Q2_K), claims Q4_K_M | reject | 8/8 | 0.445 / 0.271 / 0.667 | 0.000 | 0.7573 | 78 | 10 claimed tokens outside the sampler's support; 11 claimed tokens outside the sampler's support; 12 claimed tokens outside the sampler's support; 3 claimed tokens outside the sampler's support; 8 claimed tokens outside the sampler's support | 22.9 |
| A2 different model served (phi3), claims qwen | reject | 8/8 | 0.057 / 0.000 / 0.146 | 0.000 | 2.1420 | 337 | 34 claimed tokens outside the sampler's support; 36 claimed tokens outside the sampler's support; 40 claimed tokens outside the sampler's support; 44 claimed tokens outside the sampler's support; 45 claimed tokens outside the sampler's support; 46 claimed tokens outside the sampler's support; 47 claimed tokens outside the sampler's support | 25.2 |
| A3 hidden system prompt | reject | 8/8 | 0.737 / 0.562 / 0.896 | 0.000 | 0.2729 | 13 | 2 claimed tokens outside the sampler's support; 9 claimed tokens outside the sampler's support; token match 0.625 < 0.97; token match 0.646 < 0.97; token match 0.771 < 0.97; token match 0.854 < 0.97; token match 0.896 < 0.97 | 23.0 |
| A4 sampler tamper: ran at T=1.3, claims T=0.7 | reject | 8/8 | 0.594 / 0.354 / 0.938 | 1.000 | 0.3243 | 38 | 3 claimed tokens outside the sampler's support; 4 claimed tokens outside the sampler's support; 5 claimed tokens outside the sampler's support; 6 claimed tokens outside the sampler's support; 8 claimed tokens outside the sampler's support; token match 0.938 < 0.97 | 24.9 |
| A5 sampler tamper: ran greedy, claims T=0.7 seeded | reject | 8/8 | 0.831 / 0.708 / 0.979 | 1.000 | 0.2464 | 0 | mean |dlogprob| 0.115 > 0.1; token match 0.708 < 0.97; token match 0.750 < 0.97; token match 0.812 < 0.97; token match 0.875 < 0.97; token match 0.896 < 0.97; token match 0.917 < 0.97 | 24.9 |
| A6 seed tamper: ran seed 1234, claims seed 999 | reject | 7/8 | 0.781 / 0.542 / 0.979 | 1.000 | 0.0000 | 0 | ok; token match 0.542 < 0.97; token match 0.562 < 0.97; token match 0.750 < 0.97; token match 0.812 < 0.97; token match 0.854 < 0.97; token match 0.938 < 0.97 | 24.5 |
| A7 token edit after signing, not re-signed | reject | 8/8 | 0.865 / 0.812 / 0.917 | 0.354 | 0.1073 | 16 | signature | 22.8 |
| A8 token edit, re-signed with the prover's key | reject | 8/8 | 0.865 / 0.812 / 0.917 | 0.354 | 0.1073 | 16 | 1 claimed tokens outside the sampler's support; 2 claimed tokens outside the sampler's support; 3 claimed tokens outside the sampler's support; 4 claimed tokens outside the sampler's support; token match 0.875 < 0.97 | 23.0 |

Notes:

- H2 honest / gpu prove, gpu verify, batched replay: prefill kernels differ from decode kernels; measures batch-invariance
- H3 honest / gpu prove, cpu verify: cross-backend drift
- A1 cheaper quant served (Q2_K), claims Q4_K_M: same weights requantized to Q2_K; receipt copies the honest model's hashes
- A2 different model served (phi3), claims qwen: tokenizers differ, so the claimed prompt tokens are qwen's and the response tokens are phi3's
- A3 hidden system prompt: model saw a prefix the receipt omits
- A8 token edit, re-signed with the prover's key: key compromise; only replay can catch it

Calibration: lowest honest token-match rate 0.792; highest attack token-match rate 0.979. Current accept threshold 0.97.
