#!/usr/bin/env python3
"""Offline regression for recpt1-u3 framing and incremental AES/CTS."""

from __future__ import annotations

import importlib.util
import io
import os
import socket
import subprocess
import tempfile
import threading
from importlib.machinery import SourceFileLoader
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from u3_streaming import (
    AES_KEY, BLOCK_XOR_MASK, StreamStats, decryptor, packet_stream,
    transform_packet,
)
from transform_u3_p10_stream import mpeg2_crc32


def xor16(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def raw_from_clear(clear: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(AES_KEY), modes.ECB()).encryptor()
    raw = bytearray(188)
    raw[:4] = clear[:4]
    for offset in range(4, 164, 16):
        raw[offset:offset + 16] = xor16(
            encryptor.update(clear[offset:offset + 16]), BLOCK_XOR_MASK
        )
    second_cipher = xor16(
        encryptor.update(clear[164:180]), BLOCK_XOR_MASK
    )
    raw[164:172] = second_cipher[:8]
    first_output = second_cipher[8:] + clear[180:188]
    raw[172:188] = xor16(encryptor.update(first_output), BLOCK_XOR_MASK)
    encryptor.finalize()
    return bytes(raw)


def clear_packet(counter: int) -> bytes:
    packet = bytearray(188)
    packet[:4] = bytes((0x47, 0x40, counter & 0x1F, 0x10 | (counter & 0x0F)))
    if counter == 0:
        section = bytearray.fromhex("00b00d0001c10000")
        section += (42).to_bytes(2, "big")
        section += (0xE100).to_bytes(2, "big")
        section += mpeg2_crc32(section).to_bytes(4, "big")
        payload = b"\0" + section
        packet[4:] = payload + b"\xff" * (184 - len(payload))
        return bytes(packet)
    packet[4:] = bytes((offset + counter) & 0xFF for offset in range(184))
    return bytes(packet)


def load_client():
    path = Path(__file__).with_name("recpt1-u3")
    loader = SourceFileLoader("recpt1_u3_verify", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def main() -> int:
    clear = [clear_packet(index) for index in range(12)]
    raw = [raw_from_clear(packet) for packet in clear]
    sideband = b"sideband-event-record-33-bytes!!!"
    source = io.BytesIO(b"".join(raw[:8]) + sideband + b"".join(raw[8:]))
    stats = StreamStats()
    cipher = decryptor()
    actual = [
        transform_packet(packet, cipher, BLOCK_XOR_MASK)
        for packet in packet_stream(source, stats, chunk_size=97)
    ]
    cipher.finalize()
    if actual != clear:
        raise SystemExit("incremental U3 AES/CTS round-trip mismatch")
    if stats.gaps != [(8 * 188, len(sideband))] or stats.trailing:
        raise SystemExit(
            f"wrong sideband recovery: gaps={stats.gaps} trailing={stats.trailing}"
        )

    client = load_client()
    expected_times = {
        "-": 0, "15": 15, "01:02": 62, "1:02:03": 3723, "1H2M3S": 3723,
    }
    for text, expected in expected_times.items():
        actual_time = client.parse_record_time(text)
        if actual_time != expected:
            raise SystemExit(f"record time {text}: {actual_time} != {expected}")
    for invalid in ("0", "", "1:60", "abc", "-5"):
        try:
            client.parse_record_time(invalid)
        except ValueError:
            continue
        raise SystemExit(f"invalid record time was accepted: {invalid!r}")

    with tempfile.TemporaryDirectory(prefix="u3-backend-verify-") as temporary:
        directory = Path(temporary)
        socket_path = directory / "u3.sock"
        output_path = directory / "standard.ts"
        ready = threading.Event()
        failure: list[BaseException] = []

        def fake_daemon() -> None:
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                listener.bind(str(socket_path))
                listener.listen(1)
                ready.set()
                connection, _ = listener.accept()
                with connection:
                    command = bytearray()
                    while not command.endswith(b"\n"):
                        command += connection.recv(128)
                    if command != b"RECORD 21 1\n":
                        raise RuntimeError(f"wrong client command: {bytes(command)!r}")
                    connection.sendall(
                        b"OK\n" + b"".join(raw[:8])
                        + sideband + b"".join(raw[8:])
                    )
            except BaseException as error:
                failure.append(error)
            finally:
                listener.close()

        thread = threading.Thread(target=fake_daemon, daemon=True)
        thread.start()
        if not ready.wait(2):
            raise SystemExit("fake U3 daemon did not start")
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).parent))
        result = subprocess.run(
            [str(Path(__file__).with_name("recpt1-u3")), "--socket", str(socket_path),
             "21", "1", str(output_path)],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
        )
        thread.join(timeout=2)
        if failure:
            raise SystemExit(f"fake U3 daemon failed: {failure[0]}")
        if result.returncode != 0:
            raise SystemExit(
                "recpt1-u3 integration failed: "
                + result.stderr.decode("utf-8", "replace")
            )
        if output_path.read_bytes() != b"".join(clear):
            raise SystemExit("recpt1-u3 socket output mismatch")

    print(
        f"U3 streaming backend passes: packets={stats.packets} "
        f"gap={stats.gaps[0][1]} bytes AES/CTS=exact socket-client=exact"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
