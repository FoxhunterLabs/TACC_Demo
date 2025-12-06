# ---------------------------------------------------------------
# Telemetry-Anchored Chaotic Cipher (TACC) — Research Prototype
# ---------------------------------------------------------------
# WARNING: This is NOT secure cryptography.
#
# - Telemetry is synthetic (no real sensors).
# - The chaotic amplifier is not a proven PRF / KDF.
# - There is no reduction proof or security claim.
#
# This is a working demonstrator of the TACC architecture:
# physics-conditioned key evolution wrapped in AEAD
# (ChaCha20-Poly1305) for experimentation and review.
# ---------------------------------------------------------------

import argparse
import hashlib
import random
import secrets
import struct
import sys
from dataclasses import dataclass
from typing import Dict, Tuple

from Crypto.Cipher import ChaCha20_Poly1305 # pycryptodome


# ===============================================================
# Telemetry model (synthetic)
# ===============================================================

@dataclass
class TelemetryProfile:
"""Simple parameterization of a synthetic sensor environment."""
name: str
accel_noise: float # +/- range for accel components
temp_base: float # baseline temperature in °C
temp_jitter: float # +/- thermal wander
jitter_scale: float # timestamp jitter scale


TELEMETRY_PROFILES: Dict[str, TelemetryProfile] = {
"idle": TelemetryProfile(
name="Idle bench",
accel_noise=0.01,
temp_base=22.0,
temp_jitter=0.05,
jitter_scale=1e-4,
),
"rough": TelemetryProfile(
name="Rough motion",
accel_noise=0.25,
temp_base=27.0,
temp_jitter=0.25,
jitter_scale=1e-3,
),
"thermal_cycle": TelemetryProfile(
name="Thermal cycling",
accel_noise=0.03,
temp_base=24.0,
temp_jitter=1.25,
jitter_scale=5e-4,
),
}


class SyntheticTelemetrySource:
"""
Deterministic synthetic telemetry generator.

This is NOT a real sensor. It exists so both sides can
regenerate the same telemetry stream given the same
session_id + profile.
"""

def __init__(self, seed: int, profile: TelemetryProfile):
self.rng = random.Random(seed)
self.profile = profile

def sample(self) -> Tuple[float, float, float, float, float]:
"""
Returns (ax, ay, az, temp, jitter).
"""
p = self.profile
ax = self.rng.uniform(-p.accel_noise, p.accel_noise)
ay = self.rng.uniform(-p.accel_noise, p.accel_noise)
az = self.rng.uniform(-p.accel_noise, p.accel_noise)
temp = p.temp_base + self.rng.uniform(-p.temp_jitter, p.temp_jitter)
jitter = self.rng.uniform(0.0, p.jitter_scale)
return ax, ay, az, temp, jitter


# ===============================================================
# Entropy extraction & chaotic amplification
# ===============================================================

def extract_entropy(source: SyntheticTelemetrySource, samples: int = 32) -> bytes:
"""
NIST-style conditioning over a sliding window of telemetry.

Returns a 32-byte (256-bit) conditioned seed.
"""
buf = b""
for _ in range(samples):
t = source.sample()
packed = struct.pack("5f", *t) # 5 x float32
buf += hashlib.sha256(packed).digest()

return hashlib.sha256(buf).digest()


def arx_mix(seed: bytes, rounds: int = 8) -> bytes:
"""
ARX (Add-Rotate-Xor) mixing as a *chaotic amplifier*.

Deterministic scrambling, not a PRF. It magnifies small
differences in the seed into larger movements in keyspace.
"""
x = int.from_bytes(seed, "big")
bitlen = 8 * len(seed)
mask = (1 << bitlen) - 1

for _ in range(rounds):
# Weyl-style step
x = (x + 0x9E3779B97F4A7C15) & mask
# diffusion
x ^= (x << 7) & mask
x ^= (x >> 3)
# rotation
rot = 11
x = ((x << rot) | (x >> (bitlen - rot))) & mask

return x.to_bytes(len(seed), "big")


# ===============================================================
# Key evolution
# ===============================================================

def evolve_key(
session_id: bytes,
profile_name: str = "idle",
samples: int = 32,
rounds: int = 8,
):
"""
Derive a 256-bit key from:
- synthetic telemetry (profile + session_id)
- entropy extractor
- ARX-based chaotic amplifier

Returns (key, debug_dict).
"""
if profile_name not in TELEMETRY_PROFILES:
raise ValueError(f"Unknown telemetry profile: {profile_name}")

profile = TELEMETRY_PROFILES[profile_name]
src = SyntheticTelemetrySource(int.from_bytes(session_id, "big"), profile)

conditioned = extract_entropy(src, samples=samples)
chaotic = arx_mix(conditioned, rounds=rounds)

# Final key material (still not a formal KDF).
key = hashlib.sha256(b"TACC-DEMO" + chaotic).digest()

