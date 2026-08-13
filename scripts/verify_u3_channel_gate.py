#!/usr/bin/env python3
"""Verify that non-ch21 U3 content is gated by output PAT, not raw hash."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from inspect_ts_ca import mpeg2_crc32
from transform_u3_p10_stream import GRAPH_MATERIALS


def xor16(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def raw_from_clear(clear: bytes, key: bytes, mask: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    raw = bytearray(188)
    raw[:4] = clear[:4]
    for offset in range(4, 164, 16):
        raw[offset:offset + 16] = xor16(
            encryptor.update(clear[offset:offset + 16]), mask
        )
    second_cipher = xor16(encryptor.update(clear[164:180]), mask)
    raw[164:172] = second_cipher[:8]
    first_output = second_cipher[8:] + clear[180:188]
    raw[172:188] = xor16(encryptor.update(first_output), mask)
    encryptor.finalize()
    return bytes(raw)


def pat_packet(program: int, pmt_pid: int, continuity: int) -> bytes:
    section = bytearray.fromhex("00b00d0001c10000")
    section += program.to_bytes(2, "big")
    section += (0xE000 | pmt_pid).to_bytes(2, "big")
    section += mpeg2_crc32(section).to_bytes(4, "big")
    if mpeg2_crc32(section) != 0:
        raise AssertionError("synthetic PAT CRC construction failed")
    payload = b"\0" + section
    packet = bytearray(b"\x47\x40\0" + bytes((0x10 | continuity,)))
    packet += payload + b"\xff" * (184 - len(payload))
    return bytes(packet)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    checker = root / "scripts" / "check_u3_exact_good2_capture.py"
    graph_row = 0
    key, mask = GRAPH_MATERIALS[graph_row]
    clear = b"".join(pat_packet(42, 0x0100, index & 0x0F) for index in range(32))
    raw = b"".join(
        raw_from_clear(clear[offset:offset + 188], key, mask)
        for offset in range(0, len(clear), 188)
    )

    with tempfile.TemporaryDirectory(prefix="u3-channel-gate-") as temporary:
        directory = Path(temporary)
        capture = directory / "different-multiplex.raw"
        rejected = directory / "rejected.ts"
        accepted = directory / "accepted.ts"
        capture.write_bytes(raw)
        environment = dict(os.environ, PYTHONPATH=str(root / "scripts"))

        base = [sys.executable, str(checker), str(capture)]
        result = subprocess.run(
            base + ["--standard-out", str(rejected)],
            env=environment, text=True, capture_output=True,
        )
        if result.returncode != 2 or rejected.exists():
            raise SystemExit(
                "untrusted non-ch21 fingerprint was not rejected:\n"
                + result.stdout + result.stderr
            )

        result = subprocess.run(
            base + ["--standard-out", str(accepted), "--trusted-exact-session"],
            env=environment, text=True, capture_output=True,
        )
        if result.returncode != 0 or accepted.read_bytes() != clear:
            raise SystemExit(
                "trusted different-multiplex PAT gate failed:\n"
                + result.stdout + result.stderr
            )
        if "pat_programs=42" not in result.stdout:
            raise SystemExit("trusted output did not report synthetic PAT program 42")
        if f"graph_row={graph_row}" not in result.stdout:
            raise SystemExit("trusted output did not auto-detect graph row 0")

    print(
        "U3 channel gate passes: foreign raw fingerprint rejected by default; "
        "trusted exact session auto-detected row 0 and accepted only with CRC-valid PAT"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
