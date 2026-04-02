from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BaseCapabilityContext:
    app_id: str
    session_id: str
    user_id: str | None
    stage: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseCapabilityPlugin(ABC):
    @property
    @abstractmethod
    def capability_name(self) -> str:
        raise NotImplementedError


class BaseMemoryManager(BaseCapabilityPlugin):
    @abstractmethod
    def write(self, context: BaseCapabilityContext, *, content: str, metadata: dict[str, Any] | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, context: BaseCapabilityContext, *, query: str, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError


class BaseRAGService(BaseCapabilityPlugin):
    @abstractmethod
    def ingest(self, *, documents: list[dict[str, Any]], target: str, metadata: dict[str, Any] | None = None) -> int:
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, *, query: str, limit: int, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def answer(self, *, query: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError


class BaseMCPGateway(BaseCapabilityPlugin):
    @abstractmethod
    def list_tools(self, context: BaseCapabilityContext) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def call_tool(self, context: BaseCapabilityContext, *, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class BaseSkillRuntime(BaseCapabilityPlugin):
    @abstractmethod
    def resolve(self, context: BaseCapabilityContext, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def apply(self, context: BaseCapabilityContext, *, prompt_fragments: list[str], **kwargs: Any) -> list[str]:
        raise NotImplementedError
