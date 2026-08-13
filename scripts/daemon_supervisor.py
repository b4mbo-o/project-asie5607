#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 bamboo
"""Small restart supervisor shared by hducd and u3d."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


WORKER_ENV = "ASIE5607_DAEMON_WORKER"


def worker_process() -> bool:
    return os.environ.get(WORKER_ENV) == "1"


def supervise(script: Path, label: str, arguments: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if arguments is None else arguments)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--no-recover", action="store_true")
    parser.add_argument("--retry-seconds", type=float, default=2.0)
    parser.add_argument("--max-restarts", type=int, default=0)
    options, worker_arguments = parser.parse_known_args(argv)
    if options.retry_seconds < 0.1:
        parser.error("--retry-seconds must be at least 0.1")
    if options.max_restarts < 0:
        parser.error("--max-restarts must not be negative")

    one_shot = options.no_recover or "--dry-run" in worker_arguments or any(
        option in worker_arguments for option in ("-h", "--help")
    )
    stopping = False
    child: subprocess.Popen[bytes] | None = None

    def stop(signum: int, _frame) -> None:
        nonlocal stopping
        stopping = True
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    previous_int = signal.signal(signal.SIGINT, stop)
    previous_term = signal.signal(signal.SIGTERM, stop)
    restarts = 0
    try:
        while True:
            environment = os.environ.copy()
            environment[WORKER_ENV] = "1"
            command = [sys.executable, "-u", str(script), *worker_arguments]
            if restarts:
                print(
                    f"{label} recovery attempt {restarts}: restarting without USB reset",
                    file=sys.stderr, flush=True,
                )
            child = subprocess.Popen(command, env=environment, start_new_session=True)
            returncode = child.wait()
            child = None
            if stopping:
                return 128 + signal.SIGTERM if returncode < 0 else returncode
            if one_shot:
                return returncode
            if options.max_restarts and restarts >= options.max_restarts:
                print(
                    f"{label}: maximum recovery attempts reached; last status={returncode}",
                    file=sys.stderr,
                )
                return returncode or 2
            restarts += 1
            print(
                f"{label}: worker stopped with status {returncode}; "
                f"waiting {options.retry_seconds:g}s for the same USB path",
                file=sys.stderr, flush=True,
            )
            deadline = time.monotonic() + options.retry_seconds
            while not stopping and time.monotonic() < deadline:
                time.sleep(min(0.2, deadline - time.monotonic()))
            if stopping:
                return 128 + signal.SIGTERM
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)


__all__ = ["supervise", "worker_process"]
