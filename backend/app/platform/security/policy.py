from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ToolPermission:
    allowed_tools: set[str] = field(default_factory=set)


@dataclass(slots=True)
class KnowledgeScope:
    allowed_scopes: set[str] = field(default_factory=set)


@dataclass(slots=True)
class SecurityPolicy:
    tool_permission: ToolPermission
    knowledge_scope: KnowledgeScope
