import importlib.util
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract_as11loader_firmware.py"
SPEC = importlib.util.spec_from_file_location("firmware_extract", SCRIPT)
firmware_extract = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(firmware_extract)


class FirmwareExtractTests(unittest.TestCase):
    def test_key_and_firmware_are_derived_from_supplied_bytes(self):
        key = bytes(range(16))
        plaintext = bytes((index * 29 + 7) & 0xFF for index in range(0x4000))

        encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        encrypted = encryptor.update(plaintext) + encryptor.finalize()
        stored = bytes((value + 1) & 0xFF for value in encrypted)

        image = bytearray(
            firmware_extract.CIPHERTEXT_OFFSET + firmware_extract.FIRMWARE_SIZE
        )
        for index, value in enumerate(key):
            offset = firmware_extract.KEY_INSTRUCTION_OFFSET + index * 4
            image[offset:offset + 4] = bytes(
                (0xC6, 0x45, (0xEC + index) & 0xFF, value)
            )
        image[
            firmware_extract.CIPHERTEXT_OFFSET:
            firmware_extract.CIPHERTEXT_OFFSET + firmware_extract.FIRMWARE_SIZE
        ] = stored

        self.assertEqual(firmware_extract.key_from_driver(image), key)
        self.assertEqual(firmware_extract.decrypt_firmware(image), plaintext)

    def test_bad_key_instruction_is_rejected(self):
        image = bytearray(
            firmware_extract.CIPHERTEXT_OFFSET + firmware_extract.FIRMWARE_SIZE
        )
        with self.assertRaisesRegex(ValueError, "expected loader key instruction"):
            firmware_extract.key_from_driver(image)


if __name__ == "__main__":
    unittest.main()
