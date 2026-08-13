#!/usr/bin/env python3
"""Verify that both persistent-retune windows receive the target frequency."""

from __future__ import annotations

from u3_control_template import load_control_template
from u3_persistent_retune import retune_sequences
from u3_terrestrial_tuning import terrestrial_frequency


def sequence_frequency_bytes(sequence: str) -> tuple[int, int]:
    rows = [
        line.split()
        for line in sequence.splitlines()
        if line and not line.startswith("#")
    ]
    low_position = next(
        index
        for index, row in enumerate(rows)
        if int(row[2], 0) == 0x0D
        and int(row[3], 0) == 0xFE00
        and int(row[4], 0) == 0x0DC0
    )
    low = int(rows[low_position + 1][3], 0) >> 8
    high_position = next(
        index
        for index, row in enumerate(rows[low_position + 2 :], low_position + 2)
        if int(row[2], 0) == 0x0D
        and int(row[3], 0) == 0xFE00
        and int(row[4], 0) == 0x0EC0
    )
    high = int(rows[high_position + 1][3], 0) >> 8
    return low, high


def main() -> int:
    commands = load_control_template()
    for channel in (13, 21, 22, 62):
        tune, rearm, frequency_khz, tuner_word = retune_sequences(commands, channel)
        expected_frequency, expected_word = terrestrial_frequency(channel)
        expected_bytes = (expected_word & 0xFF, expected_word >> 8)
        assert frequency_khz == expected_frequency
        assert tuner_word == expected_word
        assert sequence_frequency_bytes(tune) == expected_bytes
        assert sequence_frequency_bytes(rearm) == expected_bytes
    print("U3 persistent retune sequences verified for channels 13, 21, 22, and 62")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
