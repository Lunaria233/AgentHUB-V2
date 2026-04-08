from __future__ import annotations

import unittest

from pricing import apply_discount


class PricingTests(unittest.TestCase):
    def test_apply_discount(self) -> None:
        self.assertEqual(apply_discount(200, 0.1), 180.0)

    def test_apply_discount_boundary(self) -> None:
        self.assertEqual(apply_discount(200, 0), 200)
        self.assertEqual(apply_discount(200, 1), 0)

    def test_apply_discount_validation(self) -> None:
        with self.assertRaises(ValueError):
            apply_discount(100, -0.1)
        with self.assertRaises(ValueError):
            apply_discount(100, 1.1)


if __name__ == "__main__":
    unittest.main()

