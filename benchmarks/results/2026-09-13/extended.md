# Extended measurements

## Inference throughput

CPU-only llama-bench, three timed repeats per configuration after warmup. Loading, tokenization, sampling and receipt creation are excluded. A zero in either token column means that phase was not part of the timed test.

| Model | Threads | Prompt tokens | Decode tokens | Mean tokens/s | Sample SD | Repeats |
|---|---|---|---|---|---|---|
| phi3-mini | 2 | 32 | 0 | 73.53 | 0.90 | 3 |
| phi3-mini | 2 | 128 | 0 | 70.44 | 8.50 | 3 |
| phi3-mini | 2 | 512 | 0 | 74.63 | 0.33 | 3 |
| phi3-mini | 2 | 0 | 32 | 32.19 | 0.29 | 3 |
| phi3-mini | 2 | 0 | 128 | 30.52 | 0.66 | 3 |
| phi3-mini | 8 | 32 | 0 | 189.66 | 2.82 | 3 |
| phi3-mini | 8 | 128 | 0 | 187.44 | 2.12 | 3 |
| phi3-mini | 8 | 512 | 0 | 181.41 | 0.69 | 3 |
| phi3-mini | 8 | 0 | 32 | 43.62 | 1.50 | 3 |
| phi3-mini | 8 | 0 | 128 | 42.13 | 0.60 | 3 |
| qwen2.5-0.5b | 2 | 32 | 0 | 441.55 | 2.98 | 3 |
| qwen2.5-0.5b | 2 | 128 | 0 | 707.82 | 21.57 | 3 |
| qwen2.5-0.5b | 2 | 512 | 0 | 803.63 | 5.81 | 3 |
| qwen2.5-0.5b | 2 | 0 | 32 | 115.20 | 0.12 | 3 |
| qwen2.5-0.5b | 2 | 0 | 128 | 112.86 | 0.23 | 3 |
| qwen2.5-0.5b | 8 | 32 | 0 | 256.25 | 16.39 | 3 |
| qwen2.5-0.5b | 8 | 128 | 0 | 548.02 | 21.53 | 3 |
| qwen2.5-0.5b | 8 | 512 | 0 | 931.52 | 28.51 | 3 |
| qwen2.5-0.5b | 8 | 0 | 32 | 156.11 | 23.54 | 3 |
| qwen2.5-0.5b | 8 | 0 | 128 | 161.74 | 22.63 | 3 |
| qwen2.5-1.5b | 2 | 32 | 0 | 149.97 | 1.75 | 3 |
| qwen2.5-1.5b | 2 | 128 | 0 | 151.73 | 0.94 | 3 |
| qwen2.5-1.5b | 2 | 512 | 0 | 149.31 | 2.60 | 3 |
| qwen2.5-1.5b | 2 | 0 | 32 | 59.54 | 0.62 | 3 |
| qwen2.5-1.5b | 2 | 0 | 128 | 58.00 | 1.37 | 3 |
| qwen2.5-1.5b | 8 | 32 | 0 | 333.64 | 3.87 | 3 |
| qwen2.5-1.5b | 8 | 128 | 0 | 346.98 | 46.23 | 3 |
| qwen2.5-1.5b | 8 | 512 | 0 | 362.90 | 2.62 | 3 |
| qwen2.5-1.5b | 8 | 0 | 32 | 80.62 | 2.97 | 3 |
| qwen2.5-1.5b | 8 | 0 | 128 | 78.85 | 1.77 | 3 |
| qwen3-0.6b | 2 | 32 | 0 | 413.75 | 12.58 | 3 |
| qwen3-0.6b | 2 | 128 | 0 | 415.83 | 7.65 | 3 |
| qwen3-0.6b | 2 | 512 | 0 | 373.49 | 2.25 | 3 |
| qwen3-0.6b | 2 | 0 | 32 | 139.04 | 0.58 | 3 |
| qwen3-0.6b | 2 | 0 | 128 | 134.58 | 0.06 | 3 |
| qwen3-0.6b | 8 | 32 | 0 | 895.30 | 29.81 | 3 |
| qwen3-0.6b | 8 | 128 | 0 | 976.70 | 2.56 | 3 |
| qwen3-0.6b | 8 | 512 | 0 | 887.32 | 7.39 | 3 |
| qwen3-0.6b | 8 | 0 | 32 | 177.73 | 0.61 | 3 |
| qwen3-0.6b | 8 | 0 | 128 | 163.38 | 9.12 | 3 |

Each resource profile encloses five throughput configurations and their repeats, including loading and warmup. CPU seconds are user plus system CPU time; CPU seconds divided by elapsed time estimates average occupied CPU cores, not peak utilization.

