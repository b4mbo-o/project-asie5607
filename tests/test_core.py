import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from replay_hduc_manifest import patch_terrestrial_tune, terrestrial_frequency


class ChannelMathTests(unittest.TestCase):
    def test_edges_and_known_channel(self):
        self.assertEqual(terrestrial_frequency(13), (473_143, 0x7649))
        self.assertEqual(terrestrial_frequency(21), (521_143, 0x8249))
        self.assertEqual(terrestrial_frequency(62), (767_143, 0xBFC9))

    def test_invalid_channel(self):
        for channel in (0, 12, 63, 999):
            with self.assertRaises(ValueError):
                terrestrial_frequency(channel)

    def test_frequency_write_patch(self):
        commands = [
            {"kind": "literal", "request": 0x0D, "value": 0xFE00, "index": 0x14C0, "length": 4},
            {"kind": "literal", "request": 0x0D, "value": 0x0003, "index": 0, "length": 2},
            {"kind": "literal", "request": 0x0D, "value": 0xFE00, "index": 0x15C0, "length": 4},
            {"kind": "literal", "request": 0x0D, "value": 0x0003, "index": 0, "length": 2},
            {"kind": "literal", "request": 0x09, "value": 0x0100, "index": 0, "length": 1},
        ]
        frequency, word, count = patch_terrestrial_tune(commands, 35)
        self.assertEqual((frequency, word, count), (605_143, 0x9749, 1))
        self.assertEqual(commands[1]["value"], 0x4903)
        self.assertEqual(commands[3]["value"], 0x9703)
if __name__ == "__main__":
    unittest.main()
