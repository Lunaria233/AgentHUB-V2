from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class ContextPacket:
    content: str
    token_count: int
    relevance_score: float = 0.5
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextSection:
    title: str
    content: str


@dataclass(slots=True)
class ContextBuildRequest:
    app_id: str
    session_id: str
    user_input: str
    user_id: str | None = None
    system_prompt: str = ""
    profile: str = "default"
    max_tokens: int = 4000
    history_limit: int | None = None
    knowledge_scopes: list[str] = field(default_factory=list)
    provider_order: list[str] = field(default_factory=list)
    inline_packets: list[ContextPacket] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextBuildResult:
    sections: list[ContextSection]
    packets: list[ContextPacket]
    prompt: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
