"""Retune a streaming U3 while its primary EP81 handle remains open."""

from __future__ import annotations

import subprocess
from pathlib import Path

from u3_channels import U3Channel
from u3_replay import replay, sequence_for
from u3_satellite_tuning import (
    leave_satellite_sequence, satellite_transponder, satellite_tune_sequence,
)
from u3_terrestrial_tuning import patch_terrestrial_tune


TUNE_INTERVAL = (35.558, 35.843)
REARM_INTERVAL = (35.890, 36.708)


def retune_sequences(
    commands: list[dict], channel: int
) -> tuple[str, str, int, int]:
    """Build channel-consistent tune and re-arm sequences.

    The re-arm window repeats tuner registers 0x0d/0x0e.  Patching only the
    first window briefly tunes the requested channel and then silently returns
    to the template channel (ch21).  Both windows must therefore be patched.
    """
    sequences: list[str] = []
    frequency_khz = tuner_word = 0
    for start, end in (TUNE_INTERVAL, REARM_INTERVAL):
        window = [command for command in commands if start <= command["t"] <= end]
        window, frequency_khz, tuner_word = patch_terrestrial_tune(window, channel)
        sequences.append(sequence_for(window, start, end))
    return sequences[0], sequences[1], frequency_khz, tuner_word


def vendor_in(
    hduc: Path, bus: int, port: int, request: int, value: int, length: int
) -> None:
    subprocess.run(
        [
            str(hduc), "vendor-ctl", "--vid", "0x3275", "--pid", "0x9010",
            "--bus", str(bus), "--port", str(port), "--dir", "in",
            "--req", f"0x{request:02x}", "--val", f"0x{value:04x}",
            "--idx", "0", "--len", str(length),
        ],
        check=True,
    )


def retune_streaming_u3(
    hduc: Path,
    commands: list[dict],
    bus: int,
    port: int,
    channel: int,
    monitor_seconds: int = 2,
) -> tuple[int, int]:
    """Apply the proven live retune while another process drains EP81.

    The long-lived async-bulk process keeps the primary claimed interface and
    queued URBs.  These device-recipient control transfers use a short-lived
    secondary libusb handle; closing it does not disturb the primary stream.
    """
    tune, rearm, frequency_khz, tuner_word = retune_sequences(commands, channel)
    replay(hduc, tune, bus, port, f"persistent physical ch{channel} tune")
    replay(hduc, rearm, bus, port, f"persistent physical ch{channel} re-arm")
    # The primary process already has EP81 URBs queued.  Start only after both
    # channel-patched windows, then reproduce the Windows post-start probes.
    vendor_in(hduc, bus, port, 0x06, 0x0000, 1)
    vendor_in(hduc, bus, port, 0x04, 0x0040, 2)
    vendor_in(hduc, bus, port, 0x05, 0x0F40, 2)
    if monitor_seconds:
        subprocess.run(
            [
                str(hduc), "u3-monitor", "--vid", "0x3275", "--pid", "0x9010",
                "--bus", str(bus), "--port", str(port),
                "--seconds", str(monitor_seconds), "--interval-ms", "500",
            ],
            check=True,
        )
    return frequency_khz, tuner_word


def monitor_u3(hduc: Path, bus: int, port: int, seconds: int) -> None:
    if not seconds:
        return
    subprocess.run(
        [
            str(hduc), "u3-monitor", "--vid", "0x3275", "--pid", "0x9010",
            "--bus", str(bus), "--port", str(port),
            "--seconds", str(seconds), "--interval-ms", "500",
        ],
        check=True,
    )


def retune_u3_channel(
    hduc: Path,
    commands: list[dict],
    bus: int,
    port: int,
    previous: U3Channel,
    target: U3Channel,
    monitor_seconds: int = 2,
) -> tuple[int, int | None]:
    """Retune among terrestrial, BS, and 110-degree CS without closing EP81."""
    if target.system == "T":
        if previous.system != "T":
            replay(
                hduc, leave_satellite_sequence(), bus, port,
                "satellite to terrestrial mode transition",
            )
        return retune_streaming_u3(
            hduc, commands, bus, port, target.value, monitor_seconds
        )

    item = satellite_transponder(target)
    entering = previous.system == "T"
    replay(
        hduc, satellite_tune_sequence(target, entering), bus, port,
        f"persistent {target.canonical} satellite tune",
    )
    vendor_in(hduc, bus, port, 0x06, 0x0000, 1)
    vendor_in(hduc, bus, port, 0x04, 0x0040, 2)
    vendor_in(hduc, bus, port, 0x05, 0x0F40, 2)
    monitor_u3(hduc, bus, port, monitor_seconds)
    return item.frequency_khz, None


__all__ = [
    "REARM_INTERVAL", "TUNE_INTERVAL", "retune_sequences",
    "retune_streaming_u3", "retune_u3_channel",
]
