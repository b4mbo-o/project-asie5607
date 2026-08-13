#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 bamboo
"""Common MPEG-TS output stages for the HDUC and U3 recpt1 clients."""

from __future__ import annotations

import os
import signal
import shutil
import subprocess
import threading
from pathlib import Path
from typing import BinaryIO, Iterable


PACKET_SIZE = 188
NULL_PID = 0x1FFF
COMMON_SI_PIDS = {
    0x0000, 0x0001,  # PAT, CAT
    0x0010, 0x0011, 0x0012, 0x0013, 0x0014,
    0x001D, 0x001E, 0x001F, 0x0023, 0x0024, 0x0029,
}


def packet_pid(packet: bytes) -> int:
    if len(packet) != PACKET_SIZE or packet[0] != 0x47:
        raise ValueError("output stage received a non-TS packet")
    return ((packet[1] & 0x1F) << 8) | packet[2]


def parse_service_ids(value: str | None) -> tuple[int, ...]:
    if value is None or value.strip().lower() == "all":
        return ()
    result: list[int] = []
    for field in value.split(","):
        field = field.strip()
        if not field:
            raise ValueError("--sid must be a comma-separated list of service IDs")
        try:
            sid = int(field, 16) if field.lower().startswith("0x") else int(field, 10)
        except ValueError as error:
            raise ValueError(f"invalid service ID: {field}") from error
        if not 1 <= sid <= 0xFFFF:
            raise ValueError(f"service ID is outside 1..65535: {field}")
        if sid not in result:
            result.append(sid)
    return tuple(result)


