#!/usr/bin/env python3
"""Run the complete three-session U3 startup and capture terrestrial raw data.

The owner's successful ``good2`` startup performs three secure proxy sessions
before the first terrestrial tune.  This runner uses the exact public session
material and f018 values recorded in ``good2`` because fixed encrypted card
proxy writes later in the normalized template are bound to those sessions.
The current-device f010 response is calculated by the native Linux transform.

No USB reset is issued.  The selected physical port is mandatory so the HDUC
on another port cannot be opened accidentally.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from u3_control_template import DEFAULT_TEMPLATE, load_control_template
from u3_f010_transform import f010_response
from u3_replay import device_present, replay, sequence_for
from u3_channels import parse_u3_channel
from u3_satellite_tuning import satellite_tune_sequence
from u3_terrestrial_tuning import patch_terrestrial_tune
from u3_f010_live import current_challenge, device_filter, run_hduc
from u3_good2_secure_material import (
    GOOD2_SESSIONS, PROPERTY9_CLEAR, PUBLIC_EXPONENT,
)
from u3_session_prefix import build_sequence_from_values


def ensure_runtime(args: argparse.Namespace) -> None:
    if device_present(args.hduc, "0x3275", "0x9010", args.bus, args.port):
        return
    if not device_present(args.hduc, "0x1738", "0x5211", args.bus, args.port):
        raise RuntimeError(
            f"neither U3 loader nor runtime found at bus {args.bus} port {args.port}")
    run_hduc([
        str(args.hduc), "loader-upload", str(args.firmware),
        "--bus", str(args.bus), "--port", str(args.port),
    ])
    for _ in range(80):
        if device_present(args.hduc, "0x3275", "0x9010", args.bus, args.port):
            return
        time.sleep(0.1)
    raise RuntimeError("U3 did not enumerate as 3275:9010 after firmware upload")


def vendor_out(args: argparse.Namespace, value: int, index: int,
               payload: bytes) -> None:
    run_hduc([
        str(args.hduc), "vendor-ctl", "--vid", "0x3275", "--pid", "0x9010",
        "--dir", "out", "--req", "0x26", "--val", f"0x{value:04x}",
        "--idx", f"0x{index:04x}", "--len", str(len(payload)),
        "--data", payload.hex(),
    ] + device_filter(args.bus, args.port))


def establish(args: argparse.Namespace, index: int, label: str) -> None:
    session = GOOD2_SESSIONS[index]
    sequence, wire = build_sequence_from_values(
        index, session["modulus"], PUBLIC_EXPONENT, session["table_entry"])
    print(
        f"{label}: index={index} modulus={session['modulus'].hex()} "
        f"wire={wire.hex()}",
        flush=True,
    )
    replay(
        args.hduc, sequence, args.bus, args.port,
        f"{label} retained exact-good2 RSA prefix", args.early_replay_scale,
    )
    challenge = current_challenge(
        args.hduc, "0x3275", "0x9010", args.bus, args.port)
    response = f010_response(challenge)
    print(
        f"{label}: f010 challenge={challenge.hex()} response={response.hex()}",
        flush=True,
    )
    vendor_out(args, 0x05F0, 0xF010, response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus", type=int, default=2)
    parser.add_argument("--port", type=int, required=True,
                        help="physical U3 port; required to avoid another ASICEN device")
    parser.add_argument("--channel", type=int, default=21,
                        choices=range(13, 63), metavar="13..62")
    parser.add_argument(
        "--satellite-channel",
        help=("after the terrestrial bootstrap/re-arm, enter this BS/CS "
              "physical channel before queueing EP81 (for example BS13_0 or CS22)"),
    )
    parser.add_argument("--seconds", type=int, default=8)
    parser.add_argument(
        "--replay-scale", type=float, default=1.0,
        help=("scale only the recorded inter-control waits; use a value below 1 "
              "for a watchdog timing experiment"),
    )
    parser.add_argument(
        "--early-replay-scale", type=float,
        help=("override the scale through secure session 3; later card, tune, and "
              "re-arm waits retain --replay-scale"),
    )
    parser.add_argument(
        "--hold-after", type=int, default=120,
        help=("seconds to retain the same USB handle with heartbeats after "
              "capture; use a large value for an unattended session"),
    )
    parser.add_argument("--out", type=Path, default=Path("/tmp/u3-full-ch21.raw"))
    parser.add_argument(
        "--ready-file",
        type=Path,
        help="marker written after Bulk capture and before the keepalive hold",
    )
    finish = parser.add_mutually_exclusive_group()
    finish.add_argument(
        "--no-start", action="store_true",
        help="stop before the Windows re-arm cycle",
    )
    finish.add_argument(
        "--prepare-server", action="store_true",
        help="perform the re-arm cycle, then let a persistent server queue/start EP81",
    )
    parser.add_argument("--hduc", type=Path,
                        default=Path("tools/hduc_ctl/hduc_ctl"))
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE,
                        help="normalized response-free good2 control template")
    parser.add_argument("--firmware", type=Path,
                        default=Path("firmware/as11loader_decrypted_full.bin"))
    args = parser.parse_args()
    if args.seconds < 1:
        parser.error("--seconds must be positive")
    if args.satellite_channel is not None:
        try:
            satellite_channel = parse_u3_channel(args.satellite_channel)
        except ValueError as error:
            parser.error(str(error))
        if satellite_channel.system == "T":
            parser.error("--satellite-channel must be a BS or CS selector")
    else:
        satellite_channel = None
    if not 0 < args.replay_scale <= 1:
        parser.error("--replay-scale must be in (0, 1]")
    if args.early_replay_scale is None:
        args.early_replay_scale = args.replay_scale
    elif not 0 < args.early_replay_scale <= 1:
        parser.error("--early-replay-scale must be in (0, 1]")
    if args.hold_after < 0:
        parser.error("--hold-after must not be negative")
    print(
        "loaded driver-independent exact-good2 secure material "
        f"property9={PROPERTY9_CLEAR.hex()}",
        flush=True,
    )

    commands = load_control_template(args.template)
    ensure_runtime(args)

    replay(args.hduc, sequence_for(commands, 4.275, 17.258),
           args.bus, args.port, "fixed boot before session 1", args.early_replay_scale)
    establish(args, 11, "session 1")
    replay(args.hduc, sequence_for(commands, 17.417, 19.039),
           args.bus, args.port, "fixed setup between sessions 1 and 2", args.early_replay_scale)

    establish(args, 8, "session 2")
    replay(args.hduc, sequence_for(commands, 19.196, 19.387),
           args.bus, args.port, "session 2 before f018", args.early_replay_scale)
    f018_8 = GOOD2_SESSIONS[8]["f018"]
    print(f"session 2: f018={f018_8.hex()}", flush=True)
    vendor_out(args, 0x07F0, 0xF018, f018_8)
    # Card OUT blocks in this interval are transforms under fixed table index
    # 8 and were verified offline against the original routine.  Card IN data
    # is read from the current device and intentionally not replayed as data.
    replay(args.hduc, sequence_for(commands, 19.389, 22.188),
           args.bus, args.port, "session 2 card exchange and fixed setup", args.early_replay_scale)

    establish(args, 7, "session 3")
    replay(args.hduc, sequence_for(commands, 22.365, 22.530),
           args.bus, args.port, "session 3 before f018", args.early_replay_scale)
    f018_7 = GOOD2_SESSIONS[7]["f018"]
    print(f"session 3: f018={f018_7.hex()}", flush=True)
    vendor_out(args, 0x07F0, 0xF018, f018_7)
    replay(args.hduc, sequence_for(commands, 22.548, 35.409),
           args.bus, args.port, "session 3 card exchange and readiness wait", args.replay_scale)

    tune_window = [
        command for command in commands if 35.558 <= command["t"] <= 35.843
    ]
    tune_window, frequency_khz, tuner_word = patch_terrestrial_tune(
        tune_window, args.channel
    )
    print(
        f"physical ch{args.channel}: center={frequency_khz}kHz "
        f"tuner_word=0x{tuner_word:04x}",
        flush=True,
    )
    replay(args.hduc, sequence_for(tune_window, 35.558, 35.843),
           args.bus, args.port,
           f"physical ch{args.channel} tune and PID filters", args.replay_scale)
    run_hduc([
        str(args.hduc), "u3-monitor", "--vid", "0x3275", "--pid", "0x9010",
        "--seconds", "3", "--interval-ms", "500",
    ] + device_filter(args.bus, args.port))
    if args.no_start:
        return 0

    # good2 itself receives no EP81 payload after its first 0x06.  Windows
    # performs this complete ~0.85 s re-arm cycle and only the second 0x06
    # starts Bulk delivery.  Reproduce that state transition instead of
    # waiting on the known-idle first start.
    replay(args.hduc, sequence_for(commands, 35.890, 36.708),
           args.bus, args.port, "first start and Windows re-arm cycle", args.replay_scale)
    if satellite_channel is not None:
        replay(
            args.hduc, satellite_tune_sequence(satellite_channel, entering=True),
            args.bus, args.port,
            f"bootstrap terrestrial to {satellite_channel.canonical} transition",
        )
    if args.prepare_server:
        print("U3 re-arm complete; persistent server must queue EP81 then send 0x06", flush=True)
        return 0
    receive_command = [
        str(args.hduc), "async-bulk", "--vid", "0x3275", "--pid", "0x9010",
        "--ep", "0x81", "--buffers", "8", "--size", "8192",
        "--seconds", str(args.seconds), "--start", "0x06", "--hduc-post-start",
        "--hold-after", str(args.hold_after), "--out", str(args.out),
    ]
    if args.ready_file:
        receive_command += ["--ready-file", str(args.ready_file)]
    run_hduc(receive_command + device_filter(args.bus, args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
