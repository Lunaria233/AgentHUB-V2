from __future__ import annotations

import unittest

from weather_service import get_weather, remote_call_count, reset_state


class WeatherServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_state()

    def test_repeated_city_should_hit_cache(self) -> None:
        first = get_weather("beijing")
        second = get_weather("beijing")
        self.assertEqual(first, second)
        self.assertEqual(remote_call_count(), 1)

    def test_different_city_should_make_new_call(self) -> None:
        get_weather("beijing")
        get_weather("shanghai")
        self.assertEqual(remote_call_count(), 2)


if __name__ == "__main__":
    unittest.main()

