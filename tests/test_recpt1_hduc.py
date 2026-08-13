import importlib.util
import io
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


ROOT = Path(__file__).resolve().parents[1]


def load_extensionless_module(name: str, path: Path):
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


recpt1_hduc = load_extensionless_module(
    "recpt1_hduc", ROOT / "scripts" / "recpt1-hduc"
)


class RecordTimeTests(unittest.TestCase):
    def test_supported_forms(self):
        parse = recpt1_hduc.parse_record_time
        self.assertEqual(parse("-"), 0)
        self.assertEqual(parse("15"), 15)
        self.assertEqual(parse("01:02"), 62)
        self.assertEqual(parse("1:02:03"), 3723)
        self.assertEqual(parse("1H2M3S"), 3723)

    def test_invalid_forms(self):
        for value in ("0", "", "1:60", "abc", "-5"):
            with self.assertRaises(ValueError):
                recpt1_hduc.parse_record_time(value)


class StreamingTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.key, cls.mask = recpt1_hduc.load_material(
            ROOT / "data" / "hduc-x64-mode6-material.json"
        )

    def raw_from_clear(self, clear: bytes) -> bytes:
        encryptor = Cipher(algorithms.AES(self.key), modes.ECB()).encryptor()
        raw = bytearray(188)
        raw[:4] = clear[:4]
        for offset in range(4, 164, 16):
            encrypted = encryptor.update(clear[offset:offset + 16])
            raw[offset:offset + 16] = bytes(
                left ^ right for left, right in zip(encrypted, self.mask)
            )
        second_cipher = bytes(
            left ^ right
            for left, right in zip(encryptor.update(clear[164:180]), self.mask)
        )
        raw[164:172] = second_cipher[:8]
        first_output = second_cipher[8:] + clear[180:188]
        raw[172:188] = bytes(
            left ^ right
            for left, right in zip(encryptor.update(first_output), self.mask)
        )
        encryptor.finalize()
        return bytes(raw)

    @staticmethod
    def clear_packet(counter: int) -> bytes:
        packet = bytearray(188)
        packet[:4] = bytes((0x47, 0x40, counter & 0x1F, 0x10 | (counter & 0x0F)))
        packet[4:] = bytes((index + counter) & 0xFF for index in range(184))
        return bytes(packet)

    def test_cts_round_trip_and_sideband_resync(self):
        clear = [self.clear_packet(index) for index in range(4)]
        raw = [self.raw_from_clear(packet) for packet in clear]
        source = io.BytesIO(raw[0] + b"sideband-event-record-33-bytes!!!" + b"".join(raw[1:]))
        stats = recpt1_hduc.StreamStats()
        decryptor = Cipher(algorithms.AES(self.key), modes.ECB()).decryptor()
        transformed = [
            recpt1_hduc.transform_packet(packet, decryptor, self.mask)
            for packet in recpt1_hduc.packet_stream(source, stats, chunk_size=97)
        ]
        decryptor.finalize()
        self.assertEqual(transformed, clear)
        self.assertEqual(stats.packets, 4)
        self.assertEqual(len(stats.gaps), 1)
        self.assertEqual(stats.gaps[0][1], 33)


if __name__ == "__main__":
    unittest.main()
