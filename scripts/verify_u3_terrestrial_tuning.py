#!/usr/bin/env python3
"""Verify U3 ch13..62 frequency patching against the normalized template."""

from __future__ import annotations

from u3_control_template import load_control_template
from u3_terrestrial_tuning import patch_terrestrial_tune


def frequency_writes(commands: list[dict]) -> dict[int, int]:
    result: dict[int, int] = {}
    pending: int | None = None
    for command in commands:
        if (
            command["req"] == 0x0D
            and command["value"] == 0xFE00
            and command["index"] in (0x0DC0, 0x0EC0)
        ):
            pending = command["index"] >> 8
        elif pending is not None:
            if command["req"] == 0x0D and (command["value"] & 0xFF) == 0x03:
                result[pending] = command["value"] >> 8
            pending = None
    return result


def main() -> int:
    commands = load_control_template()
    window = [
        command for command in commands if 35.558 <= command["t"] <= 35.843
    ]
    original = frequency_writes(window)
    if original != {0x0D: 0x49, 0x0E: 0x82}:
        raise SystemExit(f"unexpected good2 ch21 frequency bytes: {original}")
    for channel, expected_word in ((13, 0x7649), (21, 0x8249), (62, 0xBFC9)):
        patched, frequency_khz, word = patch_terrestrial_tune(window, channel)
        if word != expected_word:
            raise SystemExit(
                f"ch{channel}: word=0x{word:04x}, expected 0x{expected_word:04x}"
            )
        writes = frequency_writes(patched)
        if writes != {0x0D: word & 0xFF, 0x0E: word >> 8}:
            raise SystemExit(f"ch{channel}: wrong patched writes {writes}")
        changed = sum(a != b for a, b in zip(window, patched))
        expected_changes = (word & 0xFF != 0x49) + (word >> 8 != 0x82)
        if changed != expected_changes:
            raise SystemExit(
                f"ch{channel}: changed {changed} commands, expected {expected_changes}"
            )
        print(
            f"ch{channel}: center={frequency_khz}kHz word=0x{word:04x} "
            f"writes=0d:{writes[0x0D]:02x}/0e:{writes[0x0E]:02x} "
            f"changed={changed}"
        )
    print("U3 terrestrial tune patch vectors pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
