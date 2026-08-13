#!/usr/bin/env python3
"""Audit the normalized U3 template's smart-card proxy payloads.

The template intentionally retains host-issued OUT controls but never USB IN
completion data.  This regression pins every encrypted eight-byte card block
to the small, fixed ISO 7816 T=1 startup frames recovered from the driver call
sites and independently reproduced with the original transform oracle.
"""

from __future__ import annotations

from u3_control_template import load_control_template


# (table row, logical T=1 frame, bit-oriented input, encrypted proxy blocks)
# The logical frame is obtained by reversing the bits in each byte of the
# bit-oriented input.  It includes NAD, PCB, LEN, INF and LRC.
EXPECTED_GROUPS = (
    (8, "00c101fe3e", "0083807f7c", ("e28a4f755717e32e",)),
    (8, "0000059032000000a7", "0000a0094c000000e5",
     ("2eca0714905d0631", "dcfbd0eb2dc0f683")),
    (8, "0040059032000000e7", "0002a0094c000000e7",
     ("ec594bd5a0e3ec19", "e84f543cd5476b0e")),
    (7, "00c101fe3e", "0083807f7c", ("5726831f91824204",)),
    (7, "0000059032000000a7", "0000a0094c000000e5",
     ("45546325dabc2975", "0d222216b1f3e74a")),
    (7, "0040059032000000e7", "0002a0094c000000e7",
     ("a7d075f942c3c185", "be0e23420153707a")),
    (7, "0000059030000000a5", "0000a0090c000000a5",
     ("61374d1b16c6ae3b", "646caeb360a1f67d")),
    # The row-7 card-ID retry occurs once more after the initial-settings
    # response, so its encrypted pair is intentionally repeated.
    (7, "0040059032000000e7", "0002a0094c000000e7",
     ("a7d075f942c3c185", "be0e23420153707a")),
)


def main() -> int:
    commands = load_control_template()

    for number, command in enumerate(commands, 1):
        if command["bmrt"] & 0x80 and command["request_data"]:
            raise SystemExit(f"IN command {number} retained response data")

    observed = [
        command["request_data"].hex()
        for command in commands
        if not command["bmrt"] & 0x80
        and command["req"] == 0x26
        and command["index"] & 0xFFF8 == 0xF080
        and command["length"] == 8
    ]
    expected = [block for group in EXPECTED_GROUPS for block in group[3]]
    if observed != expected:
        raise SystemExit(
            "card proxy OUT sequence differs:\n"
            f"observed={observed!r}\nexpected={expected!r}"
        )

    for row, logical, oriented, blocks in EXPECTED_GROUPS:
        reversed_bytes = bytes(
            int(f"{byte:08b}"[::-1], 2) for byte in bytes.fromhex(oriented)
        ).hex()
        if reversed_bytes != logical:
            raise SystemExit(
                f"row {row}: bad bit-order annotation {reversed_bytes} != {logical}"
            )
        inf = bytes.fromhex(logical)[3:-1]
        label = {
            bytes.fromhex("fe"): "T=1 IFS",
            bytes.fromhex("9032000000"): "B-CAS card-ID (90 32)",
            bytes.fromhex("9030000000"): "B-CAS initial-settings (90 30)",
        }.get(inf, inf.hex())
        print(
            f"row={row} {label}: frame={logical} "
            f"encrypted_blocks={','.join(blocks)}"
        )

    print(
        "U3 card template passes: 14 OUT blocks are fixed T=1 startup "
        "commands; retained IN payload bytes=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
