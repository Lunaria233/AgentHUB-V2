from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolParameter:
    name: str
    description: str
    required: bool = True
    param_type: str = "string"


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)


@dataclass(slots=True)
class ToolContext:
    app_id: str
    session_id: str
    user_id: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def parameters(self) -> list[ToolParameter]:
        raise NotImplementedError

    @abstractmethod
    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        raise NotImplementedError

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters())
