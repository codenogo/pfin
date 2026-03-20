#!/usr/bin/env python3
"""Hash-based ID generation for the cnogo memory engine.

IDs are generated locally with time-based entropy, require no coordination
between agents, and work offline across branches and machines.
Given the same title/creator inputs, IDs are intentionally non-deterministic.

Format:  cn-<base36>          (e.g. cn-a3f8)
Child:   cn-<base36>.<N>      (e.g. cn-a3f8.1)
"""

from __future__ import annotations

import hashlib
import time


def _encode_base36(num: int) -> str:
    """Encode a non-negative integer to base36."""
    if num == 0:
        return "0"
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    result: list[str] = []
    while num:
        result.append(chars[num % 36])
        num //= 36
    return "".join(reversed(result))


def generate_id(
    title: str,
    creator: str = "claude",
    *,
    id_bytes: int = 4,
    nonce: int = 0,
) -> str:
    """Generate a candidate hash-based ID.

    Algorithm:
      1. input = title + creator + timestamp_nanos + nonce
      2. hash  = SHA256(input)
      3. Take first `id_bytes` bytes
      4. Encode as base36
      5. Return "cn-{base36}"

    Because timestamp entropy is included, this is non-deterministic across
    calls. Caller is responsible for collision checks (see storage.id_exists).
    """
    ts = str(time.time_ns())
    raw = f"{title}\x00{creator}\x00{ts}\x00{nonce}"
    h = hashlib.sha256(raw.encode("utf-8")).digest()
    num = int.from_bytes(h[:id_bytes], "big")
    return f"cn-{_encode_base36(num)}"


def generate_child_id(parent_id: str, child_number: int) -> str:
    """Generate a hierarchical child ID: <parent_id>.<N>."""
    return f"{parent_id}.{child_number}"


def content_hash(*fields: str) -> str:
    """SHA256-based content hash of substantive fields (first 16 hex chars)."""
    combined = "\x00".join(fields)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
