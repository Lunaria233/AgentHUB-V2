from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class MemoryRecord:
    content: str
    app_id: str
    session_id: str
    user_id: str | None = None
    memory_id: str = ""
    memory_type: str = "episodic"
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_kind: str = "manual"
    source_confidence: float = 0.6
    canonical_key: str = ""
    checksum: str = ""
    status: str = "active"
    superseded_by: str = ""
    embedding: list[float] = field(default_factory=list)
    access_count: int = 0
    last_accessed_at: datetime | None = None
    expires_at: datetime | None = None
    archived: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class MemoryCandidate:
    content: str
    memory_type: str = "episodic"
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_kind: str = "derived"
    source_confidence: float = 0.6
    canonical_key: str = ""
    canonical_value: str = ""


@dataclass(slots=True)
class MemoryEntity:
    entity_name: str
    entity_type: str = "entity"
    confidence: float = 0.6
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryRelation:
    source: str
    relation: str
    target: str
    confidence: float = 0.6
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryQuery:
    query: str
    app_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    memory_types: list[str] = field(default_factory=list)
    type_weights: dict[str, float] = field(default_factory=dict)
    min_importance: float = 0.0
    tag_filter: list[str] = field(default_factory=list)
    include_archived: bool = False
    include_expired: bool = False
    query_embedding: list[float] = field(default_factory=list)
    retrieval_mode: str = "hybrid"
    include_graph: bool = False
    graph_limit: int = 3
    limit: int = 5
