import io
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "recpt1_pipeline", ROOT / "scripts" / "recpt1_pipeline.py"
)
pipeline = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pipeline)


def section(table_id, identity, body):
    section_length = 5 + len(body) + 4
    result = bytearray((table_id, 0xB0 | (section_length >> 8), section_length & 0xFF))
    result += identity.to_bytes(2, "big")
    result += b"\xC1\x00\x00" + body
    result += pipeline.mpeg_crc32(result).to_bytes(4, "big")
    return bytes(result)


def packet(pid, section_data=None, fill=0xA5, cc=0):
    header = bytearray((0x47, (pid >> 8) & 0x1F, pid & 0xFF, 0x10 | cc))
    if section_data is not None:
        header[1] |= 0x40
        body = b"\x00" + section_data
    else:
        body = bytes((fill,)) * 184
    return bytes(header + body + b"\xFF" * (188 - 4 - len(body)))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.sid = 141
        self.pmt_pid = 0x100
        pat_body = b"\x00\x00\xE0\x10" + self.sid.to_bytes(2, "big") + b"\xE1\x00"
        self.pat = packet(0, section(0, 1, pat_body), cc=7)
        # PCR=0x111, one H.264 ES=0x111, one AAC ES=0x112.
        pmt_body = b"\xE1\x11\xF0\x00" + b"\x1b\xE1\x11\xF0\x00" + b"\x0f\xE1\x12\xF0\x00"
        self.pmt = packet(self.pmt_pid, section(2, self.sid, pmt_body))

    def test_service_filter_rewrites_pat_and_keeps_selected_pids(self):
        selector = pipeline.TSServiceFilter((self.sid,), strip=True)
        rewritten = selector.filter(self.pat)
        self.assertIsNotNone(rewritten)
        self.assertEqual(selector.filter(self.pmt), self.pmt)
        self.assertTrue(selector.ready)
        assembler = pipeline.SectionAssembler()
        selected_pat = assembler.feed(rewritten)[0]
        _, _, programs = pipeline.pat_programs(selected_pat)
        self.assertEqual(programs, {self.sid: self.pmt_pid})
        self.assertEqual(selector.filter(packet(0x111)), packet(0x111))
        self.assertIsNone(selector.filter(packet(0x222)))
        self.assertIsNone(selector.filter(packet(0x1FFF)))

    def test_service_and_null_option_parsing(self):
        self.assertEqual(pipeline.parse_service_ids("0141,0x00a1,141"), (141, 161))
        self.assertEqual(pipeline.parse_service_ids("all"), ())
        with self.assertRaises(ValueError):
            pipeline.parse_service_ids("0")

    def test_external_b25_stream_protocol_and_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "b25"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "while True:\n"
                " data = sys.stdin.buffer.read(65536)\n"
                " if not data: break\n"
                " sys.stdout.buffer.write(data)\n"
                " sys.stdout.buffer.flush()\n"
            )
            fake.chmod(0o755)
            target = io.BytesIO()
            with pipeline.OutputPipeline(target, strip=True, b25=True,
                                         b25_binary=str(fake)) as output:
                output.write(packet(0x101))
                output.write(packet(0x1FFF))
            self.assertEqual(target.getvalue(), packet(0x101))
            self.assertEqual(output.output_packets, 1)


if __name__ == "__main__":
    unittest.main()
