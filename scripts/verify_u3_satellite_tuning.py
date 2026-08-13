#!/usr/bin/env python3
"""Verify U3 satellite table, selectors, and driver-derived control rows."""

from __future__ import annotations

from u3_channels import parse_u3_channel
from u3_satellite_tuning import (
    SATELLITE_TRANSPONDERS, leave_satellite_sequence,
    satellite_transponder, satellite_tune_sequence,
)


def setup_rows(sequence: str) -> list[tuple[str, int, int, int, int]]:
    rows = []
    for line in sequence.splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        rows.append(
            (fields[1], int(fields[2], 0), int(fields[3], 0),
             int(fields[4], 0), int(fields[5], 0))
        )
    return rows


def main() -> int:
    assert len(SATELLITE_TRANSPONDERS) == 24
    assert [item.transponder for item in SATELLITE_TRANSPONDERS[:12]] == list(
        range(1, 24, 2)
    )
    assert [item.transponder for item in SATELLITE_TRANSPONDERS[12:]] == list(
        range(2, 25, 2)
    )
    assert all(
        right.frequency_khz > left.frequency_khz
        for left, right in zip(SATELLITE_TRANSPONDERS, SATELLITE_TRANSPONDERS[1:])
    )

    bs = parse_u3_channel("BS141")
    assert bs == parse_u3_channel("BS13_0") == parse_u3_channel("BSNITTELE")
    bs_item = satellite_transponder(bs)
    assert (bs_item.frequency_khz, bs_item.pll, bs_item.final) == (
        11_957_640, bytes.fromhex("05004000"), 0x42
    )
    bs_rows = setup_rows(satellite_tune_sequence(bs, entering=True))
    assert len(bs_rows) == 58
    assert all(direction == "in" for direction, *_ in bs_rows)
    assert ("in", 0x0D, 0x6F03, 0x0008, 2) in bs_rows
    assert ("in", 0x0D, 0x0503, 0x4000, 4) in bs_rows
    assert ("in", 0x0D, 0x4203, 0x0000, 2) in bs_rows

    cs = parse_u3_channel("CS161")
    assert cs == parse_u3_channel("CS22") == parse_u3_channel("QVC")
    cs_item = satellite_transponder(cs)
    assert (cs_item.frequency_khz, cs_item.pll, cs_item.final) == (
        12_691_000, bytes.fromhex("07dd7100"), 0x73
    )
    cs_rows = setup_rows(satellite_tune_sequence(cs, entering=False))
    assert len(cs_rows) == 26
    assert ("in", 0x0D, 0x0703, 0x71DD, 4) in cs_rows
    assert ("in", 0x0D, 0x7303, 0x0000, 2) in cs_rows

    assert len(setup_rows(leave_satellite_sequence())) == 20
    print("U3 BS/CS 24-entry table and transition controls verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
