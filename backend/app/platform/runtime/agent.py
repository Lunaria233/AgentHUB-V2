from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator


class BaseAgentRuntime(ABC):
    @abstractmethod
    def run(self, *, user_input: str) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def stream(self, *, user_input: str) -> Iterator[dict[str, object]]:
        raise NotImplementedError
