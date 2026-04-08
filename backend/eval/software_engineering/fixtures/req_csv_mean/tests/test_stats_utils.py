from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stats_utils import mean_from_csv


class StatsUtilsTests(unittest.TestCase):
    def test_mean_from_csv_with_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "numbers.csv"
            csv_path.write_text("10\n15\nabc\n\n25\n", encoding="utf-8")
            self.assertAlmostEqual(mean_from_csv(str(csv_path)), 16.6666, places=3)

    def test_mean_from_csv_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "empty.csv"
            csv_path.write_text("", encoding="utf-8")
            self.assertEqual(mean_from_csv(str(csv_path)), 0.0)


if __name__ == "__main__":
    unittest.main()

