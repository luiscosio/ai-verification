# Attack test set results

Model under test: qwen2.5 1.5B instruct (Ollama Q4_K_M blob). Prompts: 8. Tokens per prompt: up to 48. Sampler: T=0.7, top_k=40, top_p=0.95, seed=1234. Machine: arm64 macOS-26.6.2-arm64-arm-64bit-Mach-O. Generated 2026-09-10.

| Case | Expected | Correct | Token match (mean / min / max) | Logits hash match | Mean abs dlogprob | Truncated | Worst mean gap | Worst max gap | Verdict reasons | s |
|---|---|---|---|---|---|---|---|---|---|---|
| H1 honest / gpu prove, gpu verify, incremental | accept | 8/8 | 1.000 / 1.000 / 1.000 | 1.000 | 0.0000 | 0 | 0.0000 | – | bit-exact replay | 17.6 |
| H2 honest / gpu prove, gpu verify, batched replay | accept | 8/8 | 0.984 / 0.958 / 1.000 | 0.018 | 0.0047 | 0 | 0.0014 | 0.068 | within backend drift | 13.8 |
| H3 honest / gpu prove, cpu verify | accept | 8/8 | 0.904 / 0.792 / 0.979 | 0.000 | 0.0679 | 0 | 0.0217 | 0.429 | within backend drift | 18.2 |
| H4 honest / cpu 8 threads prove, cpu 4 threads verify | accept | 8/8 | 1.000 / 1.000 / 1.000 | 1.000 | 0.0000 | 0 | 0.0000 | – | bit-exact replay | 20.6 |
| A1 cheaper quant served (Q2_K), claims Q4_K_M | reject | 8/8 | 0.445 / 0.271 / 0.667 | 0.000 | 0.7573 | 78 | 0.1524 | 0.893 | 10 claimed tokens outside the sampler's support; 11 claimed tokens outside the sampler's support; 12 claimed tokens outside the sampler's support; 3 claimed tokens outside the sampler's support; 8 claimed tokens outside the sampler's support | 18.6 |
| A2 different model served (phi3), claims qwen | reject | 8/8 | 0.057 / 0.000 / 0.146 | 0.000 | 2.1420 | 337 | 0.0632 | 0.957 | 34 claimed tokens outside the sampler's support; 36 claimed tokens outside the sampler's support; 40 claimed tokens outside the sampler's support; 44 claimed tokens outside the sampler's support; 45 claimed tokens outside the sampler's support; 46 claimed tokens outside the sampler's support; 47 claimed tokens outside the sampler's support | 17.9 |
| A3 hidden system prompt | reject | 7/8 | 0.737 / 0.562 / 0.896 | 0.000 | 0.2729 | 13 | 0.0951 | 0.794 | 2 claimed tokens outside the sampler's support; 9 claimed tokens outside the sampler's support; a draw sits 0.50 of CDF mass from the claimed token (> 0.45); a draw sits 0.65 of CDF mass from the claimed token (> 0.45); a draw sits 0.67 of CDF mass from the claimed token (> 0.45); mean draw gap 0.0306 > 0.03; within backend drift | 18.2 |
| A4 sampler tamper: ran at T=1.3, claims T=0.7 | reject | 8/8 | 0.594 / 0.354 / 0.938 | 1.000 | 0.3243 | 38 | 0.1297 | 0.507 | 3 claimed tokens outside the sampler's support; 4 claimed tokens outside the sampler's support; 5 claimed tokens outside the sampler's support; 6 claimed tokens outside the sampler's support; 8 claimed tokens outside the sampler's support; logits are bit-identical but the sampler disagrees at 3 positions | 18.5 |
| A5 sampler tamper: ran greedy, claims T=0.7 seeded | reject | 8/8 | 0.831 / 0.708 / 0.979 | 1.000 | 0.2464 | 0 | 0.0851 | 0.683 | logits are bit-identical but the sampler disagrees at 1 positions; logits are bit-identical but the sampler disagrees at 12 positions; logits are bit-identical but the sampler disagrees at 14 positions; logits are bit-identical but the sampler disagrees at 4 positions; logits are bit-identical but the sampler disagrees at 5 positions; logits are bit-identical but the sampler disagrees at 6 positions; logits are bit-identical but the sampler disagrees at 9 positions | 17.8 |
| A6 seed tamper: ran seed 1234, claims seed 999 | reject | 8/8 | 0.781 / 0.542 / 0.979 | 1.000 | 0.0000 | 0 | 0.1637 | 0.933 | logits are bit-identical but the sampler disagrees at 1 positions; logits are bit-identical but the sampler disagrees at 12 positions; logits are bit-identical but the sampler disagrees at 21 positions; logits are bit-identical but the sampler disagrees at 22 positions; logits are bit-identical but the sampler disagrees at 3 positions; logits are bit-identical but the sampler disagrees at 7 positions; logits are bit-identical but the sampler disagrees at 9 positions | 18.4 |
| A7 token edit after signing, not re-signed | reject | 8/8 | 0.865 / 0.812 / 0.917 | 0.354 | 0.1073 | 16 | 0.0226 | 0.744 | signature | 18.0 |
| A8 token edit, re-signed with the prover's key | reject | 8/8 | 0.865 / 0.812 / 0.917 | 0.354 | 0.1073 | 16 | 0.0226 | 0.744 | 1 claimed tokens outside the sampler's support; 2 claimed tokens outside the sampler's support; 3 claimed tokens outside the sampler's support; 4 claimed tokens outside the sampler's support; a draw sits 0.57 of CDF mass from the claimed token (> 0.45) | 17.8 |

Notes:

- H2 honest / gpu prove, gpu verify, batched replay: prefill kernels differ from decode kernels; measures batch-invariance
- H3 honest / gpu prove, cpu verify: cross-backend drift
- A1 cheaper quant served (Q2_K), claims Q4_K_M: same weights requantized to Q2_K; receipt copies the honest model's hashes
- A2 different model served (phi3), claims qwen: tokenizers differ, so the claimed prompt tokens are qwen's and the response tokens are phi3's
- A3 hidden system prompt: model saw a prefix the receipt omits
- A8 token edit, re-signed with the prover's key: key compromise; only replay can catch it

Calibration: lowest honest token-match rate 0.792; highest attack token-match rate 0.979; largest honest draw gap 0.4289 (limit 0.45); largest honest mean gap 0.0217 (limit 0.03). Same-backend replays are bit-exact and judged by the strict rule: identical logits must give identical tokens.
