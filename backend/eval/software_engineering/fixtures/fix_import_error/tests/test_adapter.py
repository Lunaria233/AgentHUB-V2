from __future__ import annotations

import unittest

from adapter import normalize_name


class AdapterTests(unittest.TestCase):
    def test_normalize_name(self) -> None:
        self.assertEqual(normalize_name("Hello Agent Hub"), "hello-agent-hub")


if __name__ == "__main__":
    unittest.main()

