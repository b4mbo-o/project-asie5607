#!/usr/bin/env python3
"""Pure implementation of the MonsterTV U3 16-byte f010 response."""

from __future__ import annotations

import argparse


ZERO_RESPONSE = bytes.fromhex("e12c84c152b818e73639451d210139b8")

# Ordinary challenge bytes are a fixed permutation/XOR.  Challenge bytes 1
# and 8 are handled below because the protected routine fans them out.
PERMUTATION = {
    0: 14,
    2: 4,
    3: 6,
    4: 11,
    5: 13,
    6: 3,
    7: 2,
    9: 7,
    10: 5,
    11: 0,
    12: 15,
    13: 12,
    14: 1,
    15: 10,
}
BYTE1_OUTPUTS = (2, 3, 4, 5, 6, 8, 12, 15)
BYTE8_COMMON_OUTPUTS = (0, 1, 3, 7, 8, 10, 11, 13, 14)


def _byte8_feedback(value: int) -> int:
    """Return the protected routine's even feedback byte for challenge[8]."""
    bit0 = value & 1
    bit1 = bit0 & ((value >> 1) & 1)
    bit2 = ((value >> 2) & 1) | bit1
    bit3 = ((value >> 3) & 1) & bit2
    bit4 = ((value >> 4) & 1) & bit3
    bit5 = ((value >> 5) & 1) & bit4
    bit6 = ((value >> 6) & 1) | bit5
    folded = (
        bit0 | bit1 << 1 | bit2 << 2 | bit3 << 3
        | bit4 << 4 | bit5 << 5 | bit6 << 6
    )
    return folded << 1


def f010_response(challenge: bytes) -> bytes:
    """Return the exact response emitted by protected driver FUN_00018494."""
    if len(challenge) != 16:
        raise ValueError("f010 challenge must be exactly 16 bytes")
    response = bytearray(ZERO_RESPONSE)
    for input_offset, output_offset in PERMUTATION.items():
        response[output_offset] ^= challenge[input_offset]

    value1 = challenge[1]
    for output_offset in BYTE1_OUTPUTS:
        response[output_offset] ^= value1

    value8 = challenge[8]
    feedback = _byte8_feedback(value8)
    common = value8 ^ feedback
    for output_offset in BYTE8_COMMON_OUTPUTS:
        response[output_offset] ^= common
    response[9] ^= feedback
    return bytes(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("challenge", help="32 hexadecimal digits")
    args = parser.parse_args()
    try:
        challenge = bytes.fromhex(args.challenge)
    except ValueError as error:
        parser.error(str(error))
    if len(challenge) != 16:
        parser.error("challenge must be exactly 32 hexadecimal digits")
    print(f010_response(challenge).hex())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
