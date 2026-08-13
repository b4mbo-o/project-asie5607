"""Driver-derived U3 BS/110-degree-CS transponder tuning controls."""

from __future__ import annotations

from dataclasses import dataclass

from u3_channels import U3Channel


@dataclass(frozen=True)
class SatelliteTransponder:
    system: str
    transponder: int
    frequency_khz: int
    pll: bytes
    final: int


# Exact 24-entry table built by SKNET_HDTV_BS_CS_BDA.sys FUN_0001f796.
# Entries are BS1,3,...23 followed by ND/CS2,4,...24.
SATELLITE_TRANSPONDERS = tuple(
    SatelliteTransponder(system, transponder, frequency, bytes.fromhex(pll), final)
    for system, transponder, frequency, pll, final in (
        ("BS", 1, 11727480, "08330008", 0x02),
        ("BS", 3, 11765840, "04400000", 0x02),
        ("BS", 5, 11804200, "04662000", 0x22),
        ("BS", 7, 11842560, "048d2000", 0x22),
        ("BS", 9, 11880920, "04b34000", 0x42),
        ("BS", 11, 11919280, "04d94000", 0x42),
        ("BS", 13, 11957640, "05004000", 0x42),
        ("BS", 15, 11996000, "05264000", 0x42),
        ("BS", 17, 12034360, "054c4000", 0x42),
        ("BS", 19, 12072720, "05734000", 0x42),
        ("BS", 21, 12111080, "05995000", 0x52),
        ("BS", 23, 12149440, "05bf5000", 0x52),
        ("CS", 2, 12291000, "064d7100", 0x73),
        ("CS", 4, 12331000, "06757100", 0x73),
        ("CS", 6, 12371000, "069d7100", 0x73),
        ("CS", 8, 12411000, "06c57100", 0x73),
        ("CS", 10, 12451000, "06ed7100", 0x73),
        ("CS", 12, 12491000, "07157100", 0x73),
        ("CS", 14, 12531000, "073d7100", 0x73),
        ("CS", 16, 12571000, "07657100", 0x73),
        ("CS", 18, 12611000, "078d7100", 0x73),
        ("CS", 20, 12651000, "07b57100", 0x73),
        ("CS", 22, 12691000, "07dd7100", 0x73),
        ("CS", 24, 12731000, "08057100", 0x73),
    )
)


def satellite_transponder(channel: U3Channel) -> SatelliteTransponder:
    if channel.system not in ("BS", "CS"):
        raise ValueError("a BS or CS selector is required")
    return next(
        item for item in SATELLITE_TRANSPONDERS
        if item.system == channel.system and item.transponder == channel.value
    )


# delay_ms, request, wValue, wIndex, wLength.  Every command is vendor IN;
# no USB response or card payload is retained here.
Control = tuple[float, int, int, int, int]


ENTER_SATELLITE: tuple[Control, ...] = (
    (0, 0x03, 0x2530, 0x0000, 2), (0, 0x03, 0x2330, 0x004D, 2),
    (1, 0x03, 0x0330, 0x0090, 2),
    (1, 0x0D, 0xFE00, 0x0FC0, 4), (1, 0x0D, 0x0003, 0x0000, 2),
    (1, 0x0E, 0x0030, 0x0000, 5),
    (2, 0x0D, 0xFE00, 0x01C0, 4), (1, 0x0D, 0x0003, 0x0000, 2),
    (1, 0x0E, 0x0030, 0x0000, 5),
    (1, 0x0D, 0xFE00, 0x02C0, 4), (1, 0x0D, 0x0003, 0x0008, 3),
    (1, 0x0E, 0x0032, 0x0000, 6),
    (2, 0x0D, 0xFE00, 0x19C0, 4), (1, 0x0D, 0x6003, 0x0008, 2),
    (1, 0x0E, 0x0032, 0x0000, 5),
    (1, 0x0D, 0xFE00, 0x20C0, 4), (1, 0x0D, 0x0003, 0x0008, 2),
    (1, 0x0E, 0x0032, 0x0000, 5),
    (2, 0x0D, 0xFE00, 0x0EC0, 4), (1, 0x0D, 0x6F03, 0x0008, 2),
    (1, 0x0E, 0x0032, 0x0000, 5),
    (1, 0x03, 0x1732, 0x0000, 2), (1, 0x03, 0x8F32, 0x00FF, 2),
    (1, 0x03, 0x9032, 0x00FF, 2),
)

RETUNE_SATELLITE: tuple[Control, ...] = (
    (0, 0x03, 0x2532, 0x0000, 2),
    (1, 0x03, 0x2332, 0x004D, 2),
    (1, 0x03, 0x8F32, 0x0040, 2),
)

LEAVE_SATELLITE: tuple[Control, ...] = (
    (0, 0x03, 0x2532, 0x0000, 2), (0, 0x03, 0x2332, 0x004D, 2),
    (1, 0x03, 0x1732, 0x0001, 2),
    (1, 0x0D, 0xFE00, 0x0EC0, 4), (1, 0x0D, 0x2F03, 0x0000, 2),
    (1, 0x0E, 0x0032, 0x0000, 5),
    (2, 0x0D, 0xFE00, 0x16C0, 4), (1, 0x0D, 0x0003, 0x0000, 2),
    (1, 0x0E, 0x0032, 0x0000, 5),
    (1, 0x0D, 0xFE00, 0x02C0, 4), (1, 0x0D, 0x0C03, 0x00F6, 3),
    (1, 0x0E, 0x0032, 0x0000, 6),
    (2, 0x0D, 0xFE00, 0x19C0, 4), (1, 0x0D, 0x4003, 0x00F6, 2),
    (1, 0x0E, 0x0032, 0x0000, 5),
    (1, 0x0D, 0xFE00, 0x20C0, 4), (1, 0x0D, 0x0803, 0x00F6, 2),
    (1, 0x0E, 0x0032, 0x0000, 5),
    (2, 0x03, 0x1E30, 0x00AA, 2), (1, 0x03, 0x1F30, 0x00A8, 2),
)

