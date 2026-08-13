"""Driver-independent constants for the retained exact-good2 U3 sessions."""

from __future__ import annotations


PROPERTY9_CLEAR = bytes.fromhex("4efc90949311f8cf474c8c11f41b6f2d")
PUBLIC_EXPONENT = b"\0" * 7 + b"\x11"

# Values sent in the owner's successful good2 session.  The table entries are
# stored in the driver's native byte order; the wire helper reverses them.
GOOD2_SESSIONS = {
    11: {
        "modulus": bytes.fromhex("aab0cf93ab6e00cb"),
        "table_entry": bytes.fromhex("5ff35ebdbe63a4c7"),
    },
    8: {
        "modulus": bytes.fromhex("a56c5836a5f97557"),
        "table_entry": bytes.fromhex("b9b8a16b52c4d4ab"),
        "f018": bytes.fromhex(
            "d78abfbcc80ee18c50e16a8d463fcd3444a1984dd42288a2"
        ),
    },
    7: {
        "modulus": bytes.fromhex("bb33161577e63cc7"),
        "table_entry": bytes.fromhex("926c3637c7c49713"),
        "f018": bytes.fromhex(
            "ab454a5d36d0d36f8fa87d1b9540b661ba21ecd1ee281d49"
        ),
    },
}
