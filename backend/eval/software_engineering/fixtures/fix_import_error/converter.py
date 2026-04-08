from __future__ import annotations


def to_slug(text: str) -> str:
    return "-".join(text.strip().lower().split())

