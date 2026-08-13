#!/usr/bin/env python3
"""Safely derive a current U3 ``f010`` proxy response for hduc_ctl.

Without ``--write`` this is read-only: it reads the live challenge and prints
the response calculated by the native Linux transform.  ``--write``
performs the immediately following proxy write using that same value, avoiding
manual hexadecimal transcription.  It is only for MonsterTV U3 at 3275:9010.
"""

import argparse
import re
import subprocess
from pathlib import Path

from u3_f010_transform import f010_response


def run_hduc(command: list[str]) -> str:
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    if result.stderr:
        print(result.stderr, end="")
    print(result.stdout, end="")
    return result.stdout


def device_filter(bus: int | None, port: int | None) -> list[str]:
    result: list[str] = []
    if bus is not None:
        result += ["--bus", str(bus)]
    if port is not None:
        result += ["--port", str(port)]
    return result


def current_challenge(hduc: Path, vid: str, pid: str,
                      bus: int | None, port: int | None) -> bytes:
    output = run_hduc([str(hduc), "vendor-ctl", "--vid", vid, "--pid", pid,
                       "--dir", "in", "--req", "0x25", "--val", "0x03f0",
                       "--idx", "0xf010", "--len", "16"]
                      + device_filter(bus, port))
    match = re.search(r"^data:\s*((?:[0-9a-fA-F]{2}\s+){15}[0-9a-fA-F]{2})\s*$",
                      output, re.MULTILINE)
    if not match:
        raise RuntimeError("hduc_ctl did not return a 16-byte f010 challenge")
    return bytes.fromhex(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="write the derived response immediately after the live read")
    parser.add_argument("--vid", default="0x3275")
    parser.add_argument("--pid", default="0x9010")
    parser.add_argument("--bus", type=int)
    parser.add_argument("--port", type=int)
    parser.add_argument("--hduc", type=Path, default=Path("tools/hduc_ctl/hduc_ctl"))
    args = parser.parse_args()

    challenge = current_challenge(args.hduc, args.vid, args.pid, args.bus, args.port)
    response = f010_response(challenge)
    print(f"derived f010 response: {response.hex()}")
    if args.write:
        run_hduc([str(args.hduc), "vendor-ctl", "--vid", args.vid, "--pid", args.pid,
                  "--dir", "out", "--req", "0x26", "--val", "0x05f0",
                  "--idx", "0xf010", "--len", "16", "--data", response.hex()]
                  + device_filter(args.bus, args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
