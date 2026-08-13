#!/usr/bin/env python3
"""Verify the response-free U3 replay template without the private PCAP.

The more specific smart-card privacy/classification audit lives in
``verify_u3_card_template.py``.
"""

from __future__ import annotations

import hashlib

from u3_control_template import TEMPLATE_WINDOWS, load_control_template
from u3_replay import sequence_for


EXPECTED = {
    "fixed boot before session 1": (
        377, "b16bdb05db36f9109b259f65566e3599631e0d2dfe926ce0d3ab296b5a7a93bd"),
    "fixed setup between sessions 1 and 2": (
        302, "91fe97926e06cff04b645057fa7dbd90be0920091d835b19400b4b8e67f4876e"),
    "session 2 before f018": (
        15, "016ee00f861dea552ed34b8dee1ca750a2fcae3eb82a89c2d35f8db7819117ad"),
    "session 2 card exchange and fixed setup": (
        359, "0a2345894a060f6ee72afd7a8ca4de366a9f35b2c8b91eee6bc28e333bc4d09a"),
    "session 3 before f018": (
        15, "bb636ee75651ebb7736938d454579c00637da19dd1e94419463f76193e13f755"),
    "session 3 card exchange and readiness wait": (
        343, "d241d72f10b49a229f7cbfa1f9e79856fb6031804dbc056e884df5f780768d59"),
    "ch21 tune and PID filters": (
        123, "b99e3599df45e04c08d14a56d6befbbd5b94098deab6cb7ccc8db2376d930e12"),
    "first start and Windows re-arm cycle": (
        62, "2f5ebc242f619b5c6be6c954ca8da3ce2180e5a2e240c6a80bed2ef542382978"),
}


def main() -> int:
    commands = load_control_template()
    if len(commands) != 1596:
        raise SystemExit(f"wrong total command count: {len(commands)}")
    out_payload_bytes = sum(
        len(command["request_data"])
        for command in commands
        if not command["bmrt"] & 0x80
    )
    if out_payload_bytes != 220:
        raise SystemExit(f"wrong OUT payload total: {out_payload_bytes}")
    for start, end, label in TEMPLATE_WINDOWS:
        sequence = sequence_for(commands, start, end).encode()
        count = sum(start <= command["t"] <= end for command in commands)
        digest = hashlib.sha256(sequence).hexdigest()
        if (count, digest) != EXPECTED[label]:
            raise SystemExit(
                f"{label}: count/hash {(count, digest)!r}, "
                f"expected {EXPECTED[label]!r}"
            )
        print(f"{label}: commands={count} sequence_sha256={digest}")
    print("U3 response-free normalized control template passes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
