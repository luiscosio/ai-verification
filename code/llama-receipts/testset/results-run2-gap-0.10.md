# Attack test set results

Model under test: qwen2.5 1.5B instruct (Ollama Q4_K_M blob). Prompts: 8. Tokens per prompt: up to 48. Sampler: T=0.7, top_k=40, top_p=0.95, seed=1234. Machine: arm64 macOS-26.6.2-arm64-arm-64bit-Mach-O. Generated 2026-09-10.

| Case | Expected | Correct | Token match (mean / min / max) | Logits hash match | Mean abs dlogprob | Truncated | Hard mismatches (max gap) | Verdict reasons | s |
|---|---|---|---|---|---|---|---|---|---|
| H1 honest / gpu prove, gpu verify, incremental | accept | 8/8 | 1.000 / 1.000 / 1.000 | 1.000 | 0.0000 | 0 | 0 (–) | bit-exact replay | 18.2 |
| H2 honest / gpu prove, gpu verify, batched replay | accept | 8/8 | 0.984 / 0.958 / 1.000 | 0.018 | 0.0047 | 0 | 0 (0.068) | within backend drift | 14.2 |
| H3 honest / gpu prove, cpu verify | accept | 4/8 | 0.904 / 0.792 / 0.979 | 0.000 | 0.0679 | 0 | 8 (0.429) | 1 draws more than 0.10 of CDF mass from the claimed token; 3 draws more than 0.10 of CDF mass from the claimed token; within backend drift | 18.5 |
| H4 honest / cpu 8 threads prove, cpu 4 threads verify | accept | 8/8 | 1.000 / 1.000 / 1.000 | 1.000 | 0.0000 | 0 | 0 (–) | bit-exact replay | 20.0 |
| A1 cheaper quant served (Q2_K), claims Q4_K_M | reject | 8/8 | 0.445 / 0.271 / 0.667 | 0.000 | 0.7573 | 78 | 108 (0.893) | 10 claimed tokens outside the sampler's support; 11 claimed tokens outside the sampler's support; 12 claimed tokens outside the sampler's support; 3 claimed tokens outside the sampler's support; 8 claimed tokens outside the sampler's support | 18.3 |
| A2 different model served (phi3), claims qwen | reject | 8/8 | 0.057 / 0.000 / 0.146 | 0.000 | 2.1420 | 337 | 20 (0.957) | 34 claimed tokens outside the sampler's support; 36 claimed tokens outside the sampler's support; 40 claimed tokens outside the sampler's support; 44 claimed tokens outside the sampler's support; 45 claimed tokens outside the sampler's support; 46 claimed tokens outside the sampler's support; 47 claimed tokens outside the sampler's support | 17.9 |
| A3 hidden system prompt | reject | 8/8 | 0.737 / 0.562 / 0.896 | 0.000 | 0.2729 | 13 | 56 (0.794) | 11 draws more than 0.10 of CDF mass from the claimed token; 2 claimed tokens outside the sampler's support; 3 draws more than 0.10 of CDF mass from the claimed token; 4 draws more than 0.10 of CDF mass from the claimed token; 7 draws more than 0.10 of CDF mass from the claimed token; 9 claimed tokens outside the sampler's support | 18.2 |
| A4 sampler tamper: ran at T=1.3, claims T=0.7 | reject | 8/8 | 0.594 / 0.354 / 0.938 | 1.000 | 0.3243 | 38 | 101 (0.507) | 2 draws more than 0.10 of CDF mass from the claimed token; 3 claimed tokens outside the sampler's support; 4 claimed tokens outside the sampler's support; 5 claimed tokens outside the sampler's support; 6 claimed tokens outside the sampler's support; 8 claimed tokens outside the sampler's support | 17.7 |
| A5 sampler tamper: ran greedy, claims T=0.7 seeded | reject | 7/8 | 0.831 / 0.708 / 0.979 | 1.000 | 0.2464 | 0 | 46 (0.683) | 13 draws more than 0.10 of CDF mass from the claimed token; 3 draws more than 0.10 of CDF mass from the claimed token; 4 draws more than 0.10 of CDF mass from the claimed token; 6 draws more than 0.10 of CDF mass from the claimed token; 8 draws more than 0.10 of CDF mass from the claimed token; 9 draws more than 0.10 of CDF mass from the claimed token; bit-exact replay | 17.7 |
| A6 seed tamper: ran seed 1234, claims seed 999 | reject | 8/8 | 0.781 / 0.542 / 0.979 | 1.000 | 0.0000 | 0 | 73 (0.933) | 1 draws more than 0.10 of CDF mass from the claimed token; 11 draws more than 0.10 of CDF mass from the claimed token; 19 draws more than 0.10 of CDF mass from the claimed token; 20 draws more than 0.10 of CDF mass from the claimed token; 6 draws more than 0.10 of CDF mass from the claimed token; 7 draws more than 0.10 of CDF mass from the claimed token; 8 draws more than 0.10 of CDF mass from the claimed token | 17.7 |
| A7 token edit after signing, not re-signed | reject | 8/8 | 0.865 / 0.812 / 0.917 | 0.354 | 0.1073 | 16 | 21 (0.744) | signature | 17.8 |
| A8 token edit, re-signed with the prover's key | reject | 8/8 | 0.865 / 0.812 / 0.917 | 0.354 | 0.1073 | 16 | 21 (0.744) | 1 claimed tokens outside the sampler's support; 2 claimed tokens outside the sampler's support; 3 claimed tokens outside the sampler's support; 3 draws more than 0.10 of CDF mass from the claimed token; 4 claimed tokens outside the sampler's support | 17.7 |

Notes:

- H2 honest / gpu prove, gpu verify, batched replay: prefill kernels differ from decode kernels; measures batch-invariance
- H3 honest / gpu prove, cpu verify: cross-backend drift
- A1 cheaper quant served (Q2_K), claims Q4_K_M: same weights requantized to Q2_K; receipt copies the honest model's hashes
- A2 different model served (phi3), claims qwen: tokenizers differ, so the claimed prompt tokens are qwen's and the response tokens are phi3's
- A3 hidden system prompt: model saw a prefix the receipt omits
- A8 token edit, re-signed with the prover's key: key compromise; only replay can catch it

Calibration: lowest honest token-match rate 0.792; highest attack token-match rate 0.979; largest honest draw gap 0.4289 (hard-mismatch threshold 0.1).
