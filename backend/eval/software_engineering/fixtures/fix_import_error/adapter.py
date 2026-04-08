from __future__ import annotations

# BUG: wrong symbol name
from converter import slugify


def normalize_name(name: str) -> str:
    return slugify(name)

