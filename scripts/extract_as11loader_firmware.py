#!/usr/bin/env python3
"""Create the ASIE5607 runtime image from an owner-supplied loader driver.

The vendor driver is not distributed by this project. This extractor accepts
only the known 32-bit ``SKNET_AS11Loader.sys`` build shared by the supported
HDUC and U3 packages, derives the AES key from that supplied file, decrypts its
embedded RAM image, and verifies the exact known output hash.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


SUPPORTED_DRIVER_SHA256 = (
    "9abd9c8cd901d36235d96e8361ab51d7b8538bdc39a38a03d4c2d7c1b6ecfbe0"
)
EXPECTED_FIRMWARE_SHA256 = (
    "f4848c8c091634897f9829e50d2ff8e5dc28792c6b20cf095d38d40379518c7a"
)

# File offsets in the supported PE32 driver. Restricting the input hash above
# keeps these build-specific locations from silently producing bad firmware.
KEY_INSTRUCTION_OFFSET = 0x09EB
CIPHERTEXT_OFFSET = 0x55D8
FIRMWARE_SIZE = 0x4000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key_from_driver(driver: bytes) -> bytes:
    """Read the 16 byte immediates loaded by the driver's key setup code."""
    key = bytearray()
    for index in range(16):
        offset = KEY_INSTRUCTION_OFFSET + index * 4
        instruction = driver[offset:offset + 4]
        expected_displacement = (0xEC + index) & 0xFF
        if (
            len(instruction) != 4
            or instruction[:2] != b"\xC6\x45"
            or instruction[2] != expected_displacement
        ):
            raise ValueError(
                "the supplied file does not contain the expected loader key "
                f"instruction at file offset 0x{offset:x}"
            )
        key.append(instruction[3])
    return bytes(key)


def decrypt_firmware(driver: bytes) -> bytes:
    key = key_from_driver(driver)
    ciphertext = driver[CIPHERTEXT_OFFSET:CIPHERTEXT_OFFSET + FIRMWARE_SIZE]
    if len(ciphertext) != FIRMWARE_SIZE:
        raise ValueError(
            f"expected 0x{FIRMWARE_SIZE:x} bytes at file offset "
            f"0x{CIPHERTEXT_OFFSET:x}; this is not the supported driver build"
        )

    adjusted = bytes((value - 1) & 0xFF for value in ciphertext)
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return decryptor.update(adjusted) + decryptor.finalize()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "driver",
        type=Path,
        help="path to your own 32-bit SKNET_AS11Loader.sys",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("firmware/as11loader_decrypted_full.bin"),
        help="generated local image (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        driver = args.driver.read_bytes()
    except OSError as error:
        raise SystemExit(f"cannot read {args.driver}: {error}") from error

    driver_hash = sha256(driver)
    if driver_hash != SUPPORTED_DRIVER_SHA256:
        raise SystemExit(
            "unsupported SKNET_AS11Loader.sys build\n"
            f"  supplied SHA-256: {driver_hash}\n"
            f"  supported SHA-256: {SUPPORTED_DRIVER_SHA256}\n"
            "Use the 32-bit loader driver described in README.md; the 64-bit "
            "file is not interchangeable."
        )

    try:
        firmware = decrypt_firmware(driver)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    firmware_hash = sha256(firmware)
    if firmware_hash != EXPECTED_FIRMWARE_SHA256:
        raise SystemExit(
            "generated firmware failed verification\n"
            f"  generated SHA-256: {firmware_hash}\n"
            f"  expected SHA-256:  {EXPECTED_FIRMWARE_SHA256}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(firmware)
    print(f"driver SHA-256:   {driver_hash}")
    print(f"firmware SHA-256: {firmware_hash}")
    print(f"wrote {len(firmware)} bytes to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