def mpeg_crc32(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def payload(packet: bytes) -> tuple[bool, bytes] | None:
    adaptation = (packet[3] >> 4) & 0x03
    if adaptation not in (1, 3):
        return None
    offset = 4
    if adaptation == 3:
        offset = 5 + packet[4]
    if offset >= PACKET_SIZE:
        return None
    return bool(packet[1] & 0x40), packet[offset:]


class SectionAssembler:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def _extract(self) -> list[bytes]:
        sections: list[bytes] = []
        while len(self.buffer) >= 3:
            if self.buffer[0] == 0xFF:
                self.buffer.clear()
                break
            length = 3 + (((self.buffer[1] & 0x0F) << 8) | self.buffer[2])
            if length < 7 or length > 4096:
                self.buffer.clear()
                break
            if len(self.buffer) < length:
                break
            sections.append(bytes(self.buffer[:length]))
            del self.buffer[:length]
        return sections

    def feed(self, packet: bytes) -> list[bytes]:
        body = payload(packet)
        if body is None:
            return []
        start, data = body
        sections: list[bytes] = []
        if start:
            if not data:
                return []
            pointer = data[0]
            if pointer + 1 > len(data):
                self.buffer.clear()
                return []
            if pointer and self.buffer:
                self.buffer.extend(data[1:1 + pointer])
                sections.extend(self._extract())
            self.buffer.clear()
            data = data[1 + pointer:]
        self.buffer.extend(data)
        sections.extend(self._extract())
        return sections


def valid_section(section: bytes, table_id: int) -> bool:
    return (
        len(section) >= 12
        and section[0] == table_id
        and 3 + (((section[1] & 0x0F) << 8) | section[2]) == len(section)
        and mpeg_crc32(section) == 0
    )


def pat_programs(section: bytes) -> tuple[int, int, dict[int, int]]:
    if not valid_section(section, 0x00):
        raise ValueError("invalid PAT section")
    programs: dict[int, int] = {}
    for offset in range(8, len(section) - 4, 4):
        program = int.from_bytes(section[offset:offset + 2], "big")
        pid = ((section[offset + 2] & 0x1F) << 8) | section[offset + 3]
        programs[program] = pid
    return int.from_bytes(section[3:5], "big"), section[5], programs


def descriptor_ca_pids(data: bytes) -> set[int]:
    result: set[int] = set()
    offset = 0
    while offset + 2 <= len(data):
        tag, length = data[offset], data[offset + 1]
        descriptor = data[offset + 2:offset + 2 + length]
        if len(descriptor) != length:
            break
        if tag == 0x09 and length >= 4:
            result.add(((descriptor[2] & 0x1F) << 8) | descriptor[3])
        offset += 2 + length
    return result


def pmt_pids(section: bytes, service_id: int) -> set[int]:
    if not valid_section(section, 0x02):
        raise ValueError("invalid PMT section")
    if int.from_bytes(section[3:5], "big") != service_id:
        raise ValueError("PMT belongs to another service")
    result = {((section[8] & 0x1F) << 8) | section[9]}
    info_length = ((section[10] & 0x0F) << 8) | section[11]
    offset = 12
    result.update(descriptor_ca_pids(section[offset:offset + info_length]))
    offset += info_length
    limit = len(section) - 4
    while offset + 5 <= limit:
        elementary_pid = ((section[offset + 1] & 0x1F) << 8) | section[offset + 2]
        es_length = ((section[offset + 3] & 0x0F) << 8) | section[offset + 4]
        result.add(elementary_pid)
        result.update(descriptor_ca_pids(section[offset + 5:offset + 5 + es_length]))
        offset += 5 + es_length
    return result


def make_pat_packet(original: bytes, transport_id: int, flags: int,
                    programs: Iterable[tuple[int, int]]) -> bytes:
    entries = bytearray()
    for program, pid in programs:
        entries += program.to_bytes(2, "big")
        entries += bytes((0xE0 | ((pid >> 8) & 0x1F), pid & 0xFF))
    section_length = 5 + len(entries) + 4
    section = bytearray((0x00, 0xB0 | ((section_length >> 8) & 0x0F), section_length & 0xFF))
    section += transport_id.to_bytes(2, "big")
    section += bytes((flags, 0x00, 0x00))
    section += entries
    section += mpeg_crc32(section).to_bytes(4, "big")
    if len(section) + 1 > 184:
        raise ValueError("selected PAT does not fit one TS packet")
    packet = bytearray(b"\x47\x40\x00\x10")
    packet[3] |= original[3] & 0x0F
    packet += b"\x00" + section
    packet += b"\xFF" * (PACKET_SIZE - len(packet))
    return bytes(packet)


class TSServiceFilter:
    """Select one or more services and optionally discard null packets."""

    def __init__(self, service_ids: tuple[int, ...] = (), strip: bool = False) -> None:
        self.service_ids = service_ids
        self.strip = strip
        self.pat = SectionAssembler()
        self.cat = SectionAssembler()
        self.pmt_assemblers: dict[int, SectionAssembler] = {}
        self.pmt_by_service: dict[int, int] = {}
        self.parsed_services: set[int] = set()
        self.extra_pids: set[int] = set()
        self.transport_id: int | None = None
        self.pat_flags = 0xC1

    @property
    def ready(self) -> bool:
        return not self.service_ids or all(sid in self.parsed_services for sid in self.service_ids)

    def _learn(self, packet: bytes, pid: int) -> None:
        if pid == 0:
            for section in self.pat.feed(packet):
                if not valid_section(section, 0x00):
                    continue
                transport_id, flags, programs = pat_programs(section)
                selected = {sid: programs[sid] for sid in self.service_ids if sid in programs}
                self.transport_id, self.pat_flags = transport_id, flags
                for sid, pmt_pid in selected.items():
                    self.pmt_by_service[sid] = pmt_pid
                    self.pmt_assemblers.setdefault(pmt_pid, SectionAssembler())
        elif pid == 1:
            for section in self.cat.feed(packet):
                if valid_section(section, 0x01):
                    self.extra_pids.update(descriptor_ca_pids(section[8:-4]))
        elif pid in self.pmt_assemblers:
            for section in self.pmt_assemblers[pid].feed(packet):
                if not valid_section(section, 0x02):
                    continue
                sid = int.from_bytes(section[3:5], "big")
                if sid in self.service_ids:
                    self.extra_pids.update(pmt_pids(section, sid))
                    self.parsed_services.add(sid)

    def filter(self, packet: bytes) -> bytes | None:
        pid = packet_pid(packet)
        if self.service_ids:
            self._learn(packet, pid)
            allowed = COMMON_SI_PIDS | set(self.pmt_by_service.values()) | self.extra_pids
            if pid not in allowed:
                return None
            if pid == 0 and self.transport_id is not None:
                entries: list[tuple[int, int]] = []
                for sid in self.service_ids:
                    if sid in self.pmt_by_service:
                        entries.append((sid, self.pmt_by_service[sid]))
                if entries:
                    return make_pat_packet(packet, self.transport_id, self.pat_flags, entries)
        if self.strip and pid == NULL_PID:
            return None
        return packet


def find_b25(binary: str | None = None) -> str:
    candidate = binary or os.environ.get("RECPT1_B25_BIN") or os.environ.get("ARIB25_BIN") or "b25"
    resolved = shutil.which(candidate)
    if resolved is None:
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
        raise FileNotFoundError(
            f"B25 executable not found: {candidate}; use --b25-bin or RECPT1_B25_BIN"
        )
    return resolved


class OutputPipeline:
    """Write TS through optional external B25 and service/null filtering."""

    def __init__(self, target: BinaryIO, *, service_ids: tuple[int, ...] = (),
                 strip: bool = False, b25: bool = False,
                 b25_binary: str | None = None) -> None:
        self.target = target
        self.filter = TSServiceFilter(service_ids, strip)
        self.process: subprocess.Popen[bytes] | None = None
        self.thread: threading.Thread | None = None
        self.reader_error: BaseException | None = None
        self.output_packets = 0
        if b25:
            executable = find_b25(b25_binary)
            command = [executable, "-v", "0", "-p", "0", "-s", "0", "/dev/stdin", "/dev/stdout"]
            self.process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                start_new_session=True,
            )
            self.thread = threading.Thread(target=self._drain_b25, name="recpt1-b25", daemon=True)
            self.thread.start()

    def _filtered_write(self, packet: bytes) -> None:
        selected = self.filter.filter(packet)
        if selected is not None:
            self.target.write(selected)
            self.output_packets += 1

    def _drain_b25(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        pending = bytearray()
        try:
            while True:
                chunk = self.process.stdout.read(64 * 1024)
                if not chunk:
                    break
                pending.extend(chunk)
                while len(pending) >= PACKET_SIZE:
                    packet = bytes(pending[:PACKET_SIZE])
                    del pending[:PACKET_SIZE]
                    self._filtered_write(packet)
            if pending:
                raise RuntimeError(f"B25 emitted {len(pending)} trailing bytes")
        except BaseException as error:
            self.reader_error = error

    def write(self, packet: bytes) -> None:
        if self.process is None:
            self._filtered_write(packet)
            return
        if self.reader_error is not None:
            raise RuntimeError(f"B25 output failed: {self.reader_error}")
        assert self.process.stdin is not None
        self.process.stdin.write(packet)

    def close(self) -> None:
        if self.process is not None:
            assert self.process.stdin is not None
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                pass
            if self.thread is not None:
                self.thread.join()
            if self.process.stdout is not None:
                self.process.stdout.close()
            returncode = self.process.wait()
            if self.reader_error is not None:
                raise RuntimeError(f"B25 output failed: {self.reader_error}")
            if returncode:
                raise RuntimeError(f"B25 process exited with status {returncode}")
        self.target.flush()
        if self.filter.service_ids and not self.filter.ready:
            missing = sorted(set(self.filter.service_ids) - self.filter.parsed_services)
            raise RuntimeError("selected service ID was not found: " + ",".join(map(str, missing)))

    def abort(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        if self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.process.wait(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
        if self.thread is not None:
            self.thread.join(timeout=3)
        if self.process.stdout is not None:
            self.process.stdout.close()

    def __enter__(self) -> "OutputPipeline":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.close()
        else:
            self.abort()
        return False


__all__ = [
    "OutputPipeline", "TSServiceFilter", "find_b25", "make_pat_packet",
    "mpeg_crc32", "packet_pid", "parse_service_ids", "pat_programs", "pmt_pids",
]
