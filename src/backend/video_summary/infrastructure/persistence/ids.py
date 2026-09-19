"""无需外部依赖的 ULID 生成器。"""

from __future__ import annotations

import secrets
import time


_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    """生成 26 字符、时间有序的 ULID。"""

    timestamp_ms = int(time.time() * 1_000)
    if timestamp_ms >= 1 << 48:
        raise RuntimeError("ULID timestamp overflow.")
    value = (timestamp_ms << 80) | secrets.randbits(80)
    encoded: list[str] = []
    for _ in range(26):
        encoded.append(_CROCKFORD32[value & 31])
        value >>= 5
    return "".join(reversed(encoded))
