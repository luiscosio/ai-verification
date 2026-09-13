# Activation trace (rung 4) test set results

Model under test: qwen2.5 1.5B instruct (Ollama Q4_K_M blob). Prompts: 4. Tokens per prompt: up to 32. Openings per receipt: 32. Sampler: T=0.7, top_k=40, top_p=0.95, seed=1234. Verifier mode: trace (no model execution). Machine: arm64 macOS-26.6.2-arm64-arm-64bit-Mach-O. Generated 2026-09-11.

| Case | Expected | Verdicts | Leaves / graphs | Prove s | Verify s | Sidecar MB | Failed checks | Worst MUL_MAT error |
|---|---|---|---|---|---|---|---|---|
| TH1 honest / Metal prove, trace-only verify | accept | 4/4 correct | 23298 / 33 | 11.5 | 2.5 (replay 1.6 s) | 3.2 | none | 2.4e-03 |
| TH2 honest / CPU prove, trace-only verify | accept | 4/4 correct | 23298 / 33 | 10.8 | 2.6 | 3.2 | none | 9.4e-04 |
| TA1 cheaper quant served (Q2_K), claims Q4_K_M, leaf types forged | reject | 4/4 correct | 23298 / 33 | 11.9 | 2.5 | 4.6 | openings | 4.0e-01 |
| TA2 different model served (phi3), claims qwen | reject | 4/4 correct | 22374 / 33 | 21.2 | 2.3 | 5.3 | openings | 5.9e-04 |
| TA3 hidden system prompt | reject | 4/4 correct | 23298 / 33 | 11.5 | 2.7 | 3.8 | input_k_cells, input_mask, input_out_ids, input_positions, input_tokens, input_v_cells | 1.5e-03 |
| TA7 token edit, commitments and signature refreshed, trace untouched | reject | 4/4 correct | 23298 / 33 | 11.6 | 2.7 | 3.2 | challenge, input_tokens | 2.4e-03 |
| TA9 single fabricated activation, edges kept consistent | limitation | 0/4 caught | 23298 / 33 | 11.9 | 2.5 | 3.0 | none | 5.3e-04 |
| TA10 signed root differs from the leaves | reject | 4/4 correct | 23298 / 33 | 11.5 | 2.5 | 3.2 | challenge, openings, root | – |

Notes:

- TH1 honest / Metal prove, trace-only verify: verifier holds weights but never runs the model; replay time shown for comparison
- TH2 honest / CPU prove, trace-only verify: CPU kernels quantize activations to 8 bits before the dot product; tolerances must cover it
- TA1 cheaper quant served (Q2_K), claims Q4_K_M, leaf types forged: only the opened bytes betray it: every weight matmul re-executes wrong
- TA2 different model served (phi3), claims qwen: leaves reference tensors the claimed model does not have
- TA3 hidden system prompt: the prefill graph's token input hashes to more tokens than the receipt claims
- TA7 token edit, commitments and signature refreshed, trace untouched: the decode graph that consumed the edited token has a different token input
- TA9 single fabricated activation, edges kept consistent: caught only when the node or a consumer is sampled; this is the sampling bound
