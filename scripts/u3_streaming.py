"""Incremental framing and AES/CTS conversion for live U3 EP0x81 data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import BinaryIO, Iterator

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from transform_u3_p10_stream import (
    AES_KEY, BLOCK_XOR_MASK, GRAPH_MATERIALS, detect_graph_row, transform_packet,
)


PACKET = 188


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


def packet_stream(
    source: BinaryIO, stats: StreamStats, chunk_size: int = 1024 * 1024
) -> Iterator[bytes]:
    """Yield aligned records and recover after occasional EP81 sideband bytes."""
    buffered = bytearray()
    absolute = 0
    eof = False
    locked = False
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
                if not locked:
                    available = len(buffered) // PACKET
                    if not eof and available < 8:
                        break
                    checks = min(8, available)
                    locked = checks > 0 and all(
                        header_ok(buffered, index * PACKET)
                        for index in range(checks)
                    )
                if locked:
                    packet = bytes(buffered[:PACKET])
                    del buffered[:PACKET]
                    absolute += PACKET
                    stats.packets += 1
                    progressed = True
                    yield packet
                    continue

            locked = False
            candidate = 1
            found = None
            need_more = False
            while candidate < len(buffered):
                candidate = buffered.find(0x47, candidate)
                if candidate < 0:
                    break
                available = (len(buffered) - candidate) // PACKET
                # Encrypted payloads can repeat at 188-byte intervals and
                # occasionally imitate several plausible TS headers.  Eight
                # consecutive headers rejects the five-record false phase
                # observed at the start of a real U3 Linux capture.
                if not eof and available < 8:
                    need_more = True
                    break
                checks = min(8, available)
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
        if not progressed and len(buffered) > 8 * 1024 * 1024:
            raise ValueError("could not find a U3 EP81 record phase in 8 MiB")


def decryptor(row: int = 11):
    if not 0 <= row < len(GRAPH_MATERIALS):
        raise ValueError("graph row must be in 0..15")
    key, _mask = GRAPH_MATERIALS[row]
    return Cipher(algorithms.AES(key), modes.ECB()).decryptor()


__all__ = [
    "AES_KEY", "BLOCK_XOR_MASK", "GRAPH_MATERIALS", "PACKET", "StreamStats",
    "decryptor", "detect_graph_row", "packet_stream", "transform_packet",
]
