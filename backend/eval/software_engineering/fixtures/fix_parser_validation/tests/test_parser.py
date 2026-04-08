from __future__ import annotations

import unittest

from parser import parse_limit


class ParserTests(unittest.TestCase):
    def test_parse_limit_success(self) -> None:
        self.assertEqual(parse_limit("12"), 12)

    def test_parse_limit_negative_value(self) -> None:
        with self.assertRaises(ValueError):
            parse_limit("-1")

    def test_parse_limit_invalid_string(self) -> None:
        with self.assertRaises(ValueError):
            parse_limit("abc")


if __name__ == "__main__":
    unittest.main()

