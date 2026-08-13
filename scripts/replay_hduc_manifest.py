#!/usr/bin/env python3
"""Replay a normalized HDUC initialization manifest with a live nonce.

The bundled manifest contains protocol operations and timing only. Captured
session nonces, USBPcap records, Bulk payloads, and broadcast data are not
stored in it.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from pathlib import Path

import usb.core
import usb.util


VID, PID = 0x3275, 0x7080
DAT = bytes.fromhex("397230c3add44636bae55f48ae1406c1")


def terrestrial_frequency(channel: int) -> tuple[int, int]:
    if not 13 <= channel <= 62:
        raise ValueError("terrestrial physical channel must be in 13..62")
    frequency_khz = 473_143 + (channel - 13) * 6_000
    return frequency_khz, frequency_khz * 64 // 1_000


def patch_terrestrial_tune(commands: list[dict], channel: int) -> tuple[int, int, int]:
    frequency_khz, tuner_word = terrestrial_frequency(channel)
    wanted = {0x14: tuner_word & 0xFF, 0x15: tuner_word >> 8}
    counts = {0x14: 0, 0x15: 0}
    for pos, command in enumerate(commands[:-1]):
        if (
            command.get("kind") != "literal"
            or command["request"] != 0x0D
            or command["value"] != 0xFE00
            or command["index"] not in (0x14C0, 0x15C0)
        ):
            continue
        register = command["index"] >> 8
        following = commands[pos + 1]
        if (
            following.get("kind") != "literal"
            or following["request"] != 0x0D
            or following["value"] & 0xFF != 0x03
            or following["index"] != 0
        ):
            raise ValueError(f"incomplete tuner register 0x{register:02x} write")
        following["value"] = (wanted[register] << 8) | 0x03
        counts[register] += 1
    if counts[0x14] == 0 or counts[0x14] != counts[0x15]:
        raise ValueError(
            "manifest contains no complete terrestrial frequency write "
            f"(reg14={counts[0x14]}, reg15={counts[0x15]})"
        )
    return frequency_khz, tuner_word, counts[0x14]


def load_manifest(path: Path) -> list[dict]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("format") != "hduc-control-manifest-v1":
        raise ValueError("unsupported manifest format")
    commands = manifest.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError("manifest contains no commands")
    return commands


def vin(device, request: int, value: int, index: int, length: int) -> bytes:
    return bytes(device.ctrl_transfer(0xC0, request, value, index, length, timeout=1000))


def find_runtime(bus: int | None, port: int | None):
    for device in usb.core.find(find_all=True, idVendor=VID, idProduct=PID) or []:
        if bus is not None and getattr(device, "bus", None) != bus:
            continue
        ports = tuple(getattr(device, "port_numbers", ()) or ())
        if port is not None and (not ports or ports[0] != port):
            continue
        return device
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--terrestrial-channel", type=int, metavar="13..62", required=True)
    parser.add_argument("--bus", type=int, help="physical USB bus filter")
    parser.add_argument("--port", type=int, help="first-level physical USB port filter")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        commands = load_manifest(args.manifest)
        frequency_khz, tuner_word, tune_count = patch_terrestrial_tune(
            commands, args.terrestrial_channel
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2

    request_count = sum(2 if command["kind"] == "nonce-pair" else 1 for command in commands)
    print(
        f"# commands={request_count} terrestrial physical ch{args.terrestrial_channel}: "
        f"center={frequency_khz}kHz tuner_word=0x{tuner_word:04x} "
        f"patched_tunes={tune_count}"
    )

    device = None
    if not args.dry_run:
        device = find_runtime(args.bus, args.port)
        if device is None:
            where = ""
            if args.bus is not None or args.port is not None:
                where = f" at bus={args.bus} port={args.port}"
            print(f"runtime device 3275:7080 not found{where}", file=sys.stderr)
            return 2
        try:
            device.set_configuration()
        except usb.core.USBError:
            pass
        usb.util.claim_interface(device, 0)

    current_nonce: bytes | None = None
    sent = errors = 0
    try:
        for position, command in enumerate(commands):
            delay = float(command.get("delay_ms", 0)) / 1000.0
            if delay > 0 and not args.dry_run:
                time.sleep(delay)
            kind = command["kind"]
            transfers: list[tuple[int, int, int, int]]
            if kind == "literal":
                transfers = [(
                    command["request"], command["value"],
                    command["index"], command["length"],
                )]
            elif kind == "nonce-1c":
                if current_nonce is None:
                    raise RuntimeError(f"command {position}: 0x1c before live nonce")
                base = command["base"]
                real = command["real"]
                obfuscated = real ^ DAT[base & 0x0F] ^ current_nonce[base >> 4]
                index = obfuscated | ((base ^ obfuscated) << 8)
                transfers = [(0x1C, command["value"], index, command["length"])]
            elif kind == "nonce-pair":
                if current_nonce is None:
                    raise RuntimeError(f"command {position}: 0x1d/0x1e before live nonce")
                decoded = bytes.fromhex(command["decoded"])
                encoded = bytes(a ^ b for a, b in zip(decoded, current_nonce[8:16]))
                value1, index1, value2, index2 = struct.unpack("<HHHH", encoded)
                transfers = [
                    (0x1D, value1, index1, command["length1"]),
                    (0x1E, value2, index2, command["length2"]),
                ]
            else:
                raise RuntimeError(f"command {position}: unknown kind {kind!r}")

            for transfer_index, (request, value, index, length) in enumerate(transfers):
                if transfer_index and command.get("pair_delay_ms") and not args.dry_run:
                    time.sleep(float(command["pair_delay_ms"]) / 1000.0)
                if args.dry_run:
                    if request == 0x1A:
                        current_nonce = bytes(16)
                    continue
                try:
                    response = vin(device, request, value, index, length)
                    sent += 1
                    if request == 0x1A:
                        if len(response) != 16:
                            raise RuntimeError("request 0x1a returned a non-16-byte nonce")
                        current_nonce = response
                except usb.core.USBError as exc:
                    if getattr(exc, "errno", None) == 19:
                        raise RuntimeError("USB device disconnected during replay") from exc
                    errors += 1
                    print(
                        f"ERR req={request:02x} val={value:04x} idx={index:04x}: {exc}",
                        file=sys.stderr,
                    )
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(f"replay error: {exc}", file=sys.stderr)
        errors += 1
    finally:
        if device is not None:
            try:
                usb.util.release_interface(device, 0)
            except usb.core.USBError:
                pass

    print(f"# replay complete: sent={sent} errors={errors}; no stream-start sent")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
