from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Weather:
    city: str
    temperature: int


_REMOTE_CALL_COUNT = 0


def reset_state() -> None:
    global _REMOTE_CALL_COUNT
    _REMOTE_CALL_COUNT = 0


def remote_call_count() -> int:
    return _REMOTE_CALL_COUNT


def _fetch_from_remote(city: str) -> Weather:
    global _REMOTE_CALL_COUNT
    _REMOTE_CALL_COUNT += 1
    return Weather(city=city, temperature=21 if city.lower() == "beijing" else 18)


def get_weather(city: str) -> dict[str, object]:
    """Expected to add in-memory cache by city."""
    weather = _fetch_from_remote(city)
    return {"city": weather.city, "temperature": weather.temperature}