FILTER_GROUP: tuple[Control, ...] = (
    (92, 0x03, 0x0F30, 0x003C, 2), (0, 0x03, 0x0332, 0x0001, 2),
    (1, 0x03, 0x2332, 0x004C, 2), (1, 0x02, 0x1C32, 0x0000, 2),
    (2, 0x03, 0x1C32, 0x000B, 2),
    (1, 0x04, 0x0000, 0x0000, 33), (1, 0x04, 0x0020, 0x0000, 33),
    (1, 0x04, 0x0040, 0x0000, 6), (1, 0x09, 0x0100, 0x0000, 1),
    (1, 0x00, 0x0000, 0x0000, 33),
    (142, 0x05, 0x003F, 0x1F0F, 4), (2, 0x05, 0xFF42, 0xFF1F, 4),
    (1, 0x05, 0x1F41, 0x00FF, 3), (1, 0x05, 0x1F43, 0x00FF, 3),
    (2, 0x25, 0x045A, 0xF001, 1),
)

ENTER_SATELLITE_SUFFIX: tuple[Control, ...] = (
    (3, 0x25, 0x045A, 0xF001, 1), (60, 0x00, 0x0000, 0x0000, 33),
    (39, 0x03, 0x0F30, 0x003C, 2), (0, 0x03, 0x0332, 0x0001, 2),
    (1, 0x03, 0x2332, 0x004C, 2), (1, 0x02, 0x1C32, 0x0000, 2),
    (3, 0x03, 0x1C32, 0x000B, 2),
    (1, 0x04, 0x0000, 0x0000, 33), (1, 0x04, 0x0020, 0x0000, 33),
    (1, 0x04, 0x0040, 0x0000, 6), (1, 0x09, 0x0100, 0x0000, 1),
    (53, 0x00, 0x0000, 0x0000, 33),
    (98, 0x05, 0x003F, 0x1F0F, 4), (2, 0x05, 0xFF42, 0xFF1F, 4),
    (1, 0x05, 0x1F41, 0x00FF, 3), (1, 0x05, 0x1F43, 0x00FF, 3),
    (52, 0x03, 0x8F32, 0x0040, 2), (0, 0x03, 0x9032, 0x00D0, 2),
    (1, 0x04, 0x0000, 0x0000, 33), (1, 0x04, 0x0020, 0x0000, 33),
    (1, 0x04, 0x0040, 0x0000, 6), (1, 0x09, 0x0100, 0x0000, 1),
    (41, 0x00, 0x0000, 0x0000, 33),
    (109, 0x05, 0x003F, 0x1F0F, 4), (2, 0x05, 0xFF42, 0xFF1F, 4),
    (1, 0x05, 0x1F41, 0x00FF, 3), (1, 0x05, 0x1F43, 0x00FF, 3),
)


def _entry_controls(item: SatelliteTransponder) -> tuple[Control, ...]:
    a, b, c, d = item.pll
    return (
        (1, 0x0D, 0xFE00, 0x00C0, 4),
        (1, 0x0D, (a << 8) | 0x03, (c << 8) | b, 4),
        (1, 0x0D, (d << 8) | 0x06, 0x0000, 2),
        (1, 0x0E, 0x0032, 0x0000, 8),
        (2, 0x0D, 0xFE00, 0x02C0, 4),
        (1, 0x0D, (item.final << 8) | 0x03, 0x0000, 2),
        (1, 0x0E, 0x0032, 0x0000, 5),
    )


def render_controls(controls: tuple[Control, ...]) -> str:
    lines = [
        "# Driver-derived fixed U3 satellite controls; no captured responses.",
        "# delay_ms direction request wValue wIndex wLength data-or-dash",
    ]
    lines += [
        f"{delay:.3f} in 0x{request:02x} 0x{value:04x} "
        f"0x{index:04x} {length} -"
        for delay, request, value, index, length in controls
    ]
    return "\n".join(lines) + "\n"


def satellite_tune_sequence(channel: U3Channel, entering: bool) -> str:
    item = satellite_transponder(channel)
    prefix = ENTER_SATELLITE if entering else RETUNE_SATELLITE
    # The first terrestrial->satellite transition needs the complete mode
    # setup.  A satellite->satellite retune needs only the common filter pass.
    suffix = (
        ENTER_SATELLITE_SUFFIX
        if entering else ((9, 0x00, 0x0000, 0x0000, 33),) + FILTER_GROUP
    )
    controls = prefix + _entry_controls(item) + suffix
    return render_controls(controls)


def leave_satellite_sequence() -> str:
    return render_controls(LEAVE_SATELLITE)


__all__ = [
    "SATELLITE_TRANSPONDERS", "SatelliteTransponder", "leave_satellite_sequence",
    "satellite_transponder", "satellite_tune_sequence",
]