| Model | Threads | Profile elapsed s | OS CPU seconds | Average CPU cores | OS peak process GiB |
|---|---|---|---|---|---|
| phi3-mini | 2 | 53.46 | 102.98 | 1.93 | 4.30 |
| phi3-mini | 8 | 26.74 | 200.28 | 7.49 | 4.33 |
| qwen2.5-0.5b | 2 | 8.34 | 16.18 | 1.94 | 0.77 |
| qwen2.5-0.5b | 8 | 6.97 | 49.06 | 7.04 | 0.78 |
| qwen2.5-1.5b | 2 | 26.96 | 52.30 | 1.94 | 2.02 |
| qwen2.5-1.5b | 8 | 14.26 | 104.08 | 7.30 | 2.02 |
| qwen3-0.6b | 2 | 11.33 | 21.23 | 1.87 | 0.93 |
| qwen3-0.6b | 8 | 6.20 | 45.34 | 7.31 | 0.92 |

## Evidence capture and registered row proofs

Each pair uses the same two-step request. Tracing always ran second; the filesystem cache was uncontrolled. The difference is observed total overhead, including the second trace pass and serialization. Every paired token sequence matched. All 18 exported proof files passed the independent file verifier; all 18 changed-group packages were rejected. The prover also rejected 18 changed-sum pairing checks. Its own different-commitment comparisons are not counted as additional cryptographic verifications.

| Model | Prompt | K | Proofs | No trace s | With trace s | Difference s | Trace MiB | Median prove s/group | Median cold policy verify ms |
|---|---|---|---|---|---|---|---|---|---|
| qwen3-0.6b | fact | 1024 | 3 | 2.18 | 14.24 | 12.06 | 1419.86 | 2.89 | 171.00 |
| qwen3-0.6b | arithmetic | 2048 | 3 | 2.25 | 15.06 | 12.81 | 1509.28 | 2.91 | 180.00 |
| qwen3-0.6b | code | 3072 | 3 | 2.28 | 15.08 | 12.80 | 1539.09 | 3.39 | 191.00 |
| qwen2.5-1.5b | fact | 1536 | 3 | 5.05 | 8.91 | 3.86 | 441.11 | 3.29 | 179.00 |
| qwen2.5-1.5b | arithmetic | 1536 | 3 | 5.19 | 9.42 | 4.23 | 567.41 | 3.30 | 174.00 |
| qwen2.5-1.5b | code | 1536 | 3 | 5.02 | 10.12 | 5.10 | 609.51 | 3.36 | 177.00 |

The individual subprocess RSS profiles exclude the benchmark parent. The separate process-tree observations below include that parent and its trace parsing. Trace files and witnesses were removed; exported packages contain public activations from the synthetic corpus, public arithmetic sums and proofs, not weights.

## Experimental complete F20 operations

Each package proves all 1,024 rows of one matrix multiplication using 65 component proofs. Three input embeddings were used; their preparation is outside the proof. This is a separate experimental claim, not complete inference or the website row-group claim. Each package passed the verifier and 12 rejection controls.

| Token ID | Full driver s | OS CPU seconds | Witness sum s | Proving sum s | In-process verification ms | OS peak process GiB | Sampled command tree GiB | Package bytes |
|---|---|---|---|---|---|---|---|---|
| 0 | 271.20 | 1332.31 | 22.08 | 228.27 | 475 | 2.73 | 2.75 | 69591 |
| 198 | 270.57 | 1328.86 | 22.00 | 227.85 | 459 | 2.72 | 3.29 | 69570 |
| 512 | 274.25 | 1334.60 | 22.28 | 231.32 | 460 | 2.78 | 2.87 | 69737 |

Full driver time also includes model loading, registration/commitment work, process startup and final verification. The component time sums exclude these costs.

## Complete runner process tree

100 ms sampling includes the sequential orchestrator and its descendants, including trace parsing between measured subprocesses. Observation began partway through the Unicode regression; subsequent suites were observed from their start. RSS can double-count shared pages and miss brief peaks. Live CPU samples are not cumulative accounting. System swap/available memory include other applications; this is not evidence that the benchmark itself swapped.

| Suite | Samples | Peak summed RSS GiB | Minimum system available GiB | System swap GiB |
|---|---|---|---|---|
| check_live_workspace | 218 | 4.42 | 4.81 | 13.48–13.48 |
| check_witnesses | 148 | 0.49 | 6.76 | 13.46–13.48 |
| complete-operation | 7128 | 3.19 | 4.72 | 13.48–13.63 |
| native-negatives | 308 | 4.52 | 6.56 | 13.84–13.84 |
| row-proofs | 1736 | 6.22 | 4.69 | 13.84–13.85 |
| throughput | 1401 | 4.37 | 6.15 | 13.63–13.84 |
| unicode-regression | 1281 | 4.54 | 5.59 | 13.85–13.87 |

## Native negative controls

All 28 controls passed: four honest content checks and 24 rejections covering changed text, prompt, version, token IDs, per-token records and a different model file. Cross-model checks use replay/model-hash validation; the vocabulary-only helper intentionally does not authenticate the model file.
