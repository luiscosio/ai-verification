# Groth16 circuits and verification keys

One directory per compiled instance of `code/llama.cpp/examples/receipts/zk/groth16/qdot_rows.circom`: `main.circom` is the one-line instantiation (rows per proof, K) and `verification_key.json` is what a verifier needs. The instance a proof uses is named in the manifest's tensor entry (`groth16.circuit`), so a verifier picks `registry/circuits/<circuit>/verification_key.json`.

Toolchain: circom 2.2.3, snarkjs 0.7.5, circomlib 2.0.5. Parameters: a locally generated 2^18 powers of tau (`snarkjs powersoftau new bn128 18`, one contribution, `prepare phase2`), SHA-256 `a6985229b8a639691dfb24174b8374c1686d50135a5eeacdeb8d8d6c209c67f1`, and one phase-2 contribution per instance. Proof-of-concept parameters: a prover who ran this setup could forge. A deployment replaces them with a public ceremony's file and a multi-party phase 2, which changes every key here.

Prover material (the zkeys, 78 to 108 MB each, and the parameters file) is not in git. Publishing matching release assets is still pending. It can be regenerated with `setup.sh`, in which case the verification keys and registration here must be replaced too, because a new setup is a new key pair. Regenerating setup is not installation of the existing model registration.

| Instance | zkey SHA-256 (prefix) | zkey bytes |
|---|---|---|
| `r16_k1536` | 951f9eaf5c5cf1ca... | 107704480 |
| `r16_k1024` | a565c0f1f2ecb2db... | 77878592 |
| `r8_k2048` | 0b27a7a312481619... | 78251328 |
| `r8_k3072` | 14d0861edec75aa6... | 108263584 |

Registration/v1 pins SHA-256 digests of canonical sorted-key JSON verification keys, plus the circuit source, verifier source and setup file digests. Weight commitments and keys are unchanged by the September 13 verifier-policy repair, but the manifest ID changes. Obtain the new manifest independently; do not substitute a manifest supplied by a proof. `register.py --check` validates these material identities against installed files. `--commit` and `--groth16` explicitly request commitment recomputation; without them a metadata check is not a full independent registration audit.
