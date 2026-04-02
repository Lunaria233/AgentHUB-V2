from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.platform.apps.manifest import AppManifest
from app.platform.runtime.agent import BaseAgentRuntime


@dataclass(slots=True)
class RuntimeBuildContext:
    manifest: AppManifest
    session_id: str
    user_id: str | None
    model_client: Any
    model_name: str
    history_service: Any
    memory_service: Any
    rag_service: Any
    note_store: Any
    context_builder: Any
    skill_runtime: Any
    tool_registry: Any
    tool_executor: Any
    trace_service: Any
    settings: Any
    dependencies: dict[str, Any] = field(default_factory=dict)


class BaseRuntimeFactory(ABC):
    @property
    @abstractmethod
    def factory_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def create(self, build_context: RuntimeBuildContext) -> BaseAgentRuntime:
        raise NotImplementedError


class RuntimeFactoryRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, BaseRuntimeFactory] = {}

    def register(self, factory: BaseRuntimeFactory) -> None:
        self._factories[factory.factory_id] = factory

    def get(self, factory_id: str) -> BaseRuntimeFactory:
        if factory_id not in self._factories:
            raise KeyError(f"Unknown runtime factory: {factory_id}")
        return self._factories[factory_id]

    def create(self, factory_id: str, build_context: RuntimeBuildContext) -> BaseAgentRuntime:
        return self.get(factory_id).create(build_context)

    def list_factory_ids(self) -> list[str]:
        return sorted(self._factories.keys())
