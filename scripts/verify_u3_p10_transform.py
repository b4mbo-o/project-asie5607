#!/usr/bin/env python3
"""Regression vectors for the recovered U3 Property-10 AES/CTS transform."""

from __future__ import annotations

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from inspect_ts_ca import mpeg2_crc32
from transform_u3_p10_stream import AES_KEY, BLOCK_XOR_MASK, transform_packet


# PID-0 record from the exact Linux good2 ch21 capture.  Its ciphertext is
# independent evidence retained in docs/capture hashes; no Windows binary is
# needed to run this regression.
RAW_PAT = bytes.fromhex(
    "476000169e07f9f7dcf77346334f4563ca65586a4ab8a9ca0b13d5b0efe14a3c"
    "be924aaa76fcb8bb4e36a9d65b39fcb7fea170beb529605e4cf65de4476078d45"
    "a520611b529605e4cf65de4476078d45a520611b529605e4cf65de4476078d45a"
    "520611b529605e4cf65de4476078d45a520611b529605e4cf65de4476078d45a5"
    "20611b529605e4cf65de4476078d45a520611b529605e4cf65de4476078d45a52"
    "0611b529605e4cf65de46f47bfa21af7a046c7df960918979699"
)

EXPECTED_PAT = bytes.fromhex(
    "476000160000b01d7fe4d300000000e0100420e1010421e1020422e10305a0ffc8"
    "d3d5531d" + "ff" * 151
)


def main() -> int:
    decryptor = Cipher(algorithms.AES(AES_KEY), modes.ECB()).decryptor()
    actual = transform_packet(RAW_PAT, decryptor, BLOCK_XOR_MASK)
    decryptor.finalize()
    if actual != EXPECTED_PAT:
        raise SystemExit(
            f"U3 P10 vector mismatch:\nactual={actual.hex()}\n"
            f"expected={EXPECTED_PAT.hex()}"
        )
    # Header (4), pointer field (1), then a complete PAT section of 32 bytes.
    section = actual[5:5 + 32]
    if mpeg2_crc32(section) != 0:
        raise SystemExit("recovered PAT has an invalid MPEG-2 CRC")
    print("U3 P10 exact PAT vector and MPEG-2 CRC pass")
    print(f"aes_key={AES_KEY.hex()} block_xor_mask={BLOCK_XOR_MASK.hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
