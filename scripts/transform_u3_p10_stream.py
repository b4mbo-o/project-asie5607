#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 bamboo
"""Convert aligned U3 EP0x81 records to standard MPEG-TS.

This is the host-side Property-10 transform used by the 2009 U3 EagleDTV
viewer.  The packet payload is AES-128-ECB with ciphertext stealing for its
final 24 bytes.  The four-byte TS header is preserved.

The current Linux startup fixes Property-9 clear value
``4efc90949311f8cf474c8c11f41b6f2d``, but the device-selected graph row is
not fixed: independent sessions have selected rows 11 and 0.  The 16 derived
AES/mask pairs below cover every possible row.  By default the command scans
PID 0 for a CRC-valid PAT and selects the unique row automatically.  The DLL
itself is not needed by this fast path.

Input must already consist of aligned 188-byte EP0x81 records, normally the
output of ``extract_u3_ts.py``.  Conditional-access processing, if required,
is a separate downstream step.
"""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Iterable
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


PACKET_SIZE = 188
PROPERTY9_CLEAR = bytes.fromhex("4efc90949311f8cf474c8c11f41b6f2d")
GRAPH_ROW = 11
AES_KEY = bytes.fromhex("a83ddb06176012962ff4309548f2ef1f")
BLOCK_XOR_MASK = bytes.fromhex("60ef96ef969660ef60ef96ef9696efdb")

# Effective materials for Property-9 clear 4efc... and graph rows 0..15.
# Each pair was recovered at EagleDTV.dll!FUN_10066710 and checked against
# exact execution of the protected viewer routine.  Keep the row-11 aliases
# above for compatibility with older callers and regression vectors.
GRAPH_MATERIALS = tuple(
    (bytes.fromhex(key), bytes.fromhex(mask))
    for key, mask in (
        ("43ab34644bce4120933a32249cbda734", "cea720a72020cea7cea720a72020a734"),
        ("f6998c0389fd3e82838744e6b290034d", "fd0382038282fd03fd0382038282038c"),
        ("6e9556ae12ce99aef7c20769649cd32d", "ced3aed3aeaeced3ced3aed3aeaed356"),
        ("e4616b6ec72646eac1044cccb337b57b", "26b5eab5eaea26b526b5eab5eaeab56b"),
        ("d821d61de27d0b2a2e20aa3cbfa18687", "7d862a862a2a7d867d862a862a2a86d6"),
        ("20ec1a02fcab1b87cc4989aadfeb74af", "ab7487748787ab74ab7487748787741a"),
        ("c1df2150ee804fe4864505b519df7a26", "807ae47ae4e4807a807ae47ae4e47a21"),
        ("9683c2814aefa0b82d515c5db4e92951", "ef29b829b8b8ef29ef29b829b8b829c2"),
        ("ca51b160ac3f7a4a79aaaa1682acb1a5", "3fb14ab14a4a3fb13fb14ab14a4ab1b1"),
        ("50350f215f73361eba440ba21cb7d633", "73d61ed61e1e73d673d61ed61e1ed60f"),
        ("67d24ec233a6de291cfef223788948c0", "a64829482929a648a64829482929484e"),
        ("a83ddb06176012962ff4309548f2ef1f", "60ef96ef969660ef60ef96ef9696efdb"),
        ("74b4195f66f5799f6854d3cb7763ccff", "f5cc9fcc9f9ff5ccf5cc9fcc9f9fcc19"),
        ("676fa27a201458e4d0850af215ff6c28", "146ce46ce4e4146c146ce46ce4e46ca2"),
        ("1c213f2dd166326a9200c74f4bd296ef", "66966a966a6a669666966a966a6a963f"),
        ("bb00e457074c549b38a421148c5f9834", "4c989b989b9b4c984c989b989b9b98e4"),
    )
)


def xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def transform_packet(packet: bytes, decryptor, mask: bytes = BLOCK_XOR_MASK) -> bytes:
    """Apply EagleDTV's U3 AES/CTS transform to one 188-byte record."""
    if len(packet) != PACKET_SIZE:
        raise ValueError(f"expected {PACKET_SIZE} bytes, got {len(packet)}")
    if len(mask) != 16:
        raise ValueError(f"expected a 16-byte XOR mask, got {len(mask)}")

    result = bytearray(PACKET_SIZE)
    result[:4] = packet[:4]

    # Ten complete payload blocks cover offsets 4..163.
    complete = b"".join(
        xor_bytes(packet[offset:offset + 16], mask)
        for offset in range(4, 164, 16)
    )
    result[4:164] = decryptor.update(complete)

    # The remaining 24 bytes use the same two-call ciphertext-stealing layout
    # as EagleDTV's FUN_10066710.  The second result overwrites the first
    # result's leading eight bytes.
    first_output = decryptor.update(xor_bytes(packet[172:188], mask))
    second_input = packet[164:172] + first_output[:8]
    result[164:180] = decryptor.update(xor_bytes(second_input, mask))
    result[180:188] = first_output[8:]
    return bytes(result)


def mpeg2_crc32(data: bytes) -> int:
    """Return the MPEG-2 PSI CRC remainder."""
    crc = 0xFFFFFFFF
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = (
                ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
                if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
            )
    return crc


def pat_programs_from_packet(packet: bytes) -> dict[int, int]:
    """Parse a complete, single-packet CRC-valid PAT or return an empty map."""
    if len(packet) != PACKET_SIZE or packet[0] != 0x47:
        return {}
    if ((packet[1] & 0x1F) << 8 | packet[2]) != 0 or not packet[1] & 0x40:
        return {}
    adaptation = (packet[3] >> 4) & 3
    if adaptation in (0, 2):
        return {}
    payload = 4
    if adaptation == 3:
        payload += 1 + packet[4]
    if payload >= PACKET_SIZE:
        return {}
    pointer = packet[payload]
    section_start = payload + 1 + pointer
    if section_start + 3 > PACKET_SIZE or packet[section_start] != 0:
        return {}
    section_length = 3 + (
        ((packet[section_start + 1] & 0x0F) << 8)
        | packet[section_start + 2]
    )
    section = packet[section_start:section_start + section_length]
    if len(section) != section_length or section_length < 12:
        return {}
    if mpeg2_crc32(section) != 0:
        return {}
    programs: dict[int, int] = {}
    for offset in range(8, len(section) - 4, 4):
        if offset + 4 > len(section) - 4:
            break
        program = int.from_bytes(section[offset:offset + 2], "big")
        pid = ((section[offset + 2] & 0x1F) << 8) | section[offset + 3]
        if program:
            programs[program] = pid
    return programs


def detect_graph_row(
    packets: Iterable[bytes],
) -> tuple[int, bytes, bytes, dict[int, int]] | None:
    """Select the unique graph row which turns raw PID 0 into a valid PAT."""
    pid0 = [
        packet for packet in packets
        if len(packet) == PACKET_SIZE
        and packet[0] == 0x47
        and ((packet[1] & 0x1F) << 8 | packet[2]) == 0
    ]
    if not pid0:
        return None
    matches: list[tuple[int, bytes, bytes, dict[int, int]]] = []
    for row, (key, mask) in enumerate(GRAPH_MATERIALS):
        decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
        programs: dict[int, int] = {}
        for packet in pid0:
            programs.update(
                pat_programs_from_packet(transform_packet(packet, decryptor, mask))
            )
            if programs:
                break
        decryptor.finalize()
        if programs:
            matches.append((row, key, mask, programs))
    if len(matches) > 1:
        raise ValueError(
            "multiple graph rows produced CRC-valid PATs: "
            + ",".join(str(item[0]) for item in matches)
        )
    return matches[0] if matches else None


