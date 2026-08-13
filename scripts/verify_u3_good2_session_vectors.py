#!/usr/bin/env python3
"""Verify driver-independent exact-good2 U3 secure-session wire vectors."""

from __future__ import annotations

import hashlib

from u3_f010_transform import f010_response
from u3_good2_secure_material import GOOD2_SESSIONS, PUBLIC_EXPONENT
from u3_session_prefix import build_sequence_from_values


VECTORS = {
    11: {
        "modulus": "aab0cf93ab6e00cb",
        "wire": "cb006eab93cfb0aa",
        "challenge": "2a349e032403aab8d77344fab1558f4b",
        "response": "42fa0806f8c82fcd5bb75760405b4a3d",
        "prefix_sha256": "949e071681b6fd79bcda35a728259dea9e79ff08ed3a29eb099820631bd70b77",
    },
    8: {
        "modulus": "a56c5836a5f97557",
        "wire": "5775f9a536586ca5",
        "challenge": "940ee83d5e3d149231cd7e500b2bf905",
        "response": "82e618e8b4c82b190b3b7370040f9ebd",
        "f018": "d78abfbcc80ee18c50e16a8d463fcd3444a1984dd42288a2",
        "prefix_sha256": "e877e2bfbaf4e97364a58fe8d7d816fa989e4dbcb54b3f93c68d9288af6a5c9c",
    },
    7: {
        "modulus": "bb33161577e63cc7",
        "wire": "c73ce677151633bb",
        "challenge": "dee02aafa8af5e54731fc89655c13be7",
        "response": "8aea3082989057052bb75f4800531a0d",
        "f018": "ab454a5d36d0d36f8fa87d1b9540b661ba21ecd1ee281d49",
        "prefix_sha256": "5655b81e9b96d1390f1aa5eba9e28533f971406e31411262951f2f39dcf08819",
    },
}


def main() -> int:
    for index, expected in VECTORS.items():
        material = GOOD2_SESSIONS[index]
        sequence, wire = build_sequence_from_values(
            index, material["modulus"], PUBLIC_EXPONENT, material["table_entry"]
        )
        actual = {
            "modulus": material["modulus"].hex(),
            "wire": wire.hex(),
            "response": f010_response(
                bytes.fromhex(expected["challenge"])
            ).hex(),
            "prefix_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
        }
        if "f018" in expected:
            actual["f018"] = material["f018"].hex()
        for field, value in actual.items():
            wanted = expected[field]
            print(f"index={index} {field}={value} match={value == wanted}")
            if value != wanted:
                raise SystemExit(
                    f"index {index} {field}: got {value}, expected {wanted}"
                )
    print("all driver-independent exact-good2 secure-session vectors pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
