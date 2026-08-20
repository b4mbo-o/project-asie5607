"""Shared replay helpers for the U3 Linux startup runners."""

from __future__ import annotations

import subprocess
from pathlib import Path


def sequence_for(commands: list[dict], start: float, end: float) -> str:
    selected = [command for command in commands if start <= command["t"] <= end]
    if not selected:
        raise RuntimeError(f"no commands in template interval {start}..{end}")
    lines = [
        "# Dynamic local extraction; fixed U3 model-specific controls only.",
        "# delay_ms direction request wValue wIndex wLength data-or-dash",
    ]
    previous = selected[0]["t"]
    for command in selected:
        delay = (command["t"] - previous) * 1000.0
        previous = command["t"]
        direction = "in" if command["bmrt"] & 0x80 else "out"
        data = command["request_data"].hex() if direction == "out" else "-"
        lines.append(
            f"{delay:.3f} {direction} 0x{command['req']:02x} "
            f"0x{command['value']:04x} 0x{command['index']:04x} "
            f"{command['length']} {data}"
        )
    return "\n".join(lines) + "\n"


def replay(hduc: Path, sequence: str, bus: int, port: int, label: str,
           scale: float = 1.0) -> None:
    print(f"replay {label}", flush=True)
    command = [
        str(hduc), "replay-control", "--vid", "0x3275", "--pid", "0x9010",
        "--bus", str(bus), "--port", str(port), "--file", "-",
        "--proxy-retries", "2", "--scale", str(scale), "--quiet",
    ]
    subprocess.run(command, input=sequence, text=True, check=True)


def device_present(hduc: Path, vid: str, pid: str, bus: int, port: int) -> bool:
    return subprocess.run(
        [str(hduc), "info", "--vid", vid, "--pid", pid,
         "--bus", str(bus), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