debug = {
"profile": profile.name,
"session_id": session_id.hex(),
"conditioned_seed": conditioned.hex(),
"chaotic_material": chaotic.hex(),
"key_fingerprint": hashlib.sha256(key).hexdigest()[:16],
}
return key, debug


# ===============================================================
# AEAD wrapper (ChaCha20-Poly1305)
# ===============================================================

MAGIC = b"TACC1" # version tag

def encrypt(
plaintext: bytes,
profile_name: str = "idle",
samples: int = 32,
rounds: int = 8,
):
"""
Encrypt with TACC-derived key + ChaCha20-Poly1305.

Wire format:
[5B MAGIC][16B session_id][12B nonce][ciphertext...][16B tag]

Returns (blob, debug_dict).
"""
session_id = secrets.token_bytes(16)

key, debug = evolve_key(
session_id=session_id,
profile_name=profile_name,
samples=samples,
rounds=rounds,
)

nonce = secrets.token_bytes(12)
cipher = ChaCha20_Poly1305.new(key=key, nonce=nonce)
ct, tag = cipher.encrypt_and_digest(plaintext)

header = MAGIC + session_id + nonce
blob = header + ct + tag

debug.update(
{
"nonce": nonce.hex(),
"tag": tag.hex(),
"ciphertext": ct.hex(),
"blob_len": str(len(blob)),
}
)
return blob, debug


def decrypt(
blob: bytes,
profile_name: str = "idle",
samples: int = 32,
rounds: int = 8,
) -> bytes:
"""
Decrypt a TACC blob. profile/samples/rounds must match sender.
"""
min_len = len(MAGIC) + 16 + 12 + 16
if len(blob) < min_len:
raise ValueError("Blob too short")

magic = blob[: len(MAGIC)]
if magic != MAGIC:
raise ValueError("Not a TACC payload")

session_id = blob[len(MAGIC) : len(MAGIC) + 16]
nonce = blob[len(MAGIC) + 16 : len(MAGIC) + 16 + 12]
ct = blob[len(MAGIC) + 16 + 12 : -16]
tag = blob[-16:]

key, _debug = evolve_key(
session_id=session_id,
profile_name=profile_name,
samples=samples,
rounds=rounds,
)

cipher = ChaCha20_Poly1305.new(key=key, nonce=nonce)
return cipher.decrypt_and_verify(ct, tag)


# ===============================================================
# CLI
# ===============================================================

def build_arg_parser() -> argparse.ArgumentParser:
parser = argparse.ArgumentParser(
description="TACC — Telemetry-Anchored Chaotic Cipher (research prototype)",
epilog=(
"WARNING: This is NOT secure cryptography.\n"
"It is a demonstrator for physics-conditioned key evolution."
),
)
sub = parser.add_subparsers(dest="cmd", required=True)

# encrypt
enc = sub.add_parser("enc", help="encrypt a UTF-8 string")
enc.add_argument("text", help="plaintext string")
enc.add_argument(
"--profile",
choices=list(TELEMETRY_PROFILES.keys()),
default="idle",
help="synthetic telemetry profile (default: idle)",
)
enc.add_argument(
"--samples",
type=int,
default=32,
help="telemetry samples (default: 32)",
)
enc.add_argument(
"--rounds",
type=int,
default=8,
help="ARX rounds (default: 8)",
)
enc.add_argument(
"--debug",
action="store_true",
help="print debug fingerprints to stderr",
)

# decrypt
dec = sub.add_parser("dec", help="decrypt a hex-encoded blob")
dec.add_argument("hex_blob", help="ciphertext blob (hex)")
dec.add_argument(
"--profile",
choices=list(TELEMETRY_PROFILES.keys()),
default="idle",
help="telemetry profile (must match sender)",
)
dec.add_argument(
"--samples",
type=int,
default=32,
help="telemetry samples (must match sender)",
)
dec.add_argument(
"--rounds",
type=int,
default=8,
help="ARX rounds (must match sender)",
)

return parser


def main() -> None:
parser = build_arg_parser()
args = parser.parse_args()

if args.cmd == "enc":
blob, debug = encrypt(
args.text.encode("utf-8"),
profile_name=args.profile,
samples=args.samples,
rounds=args.rounds,
)
# hex blob to stdout
print(blob.hex())

if args.debug:
print("\n[debug]", file=sys.stderr)
for k, v in debug.items():
print(f"{k}: {v}", file=sys.stderr)

elif args.cmd == "dec":
try:
raw = bytes.fromhex(args.hex_blob.strip())
except ValueError:
print("Input is not valid hex", file=sys.stderr)
sys.exit(1)

try:
pt = decrypt(
raw,
profile_name=args.profile,
samples=args.samples,
rounds=args.rounds,
)
print(pt.decode("utf-8", errors="replace"))
except Exception as e:
print(f"Decryption failed: {e}", file=sys.stderr)
sys.exit(2)


if __name__ == "__main__":
main()
