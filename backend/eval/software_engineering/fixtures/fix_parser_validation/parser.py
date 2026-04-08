from __future__ import annotations


def parse_limit(value: str) -> int:
    number = int(value)
    # BUG: negative value should raise ValueError instead of silently coercing
    if number < 0:
        return 0
    return number