def transform_stream(source, target, key: bytes, mask: bytes) -> tuple[int, str, int]:
    if len(key) != 16:
        raise ValueError(f"expected a 16-byte AES key, got {len(key)}")
    if len(mask) != 16:
        raise ValueError(f"expected a 16-byte XOR mask, got {len(mask)}")
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    digest = hashlib.sha256()
    packets = 0
    while True:
        packet = source.read(PACKET_SIZE)
        if not packet:
            trailing = 0
            break
        if len(packet) != PACKET_SIZE:
            trailing = len(packet)
            break
        if packet[0] not in (0x47, 0xC7):
            raise ValueError(
                f"packet {packets} has sync 0x{packet[0]:02x}; "
                "align it with extract_u3_ts.py first"
            )
        transformed = transform_packet(packet, decryptor, mask)
        target.write(transformed)
        digest.update(transformed)
        packets += 1
    decryptor.finalize()
    return packets, digest.hexdigest(), trailing


def hex16(value: str) -> bytes:
    decoded = bytes.fromhex(value)
    if len(decoded) != 16:
        raise argparse.ArgumentTypeError("value must be exactly 32 hex digits")
    return decoded


def graph_row(value: str) -> int | None:
    if value.lower() == "auto":
        return None
    try:
        row = int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("graph row must be auto or 0..15") from error
    if not 0 <= row < len(GRAPH_MATERIALS):
        raise argparse.ArgumentTypeError("graph row must be auto or 0..15")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="aligned 188-byte EP0x81 records")
    parser.add_argument("output", type=Path, help="new standard MPEG-TS output")
    parser.add_argument(
        "--graph-row", type=graph_row, default=None, metavar="auto|0..15",
        help="device graph row (default: detect from a CRC-valid PAT)",
    )
    parser.add_argument("--aes-key", type=hex16)
    parser.add_argument("--block-xor-mask", type=hex16)
    parser.add_argument(
        "--truncate-partial",
        action="store_true",
        help="discard a final incomplete record instead of failing",
    )
    args = parser.parse_args()
    if bool(args.aes_key) != bool(args.block_xor_mask):
        parser.error("--aes-key and --block-xor-mask must be supplied together")
    if args.aes_key and args.graph_row is not None:
        parser.error("custom AES material cannot be combined with --graph-row")
    if args.output.exists():
        parser.error(f"refusing to overwrite existing file: {args.output}")

    selected_row = args.graph_row
    key = args.aes_key
    mask = args.block_xor_mask
    if key is None:
        if selected_row is None:
            with args.input.open("rb") as source:
                probe = [source.read(PACKET_SIZE) for _ in range(16_384)]
            selection = detect_graph_row(probe)
            if selection is None:
                parser.error("could not detect a graph row from a CRC-valid PAT")
            selected_row, key, mask, programs = selection
            print(
                f"detected_graph_row={selected_row} "
                f"pat_programs={','.join(map(str, sorted(programs)))}"
            )
        else:
            key, mask = GRAPH_MATERIALS[selected_row]
    assert key is not None and mask is not None

    try:
        with args.input.open("rb") as source, args.output.open("xb") as target:
            packets, digest, trailing = transform_stream(
                source, target, key, mask
            )
        if trailing and not args.truncate_partial:
            args.output.unlink()
            parser.error(
                f"input has {trailing} trailing byte(s); use --truncate-partial"
            )
    except BaseException:
        if args.output.exists() and args.output.stat().st_size == 0:
            args.output.unlink()
        raise

    print(f"packets={packets}")
    if trailing:
        print(f"trailing_bytes_discarded={trailing}")
    row_label = "custom" if selected_row is None else str(selected_row)
    print(f"property9_clear={PROPERTY9_CLEAR.hex()} graph_row={row_label}")
    print(f"aes_key={key.hex()}")
    print(f"block_xor_mask={mask.hex()}")
    print(f"output_sha256={digest} size={packets * PACKET_SIZE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
