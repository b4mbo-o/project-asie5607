#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 bamboo
"""Stream raw HDUC EP81 into standard TS using the verified x64 mode-6 path.

Unlike the offline analysis harness, this tool does not load the recording or
build the transformed result in memory.  It also removes occasional non-TS
sideband records by requiring three consecutive plausible 188-byte headers
before accepting a new phase.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PACKET = 188


def xor16(left: bytes, right: bytes) -> bytes:
    if len(left) != 16 or len(right) != 16:
        raise ValueError("xor16 requires two 16-byte values")
    return bytes(a ^ b for a, b in zip(left, right))


DEFAULT_MATERIAL = (
    Path(__file__).resolve().parents[1] / "data" / "hduc-x64-mode6-material.json"
)


def load_material(path: Path) -> tuple[bytes, bytes, bytes]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("format") != "hduc-mode6-material-v1":
        raise ValueError("unsupported mode-6 material format")
    rotated = bytes.fromhex(document["rotated_state"])
    key = bytes.fromhex(document["aes_key"])
    mask = bytes.fromhex(document["block_xor_mask"])
    if any(len(value) != 16 for value in (rotated, key, mask)):
        raise ValueError("mode-6 material values must each be 16 bytes")
    return rotated, key, mask


@dataclass
class StreamStats:
    packets: int = 0
    gaps: list[tuple[int, int]] = field(default_factory=list)
    trailing: int = 0


def header_ok(data: bytearray, offset: int) -> bool:
    return (
        offset + 4 <= len(data)
        and data[offset] == 0x47
        and ((data[offset + 3] >> 4) & 3) != 0
    )


def packet_stream(source: BinaryIO, stats: StreamStats, chunk_size: int = 1024 * 1024):
    """Yield re-synchronized packets while retaining only a small input buffer."""
    buffered = bytearray()
    absolute = 0
    eof = False
    reader = getattr(source, "read1", source.read)
    while True:
        if not eof:
            chunk = reader(chunk_size)
            if chunk:
                buffered += chunk
            else:
                eof = True

        progressed = False
        while len(buffered) >= PACKET:
            if header_ok(buffered, 0):
                packet = bytes(buffered[:PACKET])
                del buffered[:PACKET]
                absolute += PACKET
                stats.packets += 1
                progressed = True
                yield packet
                continue

            candidate = 1
            found = None
            need_more = False
            while candidate < len(buffered):
                candidate = buffered.find(0x47, candidate)
                if candidate < 0:
                    break
                available = (len(buffered) - candidate) // PACKET
                if not eof and available < 3:
                    need_more = True
                    break
                checks = min(3, available)
                if checks and all(
                    header_ok(buffered, candidate + index * PACKET)
                    for index in range(checks)
                ):
                    found = candidate
                    break
                candidate += 1

            if found is not None:
                stats.gaps.append((absolute, found))
                del buffered[:found]
                absolute += found
                progressed = True
                continue
            if need_more and not eof:
                break
            if eof:
                stats.trailing = len(buffered)
                buffered.clear()
            break

        if eof:
            if buffered:
                stats.trailing = len(buffered)
            break
        if not progressed and len(buffered) > 8 * chunk_size:
            raise ValueError("could not find a TS phase in 8 MiB of EP81 input")


def transform_packet(packet: bytes, decryptor, mask: bytes) -> bytes:
    result = bytearray(PACKET)
    result[:4] = packet[:4]
    complete = b"".join(
        xor16(packet[offset:offset + 16], mask)
        for offset in range(4, 164, 16)
    )
    result[4:164] = decryptor.update(complete)
    first_output = decryptor.update(xor16(packet[172:188], mask))
    second_input = packet[164:172] + first_output[:8]
    result[164:180] = decryptor.update(xor16(second_input, mask))
    result[180:188] = first_output[8:]
    return bytes(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="raw EP81 capture, or - for stdin")
    parser.add_argument("output", help="new standard TS output, or - for stdout")
    parser.add_argument("--material", type=Path, default=DEFAULT_MATERIAL,
                        help=f"mode-6 material JSON (default: {DEFAULT_MATERIAL})")
    parser.add_argument("--truncate-partial", action="store_true",
                        help="discard the final incomplete packet")
    parser.add_argument("--show-key-material", action="store_true",
                        help="print locally-derived AES state/key/mask (sensitive)")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace an existing output file")
    args = parser.parse_args()

    output_path = None if args.output == "-" else Path(args.output)
    if output_path is not None and output_path.exists() and not args.overwrite:
        raise SystemExit(f"refusing to overwrite existing file: {output_path}")
    try:
        rotated, key, mask = load_material(args.material)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid mode-6 material: {exc}") from exc
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    stats = StreamStats()
    digest = hashlib.sha256()
    source_context = (
        contextlib.nullcontext(sys.stdin.buffer)
        if args.input == "-" else Path(args.input).open("rb")
    )
    target_context = (
        contextlib.nullcontext(sys.stdout.buffer)
        if output_path is None
        else output_path.open("wb" if args.overwrite else "xb")
    )
    try:
        with source_context as source, target_context as target:
            for packet in packet_stream(source, stats):
                transformed = transform_packet(packet, decryptor, mask)
                target.write(transformed)
                digest.update(transformed)
            target.flush()
            decryptor.finalize()
        if stats.trailing and not args.truncate_partial:
            if output_path is not None:
                output_path.unlink()
            raise SystemExit(
                f"input has {stats.trailing} trailing byte(s); use --truncate-partial"
            )
    except BaseException:
        if output_path is not None and output_path.exists() and output_path.stat().st_size == 0:
            output_path.unlink()
        raise

    log = sys.stderr if output_path is None else sys.stdout
    print(f"packets={stats.packets}", file=log)
    print(f"resync_gaps={len(stats.gaps)} "
          f"resync_skipped_bytes={sum(length for _, length in stats.gaps)}", file=log)
    for offset, length in stats.gaps[:8]:
        print(f"resync_gap offset={offset} length={length}", file=log)
    if stats.trailing:
        print(f"trailing_bytes_discarded={stats.trailing}", file=log)
    if args.show_key_material:
        print(f"rotated_state={rotated.hex()}", file=log)
        print(f"aes_key={key.hex()}", file=log)
        print(f"block_xor_mask={mask.hex()}", file=log)
    print(f"output_sha256={digest.hexdigest()} size={stats.packets * PACKET}", file=log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
