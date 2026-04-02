from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict

from app.platform.context.types import ContextBuildRequest, ContextPacket
from app.platform.history.service import HistoryService
from app.platform.memory.service import MemoryService
from app.platform.rag.document import RetrievalQuery
from app.platform.rag.service import RAGService
from app.platform.tools.builtin_note import FileNoteStore


class BaseContextProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def collect(self, request: ContextBuildRequest) -> list[ContextPacket]:
        raise NotImplementedError

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text.split()))


class HistoryContextProvider(BaseContextProvider):
    def __init__(self, history_service: HistoryService, limit: int = 8) -> None:
        self.history_service = history_service
        self.limit = limit

    @property
    def provider_id(self) -> str:
        return "history"

    def collect(self, request: ContextBuildRequest) -> list[ContextPacket]:
        packets: list[ContextPacket] = []
        history_limit = request.history_limit or self.limit
        for message in self.history_service.get_recent_history(request.session_id, request.app_id, history_limit):
            content = f"{message.role.value}: {message.content}"
            packets.append(
                ContextPacket(
                    content=content,
                    token_count=self._estimate_tokens(content),
                    relevance_score=0.6,
                    timestamp=message.timestamp,
                    metadata={"source": "history"},
                )
            )
        return packets


class MemoryContextProvider(BaseContextProvider):
    def __init__(self, memory_service: MemoryService, limit: int = 4) -> None:
        self.memory_service = memory_service
        self.limit = limit

    @property
    def provider_id(self) -> str:
        return "memory"

    def collect(self, request: ContextBuildRequest) -> list[ContextPacket]:
        memory_scope = str(request.metadata.get("memory_scope", "user")).lower()
        memory_limit = int(request.metadata.get("memory_limit", self.limit) or self.limit)
        if memory_limit <= 0:
            return []
        session_id: str | None
        user_id: str | None = request.user_id
        if memory_scope == "session":
            session_id = request.session_id
        elif memory_scope == "user":
            if user_id:
                session_id = None
            elif request.session_id:
                # Never widen a user-scoped lookup to the whole app when identity is missing.
                session_id = request.session_id
                user_id = None
            else:
                return []
        else:
            session_id = None
        memory_types = list(request.metadata.get("memory_types", []))
        min_importance = float(request.metadata.get("memory_min_importance", 0.0) or 0.0)
        type_weights = dict(request.metadata.get("memory_type_weights", {}))
        retrieval_mode = str(request.metadata.get("memory_retrieval_mode", "hybrid") or "hybrid")
        include_graph = bool(request.metadata.get("memory_include_graph", False))
        records = self.memory_service.search_relevant_memories(
            query=request.user_input,
            app_id=request.app_id,
            session_id=session_id,
            user_id=user_id,
            limit=memory_limit,
            memory_types=memory_types,
            min_importance=min_importance,
            type_weights=type_weights,
            retrieval_mode=retrieval_mode,
            include_graph=include_graph,
        )
        packets: list[ContextPacket] = []
        for record in records:
            source_kind = str(record.get("source_kind", "memory"))
            prefix = "[graph]" if source_kind == "graph_relation" or str(record.get("memory_type")) == "graph" else "[memory]"
            content = f"{prefix} {record['content']}"
            packets.append(
                ContextPacket(
                    content=content,
                    token_count=self._estimate_tokens(content),
                    relevance_score=float(record.get("score", 0.75) or 0.75),
                    metadata={
                        "source": "memory",
                        "memory_type": record.get("memory_type", "episodic"),
                        "source_kind": source_kind,
                    },
                )
            )
        return packets


class RAGContextProvider(BaseContextProvider):
    def __init__(self, rag_service: RAGService, limit: int = 4) -> None:
        self.rag_service = rag_service
        self.limit = limit

    @property
    def provider_id(self) -> str:
        return "rag"

    def collect(self, request: ContextBuildRequest) -> list[ContextPacket]:
        retrieval_limit = int(request.metadata.get("rag_limit", self.limit) or self.limit)
        if retrieval_limit <= 0:
            return []
        retrieval = self.rag_service.search(
            RetrievalQuery(
                query=request.user_input,
                app_id=request.app_id,
                session_id=request.session_id,
                user_id=request.user_id,
                agent_id=request.metadata.get("agent_id"),
                kb_ids=list(request.metadata.get("rag_kb_ids", [])),
                scope_names=request.knowledge_scopes or [request.app_id],
                limit=retrieval_limit,
                retrieval_mode=str(request.metadata.get("rag_retrieval_mode", "hybrid") or "hybrid"),
                source_types=list(request.metadata.get("rag_source_types", [])),
                include_public=bool(request.metadata.get("rag_include_public", True)),
                include_app_shared=bool(request.metadata.get("rag_include_app_shared", True)),
                include_user_private=bool(request.metadata.get("rag_include_user_private", True)),
                include_session_temporary=bool(request.metadata.get("rag_include_session_temporary", True)),
                query_rewrite_enabled=bool(request.metadata.get("rag_query_rewrite_enabled", False)),
                hyde_enabled=bool(request.metadata.get("rag_hyde_enabled", False)),
                rerank_enabled=bool(request.metadata.get("rag_rerank_enabled", False)),
                metadata={
                    "query_rewrite_mode": str(request.metadata.get("rag_query_rewrite_mode", "hybrid") or "hybrid"),
                    "mqe_variants": int(request.metadata.get("rag_mqe_variants", 4) or 4),
                    "hyde_mode": str(request.metadata.get("rag_hyde_mode", "model") or "model"),
                    "rerank_strategy": str(request.metadata.get("rag_rerank_strategy", "feature") or "feature"),
                    "rerank_top_n": int(request.metadata.get("rag_rerank_top_n", 12) or 12),
                },
            ),
            trace_id=str(request.metadata.get("trace_id", "")) or None,
        )
        packets: list[ContextPacket] = []
        for item in retrieval.items[:retrieval_limit]:
            citation = item.citation
            content = item.content
            packets.append(
                ContextPacket(
                    content=content,
                    token_count=self._estimate_tokens(content),
                    relevance_score=float(item.score),
                    metadata={
                        "source": "rag",
                        "document_id": item.document_id,
                        "chunk_id": item.chunk_id,
                        "citation": asdict(citation),
                        "visibility": item.visibility,
                        "source_uri": item.source_uri,
                        "source_type": item.source_type,
                    },
                )
            )
        return packets


class NotesContextProvider(BaseContextProvider):
    def __init__(self, note_store: FileNoteStore, limit: int = 4) -> None:
        self.note_store = note_store
        self.limit = limit

    @property
    def provider_id(self) -> str:
        return "notes"

    def collect(self, request: ContextBuildRequest) -> list[ContextPacket]:
        note_session_id = request.session_id
        if request.metadata.get("note_scope") == "app":
            note_session_id = None
        notes = self.note_store.search(
            app_id=request.app_id,
            session_id=note_session_id,
            query=request.user_input,
            limit=self.limit,
        )
        packets: list[ContextPacket] = []
        for note in notes:
            content = f"[note:{note.get('title', '')}] {note.get('content', '')}"
            packets.append(
                ContextPacket(
                    content=content,
                    token_count=self._estimate_tokens(content),
                    relevance_score=0.7,
                    metadata={"source": "notes", "note_id": note.get("note_id")},
                )
            )
        return packets
