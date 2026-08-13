"""Build U3 proxy session-prefix controls from explicit public wire values."""

from __future__ import annotations


def _emit_write(lines: list[str], delay: float, value: int, data: bytes) -> None:
    lines.append(
        f"{delay:.3f} out 0x26 0x{value:04x} 0xf001 "
        f"{len(data)} {data.hex()}"
    )


def build_sequence_from_values(
    index: int, modulus: bytes, exponent: bytes, selected: bytes
) -> tuple[str, bytes]:
    """Return replay text from an explicit modulus, exponent and table row."""
    if not 0 <= index < 16:
        raise ValueError("table index must be in 0..15")
    if len(modulus) != 8 or len(exponent) != 8:
        raise ValueError("modulus and exponent must be exactly 8 bytes")
    if exponent != b"\0" * 7 + b"\x11":
        raise RuntimeError(f"unexpected public exponent: {exponent.hex()}")
    if len(selected) != 8:
        raise ValueError("selected table entry must be exactly 8 bytes")

    session = modulus[::-1]
    exponent_wire = exponent[::-1]
    selected_wire = selected[::-1]
    lines = [
        "# Fresh U3 terrestrial session prefix; original driver keygen, no USB access.",
        f"# subcommand2={session.hex()} modulus={modulus.hex()} "
        f"table_index={index} table_wire={selected_wire.hex()}",
        "# delay_ms direction request wValue wIndex wLength data-or-dash",
        "0.000 in 0x25 0x095a 0xf001 1 -",
        "4.000 in 0x25 0x095a 0xf001 1 -",
    ]
    _emit_write(lines, 6.0, 0x3F5A, b"\x02")
    for offset, byte in enumerate(session):
        _emit_write(lines, 4.0, (0xC0 + offset) << 8 | 0x5A, bytes((byte,)))
    _emit_write(lines, 4.0, 0x3F5A, b"\x03")
    for offset, byte in enumerate(exponent_wire):
        _emit_write(lines, 4.0, (0xC0 + offset) << 8 | 0x5A, bytes((byte,)))
    _emit_write(lines, 4.0, 0x3F5A, b"\x04")
    for offset, byte in enumerate(selected_wire):
        _emit_write(lines, 4.0, (0xC0 + offset) << 8 | 0x5A, bytes((byte,)))
    _emit_write(lines, 4.0, 0x365A, b"\0")
    _emit_write(lines, 4.0, 0x3F5A, bytes((index << 3,)))
    _emit_write(lines, 4.0, 0x01F0, b"\x5a")
    return "\n".join(lines) + "\n", session


__all__ = ["build_sequence_from_values"]
