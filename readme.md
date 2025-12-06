________________________________________
# Telemetry-Anchored Chaotic Cipher (TACC)
**Research Prototype — Not Secure Cryptography**

TACC is an experimental cipher demonstrating physics-conditioned key evolution using synthetic telemetry, entropy conditioning, chaotic ARX mixing, and a final AEAD wrapper (ChaCha20-Poly1305). It is intended for research, analysis, and experimentation only. **Do not use TACC for real-world security.**

---

## ⚠️ Security Disclaimer
TACC is not a secure cryptographic system.

- Telemetry comes from a deterministic synthetic model.
- The chaotic amplifier is not a proven PRF or KDF.
- No security reduction, proofs, or hardness assumptions exist.
- Outputs should be treated as **non-cryptographic**.

This system is a **demonstrator**, not a cryptosystem.

---

## Overview
TACC explores whether synthetic, physics-inspired telemetry streams can be used to deterministically evolve session keys. The key path is:

1. **Synthetic Telemetry**  
   A seeded pseudo-environment produces accel noise, temperature jitter, and timestamp jitter.

2. **Entropy Extraction**  
   Each sample is packed and hashed with SHA-256; the concatenated buffer is SHA-256 again.

3. **Chaotic ARX Amplification**  
   A Weyl-step + ARX mix magnifies bit-level differences.  
   This is *not* a secure construction—just a study in sensitivity and diffusion.

4. **Final Key Material**  
   `SHA256("TACC-DEMO" || chaotic_output)` → 256-bit key.

5. **AEAD**  
   ChaCha20-Poly1305 encrypts and authenticates the payload.

---

## Wire Format
All encrypted messages follow:

[5-byte MAGIC][16-byte session_id][12-byte nonce][ciphertext][16-byte tag]

Where:
- MAGIC = `b"TACC1"`
- `session_id` seeds the telemetry generator
- `nonce` is randomly generated for ChaCha20-Poly1305
- `ciphertext` and `tag` come from AEAD

---

## Telemetry Profiles
Three built-in profiles model different synthetic environments:

- **idle** — minimal noise, stable temperature  
- **rough** — high acceleration noise, moderate temperature wander  
- **thermal_cycle** — stable accel but large thermal excursions  

All telemetry is deterministic given `(session_id, profile)`.

---

## CLI Usage

### Encrypt
```bash
python tacc.py enc "hello world"
With options:
python tacc.py enc "text" --profile rough --samples 64 --rounds 12 --debug
Decrypt
python tacc.py dec <hex_blob>
Options must match the sender:
python tacc.py dec <hex_blob> --profile rough --samples 64 --rounds 12
________________________________________
API Summary
encrypt(plaintext, profile_name, samples, rounds)
Derives a session key, encrypts via ChaCha20-Poly1305, and returns (blob, debug_info).
decrypt(blob, profile_name, samples, rounds)
Validates magic header, reconstructs key, and verifies ciphertext.
evolve_key(session_id, profile_name, samples, rounds)
Runs telemetry extraction → conditioning → chaotic amplifier → SHA-256 finalization.
________________________________________
Design Intent
TACC exists to explore:
•	Deterministic telemetry-driven key evolution
•	Sensitivity to microvariations in pseudo-sensor data
•	Using ARX-based chaotic functions for mixing
•	Behavior of hybrid physical/algorithmic entropy sources
•	Auditability and reproducibility of synthetic environments
It is designed for researchers, hobbyists, and reviewers interested in unconventional key-evolution mechanisms—not end-users seeking security.
________________________________________
Limitations
•	Not secure; no claims of confidentiality or integrity beyond ChaCha20-Poly1305.
•	Telemetry lacks unpredictability.
•	No formal cryptanalysis.
•	Entire design is experimental and should not be embedded in other systems.
________________________________________
License
MIT
