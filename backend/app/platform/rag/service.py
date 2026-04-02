from __future__ import annotations

import hashlib
import logging
import shutil
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.platform.context.types import ContextBuildRequest, ContextPacket
from app.platform.models.base import BaseModelClient, ModelRequest
from app.platform.observability.tracing import TraceService
from app.platform.rag.chunking import StructuredChunker
from app.platform.rag.document import (
    Document,
    KnowledgeScopeSummary,
    RAGAnswer,
    RAGDocumentRecord,
    RetrievalQuery,
    RetrievalResult,
)
from app.platform.rag.parsers import DocumentParser
from app.platform.rag.retriever import HybridRetriever
from app.platform.rag.store import SQLiteRAGStore
from app.platform.rag.url_loader import URLDocumentLoader


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.platform.context.builder import ContextBuilder


class RAGService:
    def __init__(
        self,
        *,
        store: SQLiteRAGStore,
        parser: DocumentParser,
        chunker: StructuredChunker,
        embedder,
        vector_index,
        model_client: BaseModelClient | None = None,
        model_name: str = "",
        trace_service: TraceService | None = None,
        uploads_root: Path | None = None,
        query_rewrite_mode: str = "hybrid",
        hyde_max_tokens: int = 220,
        mqe_variants: int = 4,
        rerank_strategy: str = "feature",
        rerank_top_n: int = 12,
        url_timeout_seconds: float = 20.0,
    ) -> None:
        self.store = store
        self.parser = parser
        self.chunker = chunker
        self.embedder = embedder
        self.vector_index = vector_index
        self.model_client = model_client
        self.model_name = model_name
        self.trace_service = trace_service
        self.uploads_root = uploads_root or Path.cwd() / "rag_uploads"
        self.uploads_root.mkdir(parents=True, exist_ok=True)
        self.url_loader = URLDocumentLoader(parser=parser, timeout_seconds=url_timeout_seconds)
        self.retriever = HybridRetriever(
            store=store,
            vector_index=vector_index,
            embedder=embedder,
            trace_service=trace_service,
            model_client=model_client,
            model_name=model_name,
            query_rewrite_mode=query_rewrite_mode,
            hyde_max_tokens=hyde_max_tokens,
            mqe_variants=mqe_variants,
            rerank_strategy=rerank_strategy,
            rerank_top_n=rerank_top_n,
        )
        self._search_cache_ttl = timedelta(seconds=20)
        self._search_cache: dict[str, tuple[datetime, RetrievalResult]] = {}

    def ingest_text(
        self,
        *,
        title: str,
        text: str,
        app_id: str,
        user_id: str | None,
        session_id: str | None,
        knowledge_target: str,
        source_type: str,
        document_id: str | None = None,
        kb_id: str | None = None,
        tenant_id: str = "default",
        agent_id: str | None = None,
        owner_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, object]:
        document = self._build_document(
            document_id=document_id,
            title=title,
            text=text,
            app_id=app_id,
            user_id=user_id,
            session_id=session_id,
            knowledge_target=knowledge_target,
            source_type=source_type,
            kb_id=kb_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            owner_id=owner_id,
            metadata=metadata,
        )
        parsed = self.parser.parse_text(text=text, metadata=document.metadata)
        chunks = self.chunker.chunk(document, parsed)
        self.store.upsert_document(document=document, chunks=chunks)
        self._upsert_vectors(document=document, chunks=chunks)
        self._invalidate_search_cache()
        self._log("rag_ingest", trace_id, {"document_id": document.document_id, "chunk_count": len(chunks), "source_type": source_type})
        return self._ingest_response(document=document, chunk_count=len(chunks))

    def ingest_file(
        self,
        *,
        title: str,
        file_path: Path,
        app_id: str,
        user_id: str | None,
        session_id: str | None,
        knowledge_target: str,
        source_type: str,
        document_id: str | None = None,
        kb_id: str | None = None,
        tenant_id: str = "default",
        agent_id: str | None = None,
        owner_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, object]:
        stored_path = self._persist_upload(file_path)
        metadata = dict(metadata or {})
        metadata["stored_path"] = str(stored_path)
        parsed = self.parser.parse_file(stored_path, metadata=metadata)
        document = self._build_document(
            document_id=document_id,
            title=title or file_path.name,
            text=parsed.text,
            app_id=app_id,
            user_id=user_id,
            session_id=session_id,
            knowledge_target=knowledge_target,
            source_type=source_type,
            kb_id=kb_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            owner_id=owner_id,
            metadata={
                **metadata,
                **parsed.metadata,
                "file_name": file_path.name,
                "mime_type": parsed.metadata.get("mime_type", ""),
            },
        )
        original_file_name = str(metadata.get("uploaded_file_name", file_path.name))
        document.file_name = original_file_name
        document.mime_type = str(parsed.metadata.get("mime_type", ""))
        document.source_uri = str(stored_path)
        chunks = self.chunker.chunk(document, parsed)
        self.store.upsert_document(document=document, chunks=chunks)
        self._upsert_vectors(document=document, chunks=chunks)
        self._invalidate_search_cache()
        self._log(
            "rag_ingest",
            trace_id,
            {"document_id": document.document_id, "chunk_count": len(chunks), "source_type": source_type, "file_name": file_path.name},
        )
        return self._ingest_response(document=document, chunk_count=len(chunks))

    def ingest_url(
        self,
        *,
        url: str,
        app_id: str,
        user_id: str | None,
        session_id: str | None,
        knowledge_target: str,
        source_type: str = "url_import",
        document_id: str | None = None,
        kb_id: str | None = None,
        tenant_id: str = "default",
        agent_id: str | None = None,
        owner_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, object]:
        fetched = self.url_loader.fetch(url)
        document = self._build_document(
            document_id=document_id,
            title=fetched.title,
            text=fetched.text,
            app_id=app_id,
            user_id=user_id,
            session_id=session_id,
            knowledge_target=knowledge_target,
            source_type=source_type,
            kb_id=kb_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            owner_id=owner_id,
            metadata={**dict(metadata or {}), **fetched.metadata},
        )
        document.source_uri = fetched.url
        chunks = self.chunker.chunk(document, fetched.parsed)
        self.store.upsert_document(document=document, chunks=chunks)
        self._upsert_vectors(document=document, chunks=chunks)
        self._invalidate_search_cache()
        self._log("rag_ingest_url", trace_id, {"document_id": document.document_id, "url": fetched.url, "chunk_count": len(chunks)})
        return self._ingest_response(document=document, chunk_count=len(chunks))

    def ingest_generated_text(
        self,
        *,
        app_id: str,
        session_id: str | None,
        user_id: str | None,
        title: str,
        text: str,
        source_type: str,
        document_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, object]:
        return self.ingest_text(
            title=title,
            text=text,
            app_id=app_id,
            user_id=user_id,
            session_id=session_id,
            knowledge_target="session_temporary",
            source_type=source_type,
            document_id=document_id,
            metadata=metadata,
            trace_id=trace_id,
        )

    def search(self, query: RetrievalQuery, *, trace_id: str | None = None) -> RetrievalResult:
        cache_key = self._search_cache_key(query)
        cached = self._get_cached_search(cache_key)
        if cached is not None:
            return cached
        scope_plan = self._build_scope_plan(
            app_id=query.app_id,
            session_id=query.session_id,
            user_id=query.user_id,
            scope_names=query.scope_names,
            explicit_kb_ids=query.kb_ids,
            include_session_temporary=query.include_session_temporary,
            include_user_private=query.include_user_private,
            include_app_shared=query.include_app_shared,
            include_public=query.include_public,
        )
        allowed_kb_ids = query.kb_ids or [kb_id for _, kb_ids in scope_plan for kb_id in kb_ids]
        if not allowed_kb_ids:
            result = RetrievalResult(query=query.query, mode=query.retrieval_mode, items=[], sources=[], debug={"expanded_queries": [query.query], "candidate_chunks": 0})
            self._cache_search(cache_key, result)
            return result
        if not self._has_accessible_documents(
            app_id=query.app_id,
            user_id=query.user_id,
            session_id=query.session_id,
            kb_ids=allowed_kb_ids,
        ):
            result = RetrievalResult(
                query=query.query,
                mode=query.retrieval_mode,
                items=[],
                sources=[],
                debug={"expanded_queries": [query.query], "candidate_chunks": 0, "skipped": "no_accessible_documents"},
            )
            self._cache_search(cache_key, result)
            return result
        candidate_chunks = self.store.list_chunks(kb_ids=allowed_kb_ids)
        candidate_chunks = [
            item
            for item in candidate_chunks
            if self._chunk_is_accessible(item, query=query, allowed_kb_ids=allowed_kb_ids)
            and (not query.source_types or str(item.get("source_type")) in set(query.source_types))
        ]
        result = self.retriever.retrieve(
            query=query,
            candidate_chunks=candidate_chunks,
            vector_should_filters=self._build_vector_should_filters(scope_plan, app_id=query.app_id, user_id=query.user_id, session_id=query.session_id),
            vector_must_filters=self._build_vector_must_filters(query),
            trace_id=trace_id,
        )
        self._cache_search(cache_key, result)
        return result

    def answer_with_sources(
        self,
        *,
        query: RetrievalQuery,
        context_builder: ContextBuilder,
        system_prompt: str,
        trace_id: str | None = None,
    ) -> RAGAnswer:
        retrieval = self.search(query, trace_id=trace_id)
        inline_packets = self._build_context_packets(retrieval.items)
        context_result = context_builder.build(
            ContextBuildRequest(
                app_id=query.app_id,
                session_id=query.session_id or "rag-answer",
                user_id=query.user_id,
                user_input=query.query,
                system_prompt=system_prompt,
                profile="rag.answer",
                max_tokens=3200,
                provider_order=[],
                inline_packets=inline_packets,
                metadata={
                    "source_aware": True,
                    "rag_limit": query.limit,
                    "rag_retrieval_mode": query.retrieval_mode,
                    "rag_query_rewrite_enabled": query.query_rewrite_enabled,
                    "rag_hyde_enabled": query.hyde_enabled,
                    "rag_rerank_enabled": query.rerank_enabled,
                    "trace_id": trace_id or "",
                },
            )
        )
        prompt = context_result.prompt
        if self.model_client is None or not self.model_name:
            fallback_answer = self._build_fallback_answer(retrieval)
            return RAGAnswer(answer=fallback_answer, sources=retrieval.sources, retrieval=retrieval, prompt=prompt, fallback_used=True)
        try:
            response = self.model_client.generate(
                ModelRequest(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=900,
                )
            )
            answer = response.text.strip()
            if not answer:
                answer = self._build_fallback_answer(retrieval)
                return RAGAnswer(answer=answer, sources=retrieval.sources, retrieval=retrieval, prompt=prompt, fallback_used=True)
            self._log(
                "rag_answer",
                trace_id,
                {
                    "query": query.query,
                    "retrieved_sources": len(retrieval.sources),
                    "fallback_used": False,
                },
            )
            return RAGAnswer(answer=answer, sources=retrieval.sources, retrieval=retrieval, prompt=prompt, fallback_used=False)
        except Exception:
            fallback_answer = self._build_fallback_answer(retrieval)
            return RAGAnswer(answer=fallback_answer, sources=retrieval.sources, retrieval=retrieval, prompt=prompt, fallback_used=True)

    def delete_document(
        self,
        *,
        document_id: str,
        app_id: str,
        user_id: str | None,
        session_id: str | None,
    ) -> bool:
        record = self.store.get_document(document_id)
        if record is None:
            return False
        if not self._document_is_deletable(record, app_id=app_id, user_id=user_id, session_id=session_id):
            return False
        deleted = self.store.delete_document(document_id)
        if deleted and self.vector_index is not None and getattr(self.vector_index, "enabled", False):
            self.vector_index.delete_document(document_id)
        if deleted:
            self._invalidate_search_cache()
        source_uri = str(record.get("source_uri", "") or "")
        if source_uri and not source_uri.startswith(("http://", "https://")):
            path = Path(source_uri)
            if path.exists():
                path.unlink(missing_ok=True)
        return deleted

    def rebuild_index(self, *, app_id: str | None = None, kb_id: str | None = None) -> dict[str, object]:
        documents = self.store.list_documents(kb_ids=[kb_id] if kb_id else None, app_id=app_id)
        rebuilt = 0
        chunk_total = 0
        for record in documents:
            document = Document(
                document_id=str(record["document_id"]),
                title=str(record["title"]),
                text=str(record["raw_text"]),
                metadata=dict(record["metadata"]),
                tenant_id=str(record["tenant_id"]),
                user_id=record["user_id"],
                app_id=str(record["app_id"]),
                agent_id=record["agent_id"],
                session_id=record["session_id"],
                kb_id=str(record["kb_id"]),
                owner_id=str(record["owner_id"]),
                visibility=str(record["visibility"]),
                source_type=str(record["source_type"]),
                is_temporary=bool(record["is_temporary"]),
                file_name=str(record.get("file_name") or ""),
                mime_type=str(record.get("mime_type") or ""),
                source_uri=str(record.get("source_uri") or ""),
            )
            parsed = self.parser.parse_text(text=document.text, metadata=document.metadata)
            chunks = self.chunker.chunk(document, parsed)
            self.store.upsert_document(document=document, chunks=chunks)
            self._upsert_vectors(document=document, chunks=chunks)
            rebuilt += 1
            chunk_total += len(chunks)
        if rebuilt:
            self._invalidate_search_cache()
        return {"rebuilt_documents": rebuilt, "rebuilt_chunks": chunk_total}

    def list_knowledge_scopes(
        self,
        *,
        app_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[KnowledgeScopeSummary]:
        return self.store.list_knowledge_scopes(app_id=app_id, user_id=user_id, session_id=session_id)

    def list_documents(
        self,
        *,
        app_id: str,
        user_id: str | None = None,
        session_id: str | None = None,
        visibility: list[str] | None = None,
        source_types: list[str] | None = None,
        kb_ids: list[str] | None = None,
        limit: int = 100,
    ) -> list[RAGDocumentRecord]:
        documents = self.store.list_documents(
            app_id=app_id,
            user_id=user_id,
            session_id=session_id,
            visibility=visibility,
            source_types=source_types,
            kb_ids=kb_ids,
            limit=limit,
        )
        return [
            self.store.to_record(item)
            for item in documents
            if self._document_is_accessible(item, app_id=app_id, user_id=user_id, session_id=session_id)
        ]

    def status(self) -> dict[str, Any]:
        summary = self.store.summarize()
        vector_info = (
            self.vector_index.collection_info()
            if self.vector_index is not None and getattr(self.vector_index, "enabled", False)
            else {"enabled": False, "collection": "", "base_url": ""}
        )
        return {
            "backend": "platform_rag",
            "retriever": {
                "default_mode": self.retriever.enhancer.default_mode,
                "rerank_strategy": self.reranker_strategy,
            },
            "embedding": {
                "provider": self.embedder.__class__.__name__,
                "configured_model": getattr(self.embedder, "model", ""),
            },
            "vector_backend": vector_info,
            "documents": summary,
            "model": {
                "configured_model": self.model_name,
                "available": bool(self.model_client and self.model_name),
            },
            "features": {
                "url_import": True,
                "rerank": True,
                "mqe": True,
                "hyde": True,
                "structured_sources": True,
            },
        }

    @property
    def reranker_strategy(self) -> str:
        return self.retriever.reranker.strategy

    def retrieve(self, *, scope: str, query: str, limit: int = 5) -> list[dict[str, object]]:
        result = self.search(
            RetrievalQuery(
                query=query,
                app_id=scope,
                scope_names=[scope],
                limit=limit,
                retrieval_mode="hybrid",
                include_public=False,
                include_user_private=False,
                include_session_temporary=False,
            )
        )
        return [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "title": item.title,
                "content": item.content,
                "preview": item.preview,
                "page_or_section": item.page_or_section,
                "score": item.score,
                "visibility": item.visibility,
                "source_uri": item.source_uri,
            }
            for item in result.items
        ]

    def _has_accessible_documents(
        self,
        *,
        app_id: str,
        user_id: str | None,
        session_id: str | None,
        kb_ids: list[str],
    ) -> bool:
        documents = self.store.list_documents(kb_ids=kb_ids, limit=24)
        for record in documents:
            if self._document_is_accessible(record, app_id=app_id, user_id=user_id, session_id=session_id):
                return True
        return False

    def _persist_upload(self, file_path: Path) -> Path:
        unique_name = f"{uuid4().hex}_{file_path.name}"
        destination = self.uploads_root / unique_name
        shutil.copy2(file_path, destination)
        return destination

    def _search_cache_key(self, query: RetrievalQuery) -> str:
        return hashlib.sha1(
            repr(
                (
                    query.query,
                    query.app_id,
                    query.session_id,
                    query.user_id,
                    query.agent_id,
                    query.tenant_id,
                    tuple(query.kb_ids),
                    tuple(query.scope_names),
                    query.limit,
                    query.retrieval_mode,
                    tuple(query.source_types),
                    query.include_public,
                    query.include_app_shared,
                    query.include_user_private,
                    query.include_session_temporary,
                    query.query_rewrite_enabled,
                    query.hyde_enabled,
                    query.rerank_enabled,
                    tuple(sorted(query.metadata.items())),
                )
            ).encode("utf-8")
        ).hexdigest()

    def _get_cached_search(self, cache_key: str) -> RetrievalResult | None:
        cached = self._search_cache.get(cache_key)
        if cached is None:
            return None
        expires_at, result = cached
        if expires_at <= datetime.now(timezone.utc):
            self._search_cache.pop(cache_key, None)
            return None
        return result

    def _cache_search(self, cache_key: str, result: RetrievalResult) -> None:
        self._search_cache[cache_key] = (datetime.now(timezone.utc) + self._search_cache_ttl, result)

    def _invalidate_search_cache(self) -> None:
        self._search_cache.clear()

    def _upsert_vectors(self, *, document: Document, chunks: list) -> None:
        if self.vector_index is None or not getattr(self.vector_index, "enabled", False):
            return
        vectors: dict[str, list[float]] = {}
        for chunk in chunks:
            try:
                vectors[chunk.chunk_id] = self.embedder.encode(f"{chunk.title}\n{chunk.content}")
            except Exception as exc:
                logger.warning("RAG embedding failed for chunk %s: %s", chunk.chunk_id, exc)
                return
        try:
            self.vector_index.upsert_chunks(document=document, chunks=chunks, vectors=vectors)
        except Exception as exc:
            logger.warning("RAG vector upsert failed for document %s: %s", document.document_id, exc)

    def _build_document(
        self,
        *,
        document_id: str | None,
        title: str,
        text: str,
        app_id: str,
        user_id: str | None,
        session_id: str | None,
        knowledge_target: str,
        source_type: str,
        kb_id: str | None,
        tenant_id: str,
        agent_id: str | None,
        owner_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> Document:
        resolved_visibility, is_temporary = self._target_to_visibility(knowledge_target)
        resolved_kb_id = kb_id or self._default_kb_id(
            target=knowledge_target,
            app_id=app_id,
            user_id=user_id,
            session_id=session_id,
        )
        if resolved_visibility == "session_temporary" and not session_id:
            raise ValueError("session_temporary knowledge requires session_id")
        if resolved_visibility == "user_private" and not user_id:
            raise ValueError("user_private knowledge requires user_id")
        resolved_owner = owner_id or (user_id or app_id or "system")
        raw_metadata = dict(metadata or {})
        raw_metadata.setdefault("knowledge_target", knowledge_target)
        raw_metadata.setdefault("kb_id", resolved_kb_id)
        return Document(
            document_id=document_id or self._make_document_id(title=title, text=text),
            title=title.strip() or "Untitled knowledge document",
            text=text.strip(),
            metadata=raw_metadata,
            tenant_id=tenant_id,
            user_id=user_id,
            app_id=app_id,
            agent_id=agent_id,
            session_id=session_id,
            kb_id=resolved_kb_id,
            owner_id=resolved_owner,
            visibility=resolved_visibility,
            source_type=source_type,
            is_temporary=is_temporary,
        )

    @staticmethod
    def _make_document_id(*, title: str, text: str) -> str:
        digest = hashlib.sha256(f"{title}\n{text}".encode("utf-8")).hexdigest()[:16]
        return f"doc_{digest}"

    @staticmethod
    def _target_to_visibility(target: str) -> tuple[str, bool]:
        mapping = {
            "session_temporary": ("session_temporary", True),
            "user_private": ("user_private", False),
            "app_shared": ("app_shared", False),
            "system_public": ("system_public", False),
        }
        if target not in mapping:
            raise ValueError(f"Unsupported knowledge target: {target}")
        return mapping[target]

    @staticmethod
    def _default_kb_id(*, target: str, app_id: str, user_id: str | None, session_id: str | None) -> str:
        if target == "session_temporary":
            return f"session:{app_id}:{session_id or 'unknown'}"
        if target == "user_private":
            return f"user:{app_id}:{user_id or 'anonymous'}:default"
        if target == "app_shared":
            return f"app:{app_id}:default"
        return "public:default"

    def _build_scope_plan(
        self,
        *,
        app_id: str,
        session_id: str | None,
        user_id: str | None,
        scope_names: list[str],
        explicit_kb_ids: list[str],
        include_session_temporary: bool,
        include_user_private: bool,
        include_app_shared: bool,
        include_public: bool,
    ) -> list[tuple[str, list[str]]]:
        app_scope_names = scope_names or [app_id]
        grouped: dict[str, list[str]] = {}

        def add(kind: str, kb_ids: list[str]) -> None:
            bucket = grouped.setdefault(kind, [])
            for kb_id in kb_ids:
                if kb_id and kb_id not in bucket:
                    bucket.append(kb_id)

        if include_session_temporary and session_id:
            add("session_temporary", [self._default_kb_id(target="session_temporary", app_id=app_id, user_id=user_id, session_id=session_id)])
        if include_user_private and user_id:
            add("user_private", [self._default_kb_id(target="user_private", app_id=app_id, user_id=user_id, session_id=session_id)])
        if include_app_shared:
            add("app_shared", [f"app:{scope_name}:default" for scope_name in app_scope_names])
        if include_public:
            add("system_public", ["public:default"])
        for kb_id in explicit_kb_ids:
            if kb_id.startswith("session:") and include_session_temporary:
                add("session_temporary", [kb_id])
            elif kb_id.startswith("user:") and include_user_private:
                add("user_private", [kb_id])
            elif kb_id.startswith("app:") and include_app_shared:
                add("app_shared", [kb_id])
            elif kb_id.startswith("public:") and include_public:
                add("system_public", [kb_id])
        ordered_scope_names = ["session_temporary", "user_private", "app_shared", "system_public"]
        return [(kind, grouped[kind]) for kind in ordered_scope_names if kind in grouped]

    @staticmethod
    def _chunk_is_accessible(chunk: dict[str, Any], *, query: RetrievalQuery, allowed_kb_ids: list[str]) -> bool:
        visibility = str(chunk.get("visibility", ""))
        kb_id = str(chunk.get("kb_id", ""))
        if kb_id not in allowed_kb_ids:
            return False
        if visibility == "session_temporary":
            return bool(query.session_id and chunk.get("session_id") == query.session_id and chunk.get("app_id") == query.app_id)
        if visibility == "user_private":
            return bool(query.user_id and chunk.get("user_id") == query.user_id and chunk.get("app_id") == query.app_id)
        if visibility == "app_shared":
            return chunk.get("app_id") == query.app_id
        if visibility == "system_public":
            return True
        return False

    @staticmethod
    def _build_vector_should_filters(
        scope_plan: list[tuple[str, list[str]]],
        *,
        app_id: str,
        user_id: str | None,
        session_id: str | None,
    ) -> list[dict[str, Any]]:
        should_filters: list[dict[str, Any]] = []
        for visibility, kb_ids in scope_plan:
            must: list[dict[str, Any]] = [
                {"key": "visibility", "match": {"value": visibility}},
                {"key": "kb_id", "match": {"any": kb_ids}},
            ]
            if visibility == "session_temporary" and session_id:
                must.extend(
                    [
                        {"key": "app_id", "match": {"value": app_id}},
                        {"key": "session_id", "match": {"value": session_id}},
                    ]
                )
            elif visibility == "user_private" and user_id:
                must.extend(
                    [
                        {"key": "app_id", "match": {"value": app_id}},
                        {"key": "user_id", "match": {"value": user_id}},
                    ]
                )
            elif visibility == "app_shared":
                must.append({"key": "app_id", "match": {"value": app_id}})
            should_filters.append({"must": must})
        return should_filters

    @staticmethod
    def _build_vector_must_filters(query: RetrievalQuery) -> list[dict[str, Any]]:
        must_filters = [{"key": "tenant_id", "match": {"value": query.tenant_id}}]
        if query.agent_id:
            must_filters.append({"key": "agent_id", "match": {"value": query.agent_id}})
        if query.source_types:
            must_filters.append({"key": "source_type", "match": {"any": query.source_types}})
        if query.kb_ids:
            must_filters.append({"key": "kb_id", "match": {"any": query.kb_ids}})
        return must_filters

    @staticmethod
    def _build_context_packets(items: list) -> list[ContextPacket]:
        packets: list[ContextPacket] = []
        for item in items:
            citation = item.citation
            content = item.content.strip()
            packets.append(
                ContextPacket(
                    content=content,
                    token_count=max(1, len(content.split())),
                    relevance_score=item.score,
                    metadata={"source": "rag", "citation": asdict(citation), "chunk_id": citation.chunk_id},
                )
            )
        return packets

    @staticmethod
    def _build_fallback_answer(retrieval: RetrievalResult) -> str:
        if not retrieval.items:
            return "No grounded answer could be generated because no relevant knowledge was retrieved."
        lines = ["Grounded summary based on retrieved knowledge:"]
        for index, item in enumerate(retrieval.items[:4], start=1):
            lines.append(f"[S{index}] {item.preview}")
        return "\n".join(lines)

    @staticmethod
    def _document_is_deletable(record: dict[str, Any], *, app_id: str, user_id: str | None, session_id: str | None) -> bool:
        visibility = str(record.get("visibility", ""))
        if visibility == "session_temporary":
            return record.get("app_id") == app_id and record.get("session_id") == session_id
        if visibility == "user_private":
            return record.get("app_id") == app_id and record.get("user_id") == user_id
        if visibility == "app_shared":
            return record.get("app_id") == app_id
        return False

    @staticmethod
    def _document_is_accessible(record: dict[str, Any], *, app_id: str, user_id: str | None, session_id: str | None) -> bool:
        visibility = str(record.get("visibility", ""))
        if visibility == "session_temporary":
            return bool(session_id and record.get("session_id") == session_id and record.get("app_id") == app_id)
        if visibility == "user_private":
            return bool(user_id and record.get("user_id") == user_id and record.get("app_id") == app_id)
        if visibility == "app_shared":
            return record.get("app_id") == app_id
        if visibility == "system_public":
            return True
        return False

    def _ingest_response(self, *, document: Document, chunk_count: int) -> dict[str, object]:
        return {
            "document_id": document.document_id,
            "kb_id": document.kb_id,
            "chunk_count": chunk_count,
            "visibility": document.visibility,
            "is_temporary": document.is_temporary,
            "title": document.title,
            "source_uri": document.source_uri,
        }

    def _log(self, event_type: str, trace_id: str | None, payload: dict[str, Any]) -> None:
        if self.trace_service is not None and trace_id:
            self.trace_service.log_event(trace_id=trace_id, event_type=event_type, payload=payload)
