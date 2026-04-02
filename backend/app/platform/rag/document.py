from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ParsedSegment:
    order: int
    content: str
    page_or_section: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedDocument:
    text: str
    segments: list[ParsedSegment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Document:
    document_id: str
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = "default"
    user_id: str | None = None
    app_id: str = ""
    agent_id: str | None = None
    session_id: str | None = None
    kb_id: str = ""
    owner_id: str = ""
    visibility: str = "user_private"
    source_type: str = "text_input"
    is_temporary: bool = False
    file_name: str = ""
    mime_type: str = ""
    source_uri: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    kb_id: str
    chunk_index: int
    title: str
    content: str
    preview: str
    page_or_section: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Citation:
    doc_id: str
    title: str
    chunk_id: str
    page_or_section: str
    score: float
    preview: str
    visibility: str
    source_uri: str = ""
    source_type: str = ""


@dataclass(slots=True)
class RAGSearchHit:
    chunk_id: str
    document_id: str
    title: str
    content: str
    preview: str
    page_or_section: str
    score: float
    lexical_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: float = 0.0
    visibility: str = "user_private"
    source_type: str = "text_input"
    kb_id: str = ""
    source_uri: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def citation(self) -> Citation:
        return Citation(
            doc_id=self.document_id,
            title=self.title,
            chunk_id=self.chunk_id,
            page_or_section=self.page_or_section,
            score=self.score,
            preview=self.preview,
            visibility=self.visibility,
            source_uri=self.source_uri,
            source_type=self.source_type,
        )


@dataclass(slots=True)
class RetrievalQuery:
    query: str
    app_id: str
    session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    tenant_id: str = "default"
    kb_ids: list[str] = field(default_factory=list)
    scope_names: list[str] = field(default_factory=list)
    limit: int = 5
    retrieval_mode: str = "hybrid"
    source_types: list[str] = field(default_factory=list)
    include_public: bool = True
    include_app_shared: bool = True
    include_user_private: bool = True
    include_session_temporary: bool = True
    query_rewrite_enabled: bool = False
    hyde_enabled: bool = False
    rerank_enabled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalResult:
    query: str
    mode: str
    items: list[RAGSearchHit]
    sources: list[Citation]
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RAGAnswer:
    answer: str
    sources: list[Citation]
    retrieval: RetrievalResult
    prompt: str
    fallback_used: bool = False


@dataclass(slots=True)
class KnowledgeScopeSummary:
    kb_id: str
    visibility: str
    app_id: str
    user_id: str | None
    session_id: str | None
    owner_id: str
    is_temporary: bool
    document_count: int


@dataclass(slots=True)
class RAGDocumentRecord:
    document_id: str
    kb_id: str
    title: str
    source_type: str
    visibility: str
    tenant_id: str
    user_id: str | None
    app_id: str
    agent_id: str | None
    session_id: str | None
    owner_id: str
    is_temporary: bool
    file_name: str
    mime_type: str
    source_uri: str
    metadata: dict[str, Any]
    chunk_count: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class RAGEvalCaseResult:
    case_id: str
    description: str
    mode: str
    recall_at_k: float
    precision_at_k: float
    mrr: float
    leakage_rate: float
    source_coverage: float
    expected: list[str] = field(default_factory=list)
    retrieved: list[str] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RAGEvalSummary:
    average_recall_at_k: float
    average_precision_at_k: float
    average_mrr: float
    average_leakage_rate: float
    average_source_coverage: float
    cases: list[RAGEvalCaseResult] = field(default_factory=list)
