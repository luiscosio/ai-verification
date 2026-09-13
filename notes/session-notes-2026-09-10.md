# Session notes, Sep 10, 2026

Follow-up questions on the software-only verification stack. Sources are listed at the end of each section; statements made in private discussion are not reproduced here.

## Is the software-only verification stack open source?

Short answer: no, not end to end. About half the pieces exist, and that half already lives inside vLLM and SGLang. The ZK and exhaustion layers are the gap.

| Piece of the stack | Open source today? | Where |
|---|---|---|
| Recomputation verification (Token-DiFR, TOPLOC) | Yes, integrated with vLLM; SGLang fork with TOPLOC | Prime Intellect, Adam Karvonen |
| Deterministic batch-invariant inference | Yes, in both vLLM and SGLang | Thinking Machines kernels |
| Padded-matmul batch commitment | No | idea only, no implementation found |
| ZK proof of LLM inference | Frameworks yes, engine integration no | ezkl, DeepProve, ZKTorch |
| Attestable's 70B to 120B ZK prover | No, closed | Lean statement to reviewers only |
| Proof of useful work (cuPOW) | Yes, inside the Pearl monorepo | The "useful" binding is broken in practice |
| Idle-capacity exhaustion (the 85% bound) | No | Nothing public found |

Details:

- TOPLOC ships with a vLLM integration and Prime Intellect keeps an SGLang fork with it. DiFR and Token-DiFR have a vLLM integration and detect quantization or sampling changes within a few hundred tokens.
- Amodo's prototype is built on plain vLLM plus Token-DiFR, with the verifier running 2 to 8 times faster than the prover. Amodo says it will open-source its verification work, but no public repo for that prototype was found.
- Deterministic inference landed in SGLang and vLLM on top of the batch-invariant kernels. The pseudorandom padding trick hasn't been implemented anywhere found.
- DeepProve proves GPT-2, Gemma 3, and Llama 2 layers end to end, at about 7.6 minutes for 512 GPT-2 tokens on a CPU server. ZKTorch reports around 2,600 seconds per token on Llama-2-7B; zkPyTorch about 150 seconds per token on Llama-3 8B. None plug into an inference engine.
- cuPOW is open source in the Pearl repo with a vLLM miner, but a June 2026 study found Pearl's network does zero useful AI computation, because a miner feeding random matrices passes verification.
- One experimental repo, proof-of-compartmentalization under a "compute-verification" GitHub org, wires ZKTorch, SP1, and a cuPOW path into a Rust inference gateway with deterministic builds. Apache-2.0, one star, updated Jul 30, 2026. Looks like the PoComp work Luke Marks and Daniel Reuter described; the org hides its members.

Possible SL5 contribution: the padded-matmul batch-commit trick as a vLLM or SGLang plugin, since nobody has it, or an honest implementation of idle-capacity exhaustion.

Sources: TOPLOC (github.com/PrimeIntellect-ai/toploc, arXiv 2501.16007), DiFR (github.com/adamkarvonen/difr, arXiv 2511.20621), Amodo scaling post (amododesign.com/notes/2026-09-02-scaling-recomputation-inference-verification/), SGLang deterministic inference (sgl-project/sglang issue 10278), DeepProve (github.com/Lagrange-Labs/deep-prove), ezkl (github.com/zkonduit/ezkl), ZKTorch (arXiv 2507.07031), zkPyTorch (eprint 2025/535), Pearl (github.com/pearl-research-labs/pearl), cuPOW usefulness study (arXiv 2606.04819), proof-of-compartmentalization (github.com/compute-verification/proof-of-compartmentalization).

## What Attestable (Yogi Bar-On) is building

Attestable is an Israeli company founded in 2025. Yogi Bar-On is CEO (previously RAND, AI and national security). Technical founders: Shahar Papini (Unit 8200, StarkWare, Safe Superintelligence) and Shahar Samocha (StarkWare). About 15 people. $20M seed announced Aug 11, 2026, from TLV Partners and Altimeter.

The innovation: zero-knowledge proofs of LLM inference fast enough for production. The proof shows "this output came from this committed model on this input with this seed" without revealing weights, and the verifier never reruns the model. Academic systems took minutes per token on 7B to 8B models; Attestable's public post claims tens of tokens per second on a 31B model.

| System | Model | Proving speed (rough, different setups) |
|---|---|---|
| ZKTorch (academic, 2025) | Llama-2-7B | about 2,600 s per token |
| zkPyTorch (academic, 2025) | Llama-3 8B | about 150 s per token |
| Attestable (Aug 2026) | Gemma 4 31B, one H100 | 53 to 77 tokens per second |

Public figures (Gemma 4 31B, one H100): proofs of 4.35 to 7.92 MiB, verification of 157 to 648 ms on a CPU, cost independent of model size, hash-based (post-quantum, no trusted hardware or enclaves), 100 bits of security. Stated limits: 16K context cap, matmuls quantized to 8-bit integers with non-linear ops in floating point, some accuracy degradation, no stated slowdown versus plain inference.

From the chat, not public: implementations exist for a 70B dense model and a 120B-A5B mixture-of-experts model. The team is red-teaming a "ZK plus proof-of-work" scheme for resource exhaustion; the hard part is filling idle tensor cores without hurting real inference. Current claim: bounding 85% of compute with 10% overhead. They finished a Lean proof that the protocol is sound and want outside reviewers to check the Lean statement matches the plain-English guarantee, aiming for a protocol-independent zkML standard. Hardness assumptions: collision-resistant hashes and Fiat-Shamir; Fiat-Shamir flagged as needing more theory.

Where it fits: the "ZKPs on all inference" leg of the software-only phase 1. It gives correctness (declared work happened), not completeness (nothing else happened).

Caveats: closed source; reviewers get the Lean statement, some clients the full proof.

Sources: attestable.com, attestable.com/blog/proving-llms-scale, Calcalist (calcalistech.com/ctechnews/article/h1ddvrd8mg), Dealroom funding note, Yogi's launch post (x.com/Yogi_Brn/status/2087222696170103125).

## Built: llama-receipts (rungs 1 to 3)

`llama-receipts/` in this folder. Signed receipts, a Token-DiFR-style recompute verifier for quantized GGUF on llama.cpp, and a twelve-case attack matrix. 95 of 96 verdicts correct on qwen2.5 1.5B Q4_K_M. Findings: same-backend replay is bit-exact; sampler tampering leaves logits identical and needs the seeded-sampler replay; Metal-to-CPU drift on Q4_K_M reaches draw gaps of 0.43, so cross-backend thresholds are loose and one mild hidden-prompt attack slipped through at 48 tokens. Details in its README and `testset/results.md`.

## The explainer

`proving-the-forward-pass.html` in this folder is a nine-step interactive walkthrough of how ZK proofs verify inference (two-ball challenge, hashes, Merkle trees, constraints, random spot-checks, Fiat-Shamir, the full pipeline, correctness vs completeness). Published copy: https://claude.ai/code/artifact/bdeefe2b-f6f3-4986-92bf-2a680b382e15
