from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass(slots=True)
class ModelRequest:
    model: str
    messages: list[dict[str, Any]]
    temperature: float = 0.2
    max_tokens: int | None = None
    stream: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModelChunk:
    text: str
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class ModelResponse:
    text: str
    raw: dict[str, Any] | None = None


class BaseModelClient(ABC):
    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError

    @abstractmethod
    def stream_generate(self, request: ModelRequest) -> Iterator[ModelChunk]:
        raise NotImplementedError
