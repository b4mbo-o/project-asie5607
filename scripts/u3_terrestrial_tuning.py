#!/usr/bin/env python3
"""Patch the U3 terrestrial tuner-frequency writes in a control template."""

from __future__ import annotations


def terrestrial_frequency(channel: int) -> tuple[int, int]:
    """Return ISDB-T centre kHz and the U3's 16-bit 1/64-MHz word."""
    if not 13 <= channel <= 62:
        raise ValueError("terrestrial physical channel must be in 13..62")
    frequency_khz = 473_143 + (channel - 13) * 6_000
    tuner_word = frequency_khz * 64 // 1_000
    return frequency_khz, tuner_word


def patch_terrestrial_tune(
    commands: list[dict], channel: int
) -> tuple[list[dict], int, int]:
    """Replace the reg 0x0d/0x0e frequency bytes in a U3 tune window.

    The U3 sequence selects a demod/tuner register with request 0x0d,
    ``wValue=0xfe00`` and ``wIndex=reg<<8|0xc0``.  The immediately following
    request 0x0d carries the data byte in wValue's high byte and opcode 0x03
    in its low byte.  Only selectors for frequency registers 0x0d and 0x0e
    are modified; the surrounding tuner and PID-filter setup stays exact.
    """
    frequency_khz, tuner_word = terrestrial_frequency(channel)
    values = {0x0D: tuner_word & 0xFF, 0x0E: tuner_word >> 8}
    patched = [dict(command) for command in commands]
    counts = {0x0D: 0, 0x0E: 0}
    pending: int | None = None
    frequency_pair_started = False
    for command in patched:
        if (
            command["req"] == 0x0D
            and command["value"] == 0xFE00
            and command["index"] in (0x0DC0, 0x0EC0)
        ):
            selected = command["index"] >> 8
            # The window contains an unrelated early reg-0x0e setup write.
            # The actual frequency high byte is the reg-0x0e write following
            # the unique reg-0x0d frequency low byte.
            if selected == 0x0D:
                pending = selected
            elif frequency_pair_started and counts[0x0E] == 0:
                pending = selected
            else:
                pending = None
            continue
        if pending is None:
            continue
        if (
            command["req"] == 0x0D
            and (command["value"] & 0xFF) == 0x03
            and command["index"] == 0
        ):
            command["value"] = values[pending] << 8 | 0x03
            counts[pending] += 1
            if pending == 0x0D:
                frequency_pair_started = True
        pending = None
    if counts != {0x0D: 1, 0x0E: 1}:
        raise ValueError(
            "template does not contain exactly one complete U3 terrestrial "
            f"frequency pair (counts={counts})"
        )
    return patched, frequency_khz, tuner_word
