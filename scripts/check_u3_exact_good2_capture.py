#!/usr/bin/env python3
"""Resynchronise U3 raw, report its fingerprint, and validate transformed PAT.

The historical Windows ``good2`` ch21 windows have one repeatable 184-byte
encrypted PAT payload.  Matching it identifies that historical context, but
Linux sessions may legitimately select another one of the 16 graph rows.
For another multiplex, the live runner may assert that it just established the
secure startup.  The tool then scans all derived graph rows and accepts a
different raw hash only if exactly one AES/CTS output contains a CRC-valid PAT.
This tool is offline and never opens USB.
"""

import argparse
import hashlib
import io
from collections import Counter
from pathlib import Path

from inspect_ts_ca import PsiReassembler, mpeg2_crc32, parse_pat, ts_payload
from transform_u3_p10_stream import detect_graph_row, transform_packet
from u3_streaming import StreamStats, packet_stream


PACKET = 188
EXPECTED_PID0_MODAL_SHA256 = (
    "18105fbfd464fa33fa09272dac98b51da8a097e25bd272ba4e0aa20d39e51d1d"
)


def best_offset(data: bytes, sample: int = 4_000_000) -> tuple[int, int, int]:
    """Return the strongest 188-byte phase without importing PCAP tooling."""
    span = min(len(data), sample)
    best_offset_, best_hits, best_count = 0, -1, 0
    for offset in range(PACKET):
        count = (span - offset + PACKET - 1) // PACKET if offset < span else 0
        hits = sum(data[index] == 0x47 for index in range(offset, span, PACKET))
        if hits > best_hits:
            best_offset_, best_hits, best_count = offset, hits, count
    return best_offset_, best_hits, best_count


def aligned(data: bytes) -> tuple[bytes, int, int, int]:
    offset, hits, sampled = best_offset(data)
    stats = StreamStats()
    stream = b"".join(packet_stream(io.BytesIO(data[offset:]), stats))
    return stream, offset, stats.packets, sampled


def pid_payloads(stream: bytes, pid: int) -> Counter[bytes]:
    values: Counter[bytes] = Counter()
    for offset in range(0, len(stream) - PACKET + 1, PACKET):
        packet = stream[offset:offset + PACKET]
        current = ((packet[1] & 0x1F) << 8) | packet[2]
        if packet[0] == 0x47 and current == pid:
            values[packet[4:]] += 1
    return values


def valid_pat_programs(stream: bytes) -> dict[int, int]:
    """Return programs from CRC-valid PAT sections in a transformed stream."""
    psi = PsiReassembler()
    programs: dict[int, int] = {}
    for offset in range(0, len(stream) - PACKET + 1, PACKET):
        decoded = ts_payload(stream[offset:offset + PACKET])
        if decoded is None:
            continue
        pid, pusi, payload = decoded
        if pid != 0:
            continue
        for section in psi.feed(pid, pusi, payload):
            if len(section) >= 4 and mpeg2_crc32(section) == 0:
                programs.update(parse_pat(section))
    return programs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--aligned-out", type=Path)
    parser.add_argument(
        "--standard-out",
        type=Path,
        help=("write standard TS when the ch21 fingerprint matches, or when "
              "--trusted-exact-session is supplied and output PAT validates"),
    )
    parser.add_argument(
        "--trusted-exact-session",
        action="store_true",
        help=("allow a different multiplex fingerprint when the caller just "
              "established the retained exact-good2 secure session; the "
              "transformed output must still contain a CRC-valid PAT"),
    )
    args = parser.parse_args()

    source = args.capture.read_bytes()
    stream, offset, sync, sampled = aligned(source)
    observed = pid_payloads(stream, 0)
    if not observed:
        raise SystemExit("no PID 0 packet found in aligned capture")
    observed_value, observed_count = observed.most_common(1)[0]
    observed_digest = hashlib.sha256(observed_value).hexdigest()
    exact = observed_digest == EXPECTED_PID0_MODAL_SHA256

    print(f"capture={args.capture} size={len(source)} sha256={hashlib.sha256(source).hexdigest()}")
    print(
        f"alignment_offset={offset} packets={len(stream) // PACKET} "
        f"sync={sync}/{len(stream) // PACKET} sample_grid={sampled}"
    )
    print(
        f"pid0_packets={sum(observed.values())} unique={len(observed)} "
        f"modal_count={observed_count}"
    )
    print(f"pid0_modal={observed_value.hex()}")
    print(
        f"pid0_modal_sha256={observed_digest} "
        f"exact_good2_fingerprint={exact}"
    )
    if args.aligned_out:
        args.aligned_out.write_bytes(stream)
        print(f"aligned_out={args.aligned_out} size={len(stream)}")
    if args.standard_out:
        if not exact and not args.trusted_exact_session:
            print("standard_out=skipped (capture is not the exact-good2 session)")
        else:
            if args.standard_out.exists():
                raise SystemExit(
                    f"refusing to overwrite existing file: {args.standard_out}"
                )
            selection = detect_graph_row(
                stream[start:start + PACKET]
                for start in range(0, len(stream), PACKET)
            )
            if selection is None:
                raise SystemExit(
                    "no graph row produced a CRC-valid PAT; standard output skipped"
                )
            row, key, mask, _detected_programs = selection
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
            with args.standard_out.open("xb") as target:
                for start in range(0, len(stream), PACKET):
                    target.write(
                        transform_packet(
                            stream[start:start + PACKET],
                            decryptor,
                            mask,
                        )
                    )
            decryptor.finalize()
            transformed = args.standard_out.read_bytes()
            programs = valid_pat_programs(transformed)
            if not programs:
                args.standard_out.unlink()
                raise SystemExit(
                    "transformed stream has no CRC-valid PAT; removed standard output"
                )
            print(
                f"standard_out={args.standard_out} "
                f"size={args.standard_out.stat().st_size} "
                f"graph_row={row} aes_key={key.hex()} "
                f"block_xor_mask={mask.hex()} "
                f"pat_programs={','.join(map(str, sorted(programs)))}"
            )
    return 0 if exact or args.trusted_exact_session else 2


if __name__ == "__main__":
    raise SystemExit(main())
