"""Parse recpt1-style U3 terrestrial and satellite channel selectors."""

from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class U3Channel:
    system: str
    value: int
    canonical: str = field(compare=False)


SERVICE_ALIASES = {
    "BS141": ("BS", 13, "BS13_0"),
    "BSNITTELE": ("BS", 13, "BS13_0"),
    "CS161": ("CS", 22, "CS22"),
    "QVC": ("CS", 22, "CS22"),
}


def parse_u3_channel(value: str | int) -> U3Channel:
    text = str(value).strip().upper()
    if text.isdigit():
        channel = int(text)
        if 13 <= channel <= 62:
            return U3Channel("T", channel, str(channel))
        raise ValueError("terrestrial physical channel must be in 13..62")

    alias = SERVICE_ALIASES.get(text)
    if alias is not None:
        return U3Channel(*alias)

    match = re.fullmatch(r"BS(\d{1,2})(?:_(\d+))?", text)
    if match:
        transponder = int(match.group(1))
        if 1 <= transponder <= 23 and transponder % 2 == 1:
            slot = int(match.group(2) or 0)
            return U3Channel("BS", transponder, f"BS{transponder}_{slot}")
        raise ValueError("BS transponder must be odd-numbered BS1..BS23")

    match = re.fullmatch(r"CS(\d{1,2})", text)
    if match:
        transponder = int(match.group(1))
        if 2 <= transponder <= 24 and transponder % 2 == 0:
            return U3Channel("CS", transponder, f"CS{transponder}")
        raise ValueError("CS transponder must be even-numbered CS2..CS24")

    raise ValueError(
        "channel must be terrestrial 13..62, BS1..BS23 (odd), "
        "CS2..CS24 (even), BS141/BSNITTELE, or CS161/QVC"
    )


__all__ = ["SERVICE_ALIASES", "U3Channel", "parse_u3_channel"]
