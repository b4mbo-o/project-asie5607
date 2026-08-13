#!/usr/bin/env python3
"""Inspect PAT/CAT/PMT and conditional-access descriptors in an MPEG-TS file.

This is intentionally small and dependency-free.  It consumes an already
188-byte-aligned TS (for example one produced by extract_u3_ts.py), reassembles
PSI sections, then prints the CA_system_id / ECM PID advertised by CAT and PMT.
It does not decrypt anything and never contacts a B-CAS card.
"""
import argparse
from collections import defaultdict


STREAM_TYPES = {
    0x01: "MPEG-1 video", 0x02: "MPEG-2 video", 0x03: "MPEG-1 audio",
    0x04: "MPEG-2 audio", 0x0F: "AAC", 0x1B: "H.264/AVC", 0x24: "HEVC",
}


def mpeg2_crc32(data):
    """Return the MPEG-2 PSI CRC-32 remainder (zero means a valid section)."""
    crc = 0xFFFFFFFF
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 \
                else (crc << 1) & 0xFFFFFFFF
    return crc


def ca_descriptors(data):
    """Return (CA_system_id, ECM/EMM PID, private-data) tuples from descriptors."""
    result = []
    i = 0
    while i + 2 <= len(data):
        tag, size = data[i], data[i + 1]
        body = data[i + 2:i + 2 + size]
        if len(body) != size:
            break
        if tag == 0x09 and size >= 4:
            system_id = (body[0] << 8) | body[1]
            pid = ((body[2] & 0x1F) << 8) | body[3]
            result.append((system_id, pid, body[4:]))
        i += 2 + size
    return result


class PsiReassembler:
    def __init__(self):
        self.buffers = defaultdict(bytearray)

    @staticmethod
    def _drain(buf):
        sections = []
        while len(buf) >= 3:
            if buf[0] == 0xFF:  # stuffing after the final section in a packet
                buf.clear()
                break
            total = 3 + (((buf[1] & 0x0F) << 8) | buf[2])
            if total < 3 or total > 4096:
                buf.clear()
                break
            if len(buf) < total:
                break
            sections.append(bytes(buf[:total]))
            del buf[:total]
        return sections

    def feed(self, pid, payload_unit_start, payload):
        buf = self.buffers[pid]
        sections = []
        if payload_unit_start:
            if not payload:
                return sections
            pointer = payload[0]
            if pointer > len(payload) - 1:
                buf.clear()
                return sections
            # Bytes before the pointer complete an older section, if any.
            buf += payload[1:1 + pointer]
            sections += self._drain(buf)
            buf.clear()
            buf += payload[1 + pointer:]
        else:
            buf += payload
        sections += self._drain(buf)
        return sections


def ts_payload(pkt):
    if len(pkt) != 188 or pkt[0] != 0x47:
        return None
    pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
    pusi = bool(pkt[1] & 0x40)
    afc = (pkt[3] >> 4) & 3
    if afc in (0, 2):
        return pid, pusi, b""
    pos = 4
    if afc == 3:
        if pos >= len(pkt):
            return None
        pos += 1 + pkt[pos]
    if pos > len(pkt):
        return None
    return pid, pusi, pkt[pos:]


def parse_pat(section):
    if len(section) < 12 or section[0] != 0x00:
        return {}
    result = {}
    for i in range(8, len(section) - 4, 4):
        if i + 4 > len(section) - 4:
            break
        program = (section[i] << 8) | section[i + 1]
        pid = ((section[i + 2] & 0x1F) << 8) | section[i + 3]
        if program:
            result[program] = pid
    return result


def parse_cat(section):
    if len(section) < 12 or section[0] != 0x01:
        return []
    return ca_descriptors(section[8:-4])


def parse_pmt(section):
    if len(section) < 16 or section[0] != 0x02:
        return None
    program = (section[3] << 8) | section[4]
    pcr_pid = ((section[8] & 0x1F) << 8) | section[9]
    info_len = ((section[10] & 0x0F) << 8) | section[11]
    pos = 12
    if pos + info_len > len(section) - 4:
        return None
    program_ca = ca_descriptors(section[pos:pos + info_len])
    pos += info_len
    streams = []
    while pos + 5 <= len(section) - 4:
        stream_type = section[pos]
        pid = ((section[pos + 1] & 0x1F) << 8) | section[pos + 2]
        es_len = ((section[pos + 3] & 0x0F) << 8) | section[pos + 4]
        pos += 5
        if pos + es_len > len(section) - 4:
            break
        streams.append((stream_type, pid, ca_descriptors(section[pos:pos + es_len])))
        pos += es_len
    return program, pcr_pid, program_ca, streams


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ts", help="188-byte-aligned MPEG-TS file")
    ap.add_argument("--limit-packets", type=int, default=200000,
                    help="stop after this many packets once PSI has been seen")
    args = ap.parse_args()

    psi = PsiReassembler()
    pat = {}
    cat = []
    pmts = {}
    invalid_crc = defaultdict(int)
    packets = 0
    with open(args.ts, "rb") as src:
        while packets < args.limit_packets:
            pkt = src.read(188)
            if not pkt:
                break
            packets += 1
            decoded = ts_payload(pkt)
            if decoded is None:
                continue
            pid, pusi, payload = decoded
            if pid != 0 and pid != 1 and pid not in pat.values():
                continue
            for section in psi.feed(pid, pusi, payload):
                if len(section) < 4 or mpeg2_crc32(section) != 0:
                    invalid_crc[pid] += 1
                    continue
                if pid == 0:
                    pat.update(parse_pat(section))
                elif pid == 1:
                    cat.extend(parse_cat(section))
                elif pid in pat.values():
                    parsed = parse_pmt(section)
                    if parsed:
                        pmts[parsed[0]] = parsed
            if pat and pmts and packets > 10000:
                break

    print(f"# inspected {packets:,} packets from {args.ts}")
    print("# PAT programs: " + (" ".join(
        f"{program}->PMT 0x{pid:04x}" for program, pid in sorted(pat.items())) or "none"))
    if invalid_crc:
        print("# invalid PSI CRC sections: " + " ".join(
            f"PID 0x{pid:04x}={count}" for pid, count in sorted(invalid_crc.items())))
    if not pat:
        print("# no parseable PAT: this may be a USB/host-side framed stream that"
              " still requires a driver or viewer transform")
    if cat:
        print("# CAT CA descriptors:")
        for system_id, pid, private in cat:
            print(f"#   CA_system_id=0x{system_id:04x} EMM_PID=0x{pid:04x} private={private.hex()}")
    else:
        print("# CAT CA descriptors: none")
    for program, pmt_pid in sorted(pat.items()):
        parsed = pmts.get(program)
        if not parsed:
            print(f"# program {program}: PMT 0x{pmt_pid:04x} not seen")
            continue
        _, pcr_pid, program_ca, streams = parsed
        print(f"# program {program}: PMT=0x{pmt_pid:04x} PCR=0x{pcr_pid:04x}")
        for system_id, pid, private in program_ca:
            print(f"#   program CA_system_id=0x{system_id:04x} ECM_PID=0x{pid:04x} private={private.hex()}")
        for stream_type, pid, es_ca in streams:
            label = STREAM_TYPES.get(stream_type, "private/other")
            line = f"#   ES PID=0x{pid:04x} type=0x{stream_type:02x} ({label})"
            if es_ca:
                line += " " + " ".join(
                    f"CA=0x{system_id:04x}/ECM 0x{ca_pid:04x}"
                    for system_id, ca_pid, _ in es_ca)
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
