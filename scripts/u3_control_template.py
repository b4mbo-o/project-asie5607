#!/usr/bin/env python3
"""Load the normalized, response-free U3 good2 control template."""

from __future__ import annotations

import json
from pathlib import Path


SCHEMA = "u3-control-template-v1"
DEFAULT_TEMPLATE = Path("templates/u3_good2_terrestrial.json")
TEMPLATE_WINDOWS = (
    (4.275, 17.258, "fixed boot before session 1"),
    (17.417, 19.039, "fixed setup between sessions 1 and 2"),
    (19.196, 19.387, "session 2 before f018"),
    (19.389, 22.188, "session 2 card exchange and fixed setup"),
    (22.365, 22.530, "session 3 before f018"),
    (22.548, 35.409, "session 3 card exchange and readiness wait"),
    (35.558, 35.843, "ch21 tune and PID filters"),
    (35.890, 36.708, "first start and Windows re-arm cycle"),
)


def load_control_template(path: Path = DEFAULT_TEMPLATE) -> list[dict]:
    """Return replay command dictionaries from a normalized template.

    The on-disk rows contain only host-issued USB setup values and OUT data.
    USBPcap completion responses, Bulk payloads, and smart-card IN data are
    deliberately absent.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != SCHEMA:
        raise ValueError(
            f"unsupported U3 template schema {document.get('schema')!r} in {path}"
        )
    commands = []
    previous_us = -1
    for row_number, row in enumerate(document.get("commands", []), 1):
        if not isinstance(row, list) or len(row) != 7:
            raise ValueError(f"template row {row_number} must have seven fields")
        t_us, bmrt, req, value, index, length, data_hex = row
        if not all(
            isinstance(value_, int)
            for value_ in (t_us, bmrt, req, value, index, length)
        ):
            raise ValueError(f"template row {row_number} has a non-integer setup field")
        if t_us < previous_us:
            raise ValueError(f"template timestamp goes backwards at row {row_number}")
        previous_us = t_us
        request_data = bytes.fromhex(data_hex)
        direction_in = bool(bmrt & 0x80)
        if direction_in and request_data:
            raise ValueError(f"template IN row {row_number} contains captured response data")
        if not direction_in and len(request_data) != length:
            raise ValueError(
                f"template OUT row {row_number} has {len(request_data)} data bytes, "
                f"expected {length}"
            )
        commands.append(
            {
                "t": t_us / 1_000_000,
                "bmrt": bmrt,
                "req": req,
                "value": value,
                "index": index,
                "length": length,
                "request_data": request_data,
            }
        )
    if not commands:
        raise ValueError(f"U3 control template is empty: {path}")
    return commands
