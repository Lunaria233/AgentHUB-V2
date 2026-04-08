from __future__ import annotations


def apply_discount(total: float, discount_ratio: float) -> float:
    if discount_ratio < 0 or discount_ratio > 1:
        raise ValueError("discount_ratio must be between 0 and 1")
    # BUG: should be (1 - discount_ratio)
    return round(total * (1 + discount_ratio), 2)

