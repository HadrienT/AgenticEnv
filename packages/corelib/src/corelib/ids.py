from __future__ import annotations

import os
import time
import uuid


def new_uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: sortable by creation time, unique per-process via random bits."""
    unix_ms = time.time_ns() // 1_000_000
    rand = os.urandom(10)

    time_bytes = unix_ms.to_bytes(6, byteorder="big")
    # Version 7 in the high nibble of byte 6, 12 random bits follow.
    byte6 = 0x70 | (rand[0] & 0x0F)
    byte7 = rand[1]
    # Variant bits (10xx xxxx) in byte 8.
    byte8 = 0x80 | (rand[2] & 0x3F)

    raw = time_bytes + bytes([byte6, byte7, byte8]) + rand[3:10]
    return uuid.UUID(bytes=raw)


def new_id() -> str:
    """Sortable, unique string identifier — the default `id` for DTOs and rows."""
    return str(new_uuid7())


def deterministic_key(*parts: str) -> str:
    """Stable key from ordered parts, e.g. a doc_key-like slug composition."""
    return "-".join(p.strip().lower().replace(" ", "_") for p in parts if p)
