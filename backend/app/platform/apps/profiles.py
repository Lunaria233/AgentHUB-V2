from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ContextProfile:
    profile_id: str
    history_limit: int = 8
    max_tokens: int = 4000
    provider_order: list[str] = field(default_factory=list)
    memory_scope: str = "user"
    note_scope: str = "session"
    knowledge_scopes: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryProfile:
    profile_id: str = "default"
    schema_id: str = "default"
    enabled: bool = False
    write_policy: str = "selective"
    write_types: list[str] = field(default_factory=lambda: ["working", "episodic"])
    extraction_mode: str = "hybrid"
    retrieval_scope: str = "user"
    retrieval_limit: int = 4
    retrieval_types: list[str] = field(default_factory=lambda: ["semantic", "episodic", "working"])
    retrieval_mode: str = "hybrid"
    vector_backend: str = "auto"
    graph_backend: str = "auto"
    min_importance: float = 0.0
    working_limit: int = 20
    working_ttl_hours: int = 24
    episodic_ttl_days: int = 30
    promotion_threshold: float = 0.72
    semantic_threshold: float = 0.82
    consolidation_enabled: bool = False
    graph_enabled: bool = False
    perceptual_enabled: bool = False
    forgetting_enabled: bool = True
    conflict_strategy: str = "confidence"


@dataclass(slots=True)
class RAGProfile:
    profile_id: str = "default"
    enabled: bool = False
    scopes: list[str] = field(default_factory=list)
    retrieval_limit: int = 4
    retrieval_mode: str = "hybrid"
    citation_mode: str = "inline"
    rerank_enabled: bool = False
    rerank_strategy: str = "feature"
    rerank_top_n: int = 12
    allow_user_uploads: bool = False
    include_public: bool = True
    include_app_shared: bool = True
    include_user_private: bool = True
    include_session_temporary: bool = True
    query_rewrite_enabled: bool = False
    query_rewrite_mode: str = "hybrid"
    mqe_variants: int = 4
    hyde_enabled: bool = False
    hyde_mode: str = "model"


@dataclass(slots=True)
class MCPProfile:
    profile_id: str = "default"
    enabled: bool = False
    allowed_servers: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    allowed_resources: list[str] = field(default_factory=list)
    allowed_prompts: list[str] = field(default_factory=list)
    connection_mode: str = "shared"


@dataclass(slots=True)
class SkillBinding:
    skill_id: str
    enabled: bool = True
    stage: str = "default"
    priority: int = 100
    metadata: dict[str, str] = field(default_factory=dict)


def _default_context_profiles() -> dict[str, ContextProfile]:
    return {"default": ContextProfile(profile_id="default")}


@dataclass(slots=True)
class AppCapabilityProfiles:
    default_context_profile: str = "default"
    context_profiles: dict[str, ContextProfile] = field(default_factory=_default_context_profiles)
    memory_profile: MemoryProfile = field(default_factory=MemoryProfile)
    rag_profile: RAGProfile = field(default_factory=RAGProfile)
    mcp_profile: MCPProfile = field(default_factory=MCPProfile)
    skills: list[SkillBinding] = field(default_factory=list)

    def get_context_profile(self, profile_id: str | None = None) -> ContextProfile:
        resolved_id = profile_id or self.default_context_profile
        if resolved_id in self.context_profiles:
            return self.context_profiles[resolved_id]
        if self.context_profiles:
            return next(iter(self.context_profiles.values()))
        return ContextProfile(profile_id="default")
