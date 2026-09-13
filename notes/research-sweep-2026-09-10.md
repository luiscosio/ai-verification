# Research and code sweep: AI compute verification, Sep 10, 2026

Method: four parallel sweeps of the arXiv API (sorted by submission date) and the GitHub search API (sorted by last push), backfilled from org sites and the WHodgkins bibliography. arXiv throttled some queries, so coverage of a few topics is incomplete; gaps are listed at the end. Priority was June to September 2026.

## 1. Zero-knowledge proofs of inference

### Papers (newest first)

| Paper | Date | Authors / org | Link | What it does | Scale or performance |
|---|---|---|---|---|---|
| Sound Debloating of Redundant Checks in zkML Circuits | Sep 9 | Xue, Ma et al. | arXiv 2609.10149 | Abstract interpretation removes redundant range/sign/bit checks in Halo2-style circuits | Up to 25.3M constraints; 49% fewer constraints, 73% less prover time |
| Private and Verifiable Outsourcing of Open-Weight LLM Inference | Aug 31 | Gupta, Katz, Miers | eprint 2026/1849 | Two non-colluding servers; MPC, not ZK | Llama-2-70B, 11 to 14x faster than SIGMA |
| Hollow-LLM Attack | Jul 30 | Gong, Liu, Li (S&P '26) | arXiv 2607.28884 | "Ghost weights" satisfy zkLLM and zkGPT circuits at small-model cost | Attack: proof of correct inference is not proof of model size |
| zkComposer | Jul 9 | Sanjaya, Giannoula et al. | arXiv 2607.08095 | Splits proofs by layer and sequence, links via shared commitments | 4.8 to 6.8x over zkGPT on GPT-2; no code |
| Separation Principle for Lookup-Based zkML | Jul 8 | Min Jun Jo | eprint 2026/1390 | Per-lookup cost depends on access pattern, not activation structure | Theory; caps nonlinearity tricks |
| VeriAttn | Jun 15 | Chen, Wu et al. | arXiv 2606.16352 | TEE (TDX) verifies GPU-offloaded attention | 2.6 to 5.4x over TSDP; TEE plus GPU, not ZK |
| NTT vs SumCheck in hardware | Jun 15 | Mo, Daftardar et al. | arXiv 2606.16146 | Same-budget accelerator comparison | Sumcheck wins for high-degree polynomials |
| DeepProve | May 30 | Lagrange Labs | eprint 2026/1112 | Sumcheck plus lookups; full-sequence proof via output certification | GPT-2 174 tok/min, Gemma-3 86 tok/min on CPU; 1,855 tok/min distributed; verify 1 to 3.7 s |
| Remainder papers | May 23 to 27 | Cao, Cosby et al. (ex-Modulus) | eprint 2026/1038, 1063 | GKR prover, MLP benchmarks across six provers | About 180x prover blowup |
| Lightweight Cryptographic Proofs of Inference | Mar 19 | Anchuri, Campanelli, Gennaro et al. (SaTML '26) | arXiv 2603.19025 | Merkle-committed trace with sampled openings | Llama-2-7B; probabilistic soundness |
| NanoZK | Mar 17 (v2 Jul 18) | Z. Wang | arXiv 2603.18046 | Halo2 layerwise proofs, 16-bit lookup tables | Small; GPU numbers are projections |
| Jolt Atlas | Feb 19 | ICME | arXiv 2602.17452 | Jolt lookups on ONNX tensors, streaming prover | GPT-2 125M in about 15 s on a laptop |
| zkAgent | Feb 7 | Wang, Lou et al. | eprint 2026/199 | One-shot transcript proofs including tool calls | GPT-2, 0.40 s per token |

2025 anchors: ZKTorch (arXiv 2507.07031, no public repo), zkPyTorch (eprint 2025/535, no repo), zkGPT (eprint 2025/1184), ZKLoRA (arXiv 2501.13965).

### Repos

| Repo | Last push | Stars | License | What / scale | Integrations |
|---|---|---|---|---|---|
| Lagrange-Labs/deep-prove | May 31 (v2.0.1) | 3,353 | Lagrange custom | GPT-2, Gemma-3-1B, Llama-2-7B supported; CUDA HyperKZG; distributed workers | SafeTensors, GGUF, ONNX; no vLLM or SGLang |
| zkonduit/ezkl | Feb 20 (v23.0.5) | 1,221 | none in repo | Halo2; nanoGPT scale; Icicle GPU | ONNX |
| ICME-Lab/jolt-atlas | Sep 4 | 78 | ICME custom | GPT-2 125M in 15 s | ONNX |
| inference-labs-inc/JSTprove | Apr 23 | 1,318 | source-available | ONNX to Expander GKR; Remainder backend | ONNX |
| inference-labs-inc/Remainder_CE | Feb 26 | 0 | Apache-2.0 | Modulus Labs' GKR prover, community edition | |
| PolyhedraZK/Expander | Jul 20 | 152 | AGPL-3.0 | GKR prover; zkPyTorch frontend not public | |
| uiuc-kang-lab/zkTransformer | Apr 26 | 0 | Apache-2.0 | Rust, sumcheck; lists GPT-2 to LLaMA-2-7B; no paper, no numbers | |
| compute-verification/zkp-harness | Aug 5 | 0 | none | One 2-page PDF: design note for a Lean-specified prover evaluation harness | |
| Attestable | no public repo or paper | | closed | Claims 30B model, one H100, tens of tok/s (Aug 11 launch) | |
| Dormant: SafeAILab/zkDL, ora-io/opml, gizatechxyz/LuminAIR, Modulus-Labs | 2023 to 2025 | | | | |

### Takeaways

- Largest LLM with an end-to-end ZK proof in open code: DeepProve supports Llama-2-7B, but published throughput exists only for GPT-2 and Gemma-3-1B on CPU. No open 7B timings anywhere.
- Best claimed throughput is closed: Attestable's tens of tokens per second on a 30B model on one H100. If true, roughly 100x the open state of the art. No primary technical source beyond the company's post.
- Open GPU proving is partial: DeepProve (CUDA polynomial commitment), ezkl and zkTransformer (Icicle). Nobody open has published H100 end-to-end LLM numbers.
- The technique has converged on sumcheck/GKR plus lookups. Scaling levers are inter-proof parallelism (zkComposer, DeepProve distributed) and compiler passes (debloating).
- Hollow-LLM (S&P '26) matters for treaties: a valid proof of correct inference doesn't prove the declared model size was computed. Weight binding needs its own check.
- At 70B and above, 2026 verification is MPC, TEE plus GPU, or statistical, not ZK.
- Licensing: the leading open provers are source-available, not OSI (DeepProve, JSTprove, Jolt Atlas); ezkl ships no license file. Activity since June is concentrated at Inference Labs, ICME, and Lagrange.

## 2. Recomputation and deterministic inference (non-ZK)

### Papers (newest first)

| Paper | Date | Authors | Link | What it does | Detects / overhead | Engine |
|---|---|---|---|---|---|---|
| Same Request, Different Answer | Sep 4 | Patodiya | arXiv 2609.04748 | Prefix-cache nondeterminism | Cache flips agent runs 36% (bf16) to 75% (4-bit); bit-identical with cache off | two engines |
| Adversarial Entropy Inflation | Aug 24 | Kezins | arXiv 2608.23375 | Attack on Gumbel-forgiveness verifier | Exfiltration slowdown falls from over 200x to 60 to 118x | |
| CoRun | Aug 14 | Zhao et al. | arXiv 2608.14376 | Padded fixed-shape decode for determinism | Batch-invariant kernels cost over 2x latency, 74% throughput; no code | custom |
| Integer Alibi | Aug 13 | Chen | arXiv 2608.13756 | INT8 CUTLASS vs Triton kernels | Kernels never agree bitwise | vLLM, Qwen3 8B |
| Repeated-Game Security for Restaking | Aug 10 | Shang et al. | arXiv 2608.09055 | Game theory of re-execution with slashing | One-shot slashing overstates security | |
| IRIS | Jul 23 | Zhang et al. | arXiv 2607.20860 | Text-only model-substitution audit | 0.99 AUROC on a Qwen3 ladder | API |
| Gateway-Path Provenance | Jun 21 | Wang, Tian | arXiv 2606.22560 | Signed gateway provenance | Route substitution, hidden fallback | gateway |
| Bit-Exact Inference Verification | May 29 | Cankaya (MIRI) | arXiv 2606.00279 | Bitwise recompute via cross-GPU emulation, no determinism flags | Steganography, hidden batch elements; ICML '26 TAIGR best paper | vLLM, HF |
| MarginGate | May 28 | Chu et al. | arXiv 2605.30218 | Verify only low-margin decode steps | 0.3 to 1.3% of steps | custom |
| IMMACULATE | Feb 26 | Guo et al. | arXiv 2602.22700 | Sampled verifiable computation | Substitution, quantization, overbilling; under 1% | dense and MoE |
| TensorCommitments | Feb 13 | Baser, Alves et al. | arXiv 2602.12630 | Tensor-native commitments | 0.97% prover, 0.12% verifier overhead | custom |
| EigenAI | Jan 30 | Alves et al. | arXiv 2602.00182 | Deterministic engine plus optimistic re-execution in TEE | Byte equality; no code | proprietary |
| LLM-42 | Jan 25 | Gond, Ramjee, Panwar (MSR, SOSP '26) | arXiv 2601.17768 | Decode-verify-rollback determinism | No new kernels needed | SGLang |
| Token- and Activation-DiFR | Nov 2025 | Karvonen, Rinberg et al. | arXiv 2511.20621 | Seed-synced recomputation | 4-bit quantization AUC over 0.999 in 300 tokens; zero prover cost | vLLM |
| Weight Exfiltration Verification | Nov 2025 | Rinberg et al. | arXiv 2511.02620 | Gumbel-forgiveness verifier | Over 200x slowdown, now contested | vLLM |
| TOPLOC | Jan 2025 | Prime Intellect | arXiv 2501.16007 | Top-k LSH of hidden state | 258 bytes per 32 tokens; flaws noted by DiFR and Amodo | vLLM, SGLang fork |

### Repos

| Repo | Stars | Last push | License | What |
|---|---|---|---|---|
| Amodo-Design/Inference-Recomputation-Prototype | 0 | Sep 10 (new) | MIT | vLLM sidecar tap, Postgres ledger, Kubernetes verifiers, async Token-DiFR; 8x H100 plus 4x H200; Qwen2.5-7B |
| vLLM `VLLM_BATCH_INVARIANT=1` | 91k | Sep 10 | Apache | Beta; tracker #27433; no prefix cache, no spec decode, no AMD |
| SGLang `--enable-deterministic-inference` | 36k | Sep 10 | Apache | FlashInfer, FA3, Triton; CUDA graphs, radix cache; roadmap #10278 |
| microsoft/llm-42 | 28 | Sep 10 | Apache | SOSP '26 artifact on SGLang 0.5.3 |
| PrimeIntellect-ai/toploc | 61 | Sep 4 (dependabot; code Apr 2025) | MIT | Library; Llama-3.1-8B |
| PrimeIntellect-ai/sglang fork | 4 | Jun 12 | Apache | topk-verif branch, last real commit Jan 2025 |
| adamkarvonen/difr, token-difr; RoyRin exfiltration repo | 6 / 4 / 6 | Feb to Jul | MIT | DiFR and TOPLOC metrics on vLLM v1 |
| gensyn-ai/ree | 23 | Aug 28 | MIT plus proprietary | Reproducible inference container |
| thinking-machines-lab/batch_invariant_ops | 1,075 | Nov 2025 | MIT | Upstreamed into vLLM and SGLang; dormant |
| Minor: guo-yanpei/Immaculate, kexinchu/MarginGate, NaciCankaya PoC | | | | |

Not found: Hyperbolic proof-of-sampling code, EigenAI verifier, Atoma, Gensyn Verde, CoRun, any TensorRT-LLM determinism work.

Amodo Design notes in 2026: Sep 2 Scaling Recomputation Verification; Jul 3 Traffic Hashing at 400GbE; Jul 1 Memory Wipes on H200; Jun 29 Prototype Stage 1 (Token-DiFR, 37,500 runs, LoRA-append attacks); Jun 23 Example Schemes; Jun 10 Why Verification; Jun 8 Verification Is a Ladder; May 3 Network Tapping; Apr 2 Power Delivery; Mar 20 Taps test; Mar 16 DPU limiter. Only the two prototype posts link code.

### Takeaways

- Determinism is mainline in vLLM and SGLang, at over 2x latency cost by CoRun's measurement. Scheduling fixes (LLM-42, CoRun, MarginGate) cut it; only LLM-42 is maintained.
- Token-DiFR is the working recomputation scheme: zero prover cost. Amodo's September stack is the first production-shaped async pipeline, with the verifier needing one half to one eighth of the prover's GPU time.
- TOPLOC is frozen since April 2025 and its flaws are cited by successors.
- Summer attacks: Kezins halves the exfiltration bound; restaking slashing is gameable; billing audits inflate 15x. Static thresholds aren't treaty-grade.
- Bit-exact recompute works (Cankaya, EigenAI) only if batch composition, cache state, and kernel identity are logged. Prefix caching and INT8 kernels are new divergence sources.
- Missing: completeness, evidence formats, adversarial calibration, tests above roughly 32B, MoE verification, TensorRT-LLM.

## 3. Hardware and datacenter mechanisms

### Papers and reports (newest first)

| Item | Date | Authors / org | Link | What it does | Maturity | Mechanism |
|---|---|---|---|---|---|---|
| Beyond Training: Inference-Time Governance Taxonomy | Sep 9 | Ansari | arXiv 2609.10105 | 20 inference-time mechanisms rated; companion to 2604.04712 (20 hardware mechanisms) | paper | taxonomy |
| How to Make International AI Verification a Reality | Sep 2 | The Future Society | thefuturesociety.org | Ranks retrofittable off-chip devices (taps, power and thermal sensors) as top near-term priority | policy | taps, power |
| Workload Identification with Physical Side Channels | Aug 31 | Gargiulo, Kulp (ISL, RAND) | arXiv 2609.00309 | External power at about 10 MHz on H200; 930 traces; 97% train/infer/non-AI; diluted-LoRA evasion only 48 to 88% caught | prototype plus dataset (gated) | power |
| Near-Term Verification Methods for AI Chip Exports | Aug 19 | Grunewald (IAPS) | iaps.ai | One-year-deployable chip-export verification guide | policy | location, inspection |
| Privacy-Preserving Verification via Minimal Information Disclosure | Aug 3 | Abdelghafar, Kulp | arXiv 2608.02774 | Bounds collateral leakage from physical measurements; Groth16 projection | prototype | power |
| De-risking Interconnect Limits | Jul 30 | Sarbakysh, Moskvin, Scher (MIRI TGT) | techgov.intelligence.org | Two-node A100 test: training 2 to 3 GB/s vs inference about 10 KB/s; DiLoCo still detectable; proposes about 1 MB/s cap | prototype | compartmentalization |
| Assessment of Plan A verification | Jul 30 | J. Drori | LessWrong 2eznrbNo6S7k5M9mu | Memory wipes about 24 h per rack with 100 TB unwiped; no way to classify training vs inference code | analysis | all |
| Hardware Mechanisms to Dynamically Throttle AI | Jul 20 | Ma et al. (Princeton) | arXiv 2607.18069 | L2 and shared-memory knobs cut performance up to 80% with under 10K flip-flops | simulation | on-chip |
| Bit2Watt | Jul 7 | Ji, Pan, Xu | arXiv 2607.05993 | GPU workloads produce grid-visible high-frequency power signatures | paper | power |
| Amodo: Traffic Hashing, Memory Wipes, Plan A SITREP | Jul 1 to 3 | Amodo | amododesign.com/notes | DPDK hashes 400G at 1500B frames or larger, DPU only 162 Gbps; PoSE wipe of 140 GB HBM in 524 s, about 43 min per GB200 tray, storage takes hours; SITREP: 4 items active, 13 not started or off track | prototype | taps, erasure |
| Verifying Restrictions on Frontier AI Research | Jun 27 | Scher (MIRI) | arXiv 2606.28694 | 28 mechanisms including inspections, code review, whistleblowers | paper | inspection |
| System Overview for Near-Term Low-Trust Compute Verification | Jun 23 | Cankaya (MIRI) | techgov.intelligence.org | Taps capture and commit; air-gapped recompute of random challenges; ZK optional | architecture | taps |
| Detecting Hidden ML Training With Zero-Overhead Telemetry | Jun 17 | Rahman, Tajdari | arXiv 2606.19262 | Nine NVML counters at 1 Hz; 98% clean, 43 to 87% under disguise | prototype | telemetry |
| How to Catch a GPU | Jun 16 | Koopmanskap, Barten | arXiv 2607.22619 | Enforcement taxonomy; "enforcement breaking point" | paper | inspection |
| Fingerprinting All AI Cluster I/O Without Mutually Trusted Processors | Jun 9 | Cankaya, Kryś, Ng, Marks, Krückel | arXiv 2606.10724 | Passive splitters plus coin-flip RNG secure gateway against timing and steganographic channels | design | taps, compartmentalization |
| Usefulness Gap in PoUW: cuPOW | Jun 3 | Basu | arXiv 2606.04819 | Pearl's 24 EH/s (about 112 MW) runs zero inference; verifier accepts random matrices | empirical | exhaustion |
| Bit-Exact Inference Verification | May 29 | Cankaya | arXiv 2606.00279 | Software GPU emulation gives bit-exact recompute; code released | prototype | taps |
| Proofs of Compartmentalization | ICML TAIGR, Jul | Reuter, Marks et al. | OpenReview ajrtHuFw2S | Pod and task PoComp with zkML sampling; cuPOW saturation variant | prototype | compartmentalization, exhaustion |
| Bounding Unexplained Information Exfiltration | ICML TAIGR | Petrie, Mühlhäuser | OpenReview qtgG5HZSsk | Budgets unexplained bits across content, timing, metadata | paper | taps |
| Suppressing Side Channels in an Untrusted Data Center | 2026 | Cankaya (MIRI) | techgov.intelligence.org | Enclosures, sensors, jamming, unannounced inspections; kbps bound at under 1% BOM | design | side channels |
| GPU Fingerprinting for Location Verification | May 3 | Tee, Happel (TamperSec) | arXiv 2605.01930 | Hardware fingerprints instead of extractable keys | PoC | location |
| Secure Network Taps: Fundamentals and Feasibility | Apr 30 | Cankaya, Friedman, Baker | nacicankaya.substack.com | North-south FPGA taps under 0.01% of DC cost; fabric sampling 0.2 to 1.5%; copper scale-up domains untappable | analysis | taps |
| Amodo: Network Tapping Assessment, First Test, Tray Bandwidth Boundary | Mar to May | Amodo | amododesign.com/notes | COTS taps exist at 26 GBaud, none at 53 or 106; 10G passive splitter demo; BlueField-3 per-tray limiter 390 Gbps raw | PoC | taps, compartmentalization |
| Secure Inference Data Centers (RRA4827-1) | 2026 | Comer, Kulp et al. (RAND) | rand.org | SL5 facilities, data diodes, formal methods | design | compartmentalization |
| Timing and Memory Telemetry on GPUs | Feb | Monfared, Ganji, Holcomb (WPI) | arXiv 2602.09369 | Timing and memory-residency observables with untrusted host and device | prototype | side channel |
| AVID Workshop (FAR.AI, CAIS, IEEE S&P) | May 17 | far.ai | Talks: power signatures (Nuriyev, Kulp), memory challenge-response (Baker), tamper detection (Tajik), I/O logging (Friedman) | talks | mixed |

Older anchors: cuPOW (arXiv 2504.09971, Apr 2025); FlexHEG trio (arXiv 2506.15093, 2506.15100, 2506.03409, Jun 2025). No 2026 FlexHEG paper found.

### Repos and datasets

| Name | Pushed | Stars / license | What it contains | Maturity |
|---|---|---|---|---|
| compute-verification/proof-of-compartmentalization | Jul 30 | 1, Apache-2.0 | Rust PoComp: SP1 guests, pinned zkTorch fork, audited gateway and gateway-free cuPOW saturation on Vast pods; CITATION lists Reuter, Marks, Carlucci, Ng, Petrie, Hausenloy, Karvonen, Baker | research prototype, self-labeled "Experimental" |
| pearl-research-labs/pearl | Sep 10 | 298, ISC | L1 PoUW chain, vLLM miner, Plonky2 | deployed mainnet |
| WHodgkins/AI-Verification-Papers | Aug 29 | 5, CC BY 4.0 | 69 entries, 25 dated 2026 | curated bibliography |
| Amodo-Design/Inference-Recomputation-Prototype | Sep 10 | 0 | vLLM tap sidecar, Postgres ledger, Kubernetes DiFR verifier | prototype |
| Amodo-Design/PSRR-Injector-Board | Mar 31 | 1, CERN-OHL-P | Power-rail ripple injector | hardware |
| Lucid-Computing/sovereignty-certificate-specification | Mar 6 | 2 | Draft ping-based location attestation (RATS/EAT) | draft spec |
| Gargiulo H200 power traces (Hugging Face) | | | 930 plus 680 traces | returns HTTP 401 |
| TamperSec/kimesh | 2023 | GPL-3 | KiCad security mesh | stale |

No public GitHub for MIRI techgov, FLI, or ISL. Lucid runs a red-team cluster ("Proof of Principle stage 2 of 4") with no published results.

### Takeaways

- The consensus stack is retrofit off-chip: passive optical taps, line-rate hashing, memory wipes, air-gapped recompute. MIRI, Amodo, and The Future Society converged on it independently. Nobody has run an end-to-end pilot.
- Taps are the bottleneck. Demonstrated only at 10G; COTS parts stop at 26 GBaud; copper scale-up (NVLink) domains can't be tapped at all.
- Power and telemetry classification now has data: 97 to 98% clean accuracy from two groups, but adversarial evasion drops detection to 50 to 88%. The main dataset is gated.
- Interconnect limits are the most robust cheap mechanism (a 100,000x traffic gap between training and inference, DiLoCo still visible). PoComp is the only cryptographic compartmentalization prototype.
- Exhaustion and proof of useful work: Pearl shows cuPOW runs at scale, Basu shows it does nothing useful. Saturation-as-proof (PoComp) is the honest framing.
- Erasure is the practical blocker for inference-only regimes: about 43 min per tray for HBM and RAM, hours to a day for storage, and about 100 TB per rack unwipeable.
- Open gaps: no classifier for training vs inference code; side-channel suppression enclosures unbuilt; tap-install verification, reporting integrity, and inspection protocols "not on track" per Amodo's SITREP.

## 4. Attestation, TEEs, and audit tooling

### Papers and reports (newest first)

| Item | Date | Authors / org | Link | What it does | Maturity |
|---|---|---|---|---|---|
| Not to Break, but to Attest | Aug 28 | Wilding, Shaker, Ganji | arXiv 2608.27954 | zk-SNARK audit with adversarial probes to detect silent model swaps | paper |
| Double-Blind Evals technical report | Aug 27 | Trask et al.; AVERI, Google DeepMind, Singapore AISI, OpenMined, MLCommons | deepmind.google blog and PDF; averi.org | Gemini 2.5 Flash Lite evaluated on private AILuminate prompts inside GCP Confidential Space (TDX plus H100 CC) via PySyft | pilot, single node; Google remains in the attestation-verification path, guest OS builds not reproducible |
| Benchmarking Confidential Computing on Blackwell | Aug 27 | Asad, Grunseid | arXiv 2608.26575 | 1 to 3% throughput overhead tuned, 30 to 40% with defaults | measurements |
| VMs won't contain cyber-capable agents | Aug 26 | Dinaburg (Trail of Bits) | blog.trailofbits.com | GPT 5.6-Cyber escaped QEMU/KVM three times, last via chained zero-days; Firecracker held but hardlocked | empirical |
| Lean kernel soundness bug hunt postmortem | Aug 24 | de Moura, OpenAI | leodemoura.github.io | AI found 8 soundness and runtime bugs, fixed in v4.33.1 | postmortem |
| Audit Log Integrity and Session State Channels | Aug 22 | Quinn, MaxVH (for-all.dev) | tractable.for-all.dev | Problem sketch: verified Merkle logs (CT or Rekor style), TLA+ permission model | problem statement |
| Auditor-in-a-Box | Jul 28 | Rinberg, Penchas | LessWrong uWYk7MM9hAf9GEbGe | Open-weight LLM in a TEE runs co-signed audit plans over both parties' private data; append-only ledger | prototype |
| MITRE Continuous Remote Attestation Framework v0.9.6 | Jul 16 (comments to Sep 30) | MITRE, Fr0ntierX, Invary, U. Kansas | mitre.org | Runtime attestation spec: kernel and process integrity, attested transport, AI workload verification | public review draft; no reference code found |
| EnclaveX | Jun 30 | TU Dresden, Scontain | arXiv 2606.31408 | End-to-end TDX plus H200 workflow; flags Kubernetes-admin access to CVMs | paper |
| The Serialized Bridge | Jun 22 | Yin, Wang (dstack) | arXiv 2606.23969 | CVM to GPU bridge costs 13 to 27% on Blackwell; recovers 57 to 92% | measurements |
| VCT verifiable transcripts | Jun 22 | Xing et al. | arXiv 2606.23003 | Hash chains per Q&A branch, session Merkle roots, joint signatures | paper, no code |
| ZK verification for frontier training | Jun 3 (v2 Aug 22) | Peigné, Nguyen, Wang | arXiv 2606.05433 | Network observations plus Merkle commitments plus zkVM; about 36 months to a PoC | proposal |
| Pod-level attestation on dstack | Jun 2 | Yang et al. | arXiv 2606.03323 | Per-pod hardware-backed identity inside one TDX CVM | open source per paper |
| SandboxEscapeBench | Mar 1 (rev Aug 1) | Marchand et al. | arXiv 2603.02277 | 18-level container escape benchmark in Inspect | open benchmark |

Also cited but not confirmed: Mandato (arXiv 2608.14074), Black Box for Agentic Processes (arXiv 2609.04017), Proof of Execution (arXiv 2607.05397).

### Repos

| Repo | Stars / last push / license | What it does | Maturity |
|---|---|---|---|
| Verified-zkEVM/ArkLib | 333 / Sep 10 / Apache-2.0 | Lean IOR framework: sumcheck, FRI, STIR, WHIR, Spartan in progress | no extraction to an executable verifier |
| Verified-zkEVM/clean | 182 / Sep 10 / MIT | Lean circuit DSL with soundness and completeness per gadget | active |
| digama0/lean4lean | 243 / Aug 29 / Apache-2.0 | Lean 4 kernel in Lean | 27 `sorry`s remain |
| succinctlabs/veil-formal-verification | 0 / May 6 / Apache-2.0 | VEIL protocol math in Lean 4, AI-written proofs | math only |
| NVIDIA/nvtrust | 321 / Sep 1 / Apache-2.0 | GPU attestation SDK; v1.x end of life Sep 15 | production |
| Dstack-TEE/dstack | 541 / Sep 10 / Apache-2.0 | Confidential containers on TDX and SEV-SNP with NVIDIA CC; verifier, Trust Center | production-ish |
| edgelesssys/contrast | 314 / Aug 25 / custom | Confidential containers on Kubernetes | production |
| ultravioletrs/cocos | 60 / Jul 30 / Apache-2.0 | Confidential AI compute | active |
| confidential-containers/trustee | 185 / Sep 10 / Apache-2.0 | Attestation and secret delivery | production |
| OpenMined/PySyft `packages/syft-enclave` | 10,029 / Sep 7 / Apache-2.0 | Attestation and restriction code used in the DeepMind pilot | active |
| RoyRin/auditor-in-a-TEE | 1 / May 15 / none | Auditor-in-a-Box code; empty README | prototype |
| for-all-dev/aisec-via-fm | 1 / Aug 22 / none | Problem statements only | docs |
| Sidshah29/llm-audit-chain | 0 / May / MIT | Merkle hash-chain LLM call log | toy; the only Merkle-log repo found |

### Takeaways

- Attested GPU inference is deployable now (nvtrust, dstack, contrast, Blackwell CC) at 1 to 3% overhead when tuned. Attestation still measures launch state; runtime integrity is what MITRE's draft targets, and nobody ships a reference implementation.
- TEEs protect the workload from the host. They don't stop a guest agent escaping outward. Trail of Bits got a hypervisor escape from a production model.
- The double-blind pilot is real but narrow: one model, one node, residual trust in Google. The authors say legal and code-review coordination is now the bottleneck, not hardware.
- No publicly verified-in-Lean executable ZK verifier exists. ArkLib proves protocol-level soundness with no extraction; lean4lean still has 27 sorries. Attestable's claimed Lean proof would be the first, and it's private.
- Audit-log integrity for inference is paper-stage. Nothing production-grade exists for Merkle logs of tokens.

## Cross-cutting takeaways

1. The open-source frontier for ZK inference is about 7B parameters with no published GPU timings; the closed frontier (Attestable) claims 30B at tens of tokens per second. That gap is the single most important unverified claim in the field.
2. Recomputation (Token-DiFR on vLLM) is the only verification path with production-shaped code, and Amodo published theirs on Sep 10.
3. The "software-only phase 1" from the group (ZKPs plus exhaustion) has a new problem: Hollow-LLM shows a ZK proof of correct inference can be satisfied at small-model cost, and Basu shows cuPOW-style saturation can be fed random matrices. Weight binding and saturation both need their own guarantees.
4. Every completeness mechanism has hard measured numbers now, and they're sobering: taps top out at 10G demonstrated, erasure takes 43 minutes per tray, power classifiers fall to 50 to 88% under evasion, interconnect limits are the one cheap thing that holds.
5. Attacks are arriving faster than defenses: entropy inflation, prefix-cache nondeterminism, restaking games, billing inflation, hypervisor escape by a production model.
6. Formal verification of the verifiers themselves is the next trust layer, and it's early: ArkLib and clean are active, lean4lean is incomplete, the Lean kernel itself shipped soundness fixes in August.
7. Three groups (MIRI TGT, Amodo, The Future Society) independently converged on retrofit off-chip devices as the near-term priority, matching the group's "scramble" debate.

## Not verified or incomplete

- arXiv API throttled several queries across all four sweeps; coverage of double-blind evaluation, formally verified ZK, and sandbox escape topics came from web search instead.
- Attestable's model name and proof system have no primary technical source.
- OpenReview blocked direct fetches; PoComp and Petrie papers were sourced via the WHodgkins bibliography and the repo CITATION file.
- The MITRE main spec PDF returned 403; only Annex C was confirmed.
- Gargiulo's Hugging Face dataset returns 401.
- Incidents cited by papers (an April 2026 frontier model escape, a July 2026 Hugging Face incident) were not independently confirmed.
