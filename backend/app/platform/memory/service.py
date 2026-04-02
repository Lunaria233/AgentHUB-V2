from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging

from app.config import MemorySettings
from app.platform.apps.profiles import MemoryProfile
from app.platform.memory.base import MemoryCandidate, MemoryEntity, MemoryQuery, MemoryRecord, MemoryRelation
from app.platform.memory.embedding import BaseMemoryEmbedder, LocalHashEmbedder
from app.platform.memory.extractor import ExtractionResult, MemoryExtractor
from app.platform.memory.graph_backends import Neo4jGraphMemoryStore
from app.platform.memory.schemas import MemorySchemaRegistry
from app.platform.memory.store import SQLiteMemoryStore
from app.platform.memory.vector_index import QdrantMemoryIndex
from app.platform.models.base import BaseModelClient


DEFAULT_TYPE_WEIGHTS = {
    "working": 0.04,
    "episodic": 0.1,
    "semantic": 0.16,
    "perceptual": 0.08,
    "graph": 0.14,
}

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(
        self,
        store: SQLiteMemoryStore,
        *,
        settings: MemorySettings | None = None,
        model_client: BaseModelClient | None = None,
        model_name: str = "",
        embedder: BaseMemoryEmbedder | None = None,
        vector_index: QdrantMemoryIndex | None = None,
        graph_backend: Neo4jGraphMemoryStore | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.extractor = MemoryExtractor(model_client=model_client, model_name=model_name)
        self.embedder = embedder or LocalHashEmbedder()
        self.vector_index = vector_index
        self.graph_backend = graph_backend
        self.schema_registry = MemorySchemaRegistry()

    def remember_interaction(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        content: str,
        user_message: str | None = None,
        assistant_message: str | None = None,
        profile: MemoryProfile | None = None,
        importance: float = 0.45,
    ) -> dict[str, int]:
        resolved_profile = self._resolve_profile(profile)
        now = datetime.now(timezone.utc)
        stored = 0
        if "working" in resolved_profile.write_types:
            self._persist_record(
                MemoryRecord(
                    app_id=app_id,
                    session_id=session_id,
                    user_id=user_id,
                    content=content,
                    memory_type="working",
                    importance=min(0.95, importance),
                    tags=["interaction"],
                    source_kind="interaction_raw",
                    source_confidence=0.65,
                    expires_at=now + timedelta(hours=resolved_profile.working_ttl_hours),
                ),
                conflict_strategy=resolved_profile.conflict_strategy,
            )
            stored += 1
        if "episodic" in resolved_profile.write_types:
            self._persist_record(
                MemoryRecord(
                    app_id=app_id,
                    session_id=session_id,
                    user_id=user_id,
                    content=content,
                    memory_type="episodic",
                    importance=min(0.95, max(importance, 0.55)),
                    tags=["interaction"],
                    source_kind="interaction_raw",
                    source_confidence=0.68,
                    expires_at=now + timedelta(days=resolved_profile.episodic_ttl_days),
                ),
                conflict_strategy=resolved_profile.conflict_strategy,
            )
            stored += 1

        extracted = (
            self.extractor.extract_interaction(
                user_input=user_message or content,
                assistant_output=assistant_message or "",
                extraction_mode=resolved_profile.extraction_mode,
                schema_id=resolved_profile.schema_id,
            )
            if resolved_profile.extraction_mode != "disabled"
            else ExtractionResult()
        )
        extracted_count = self._persist_extraction_result(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            profile=resolved_profile,
            extraction=extracted,
        )
        return {"stored": stored, "extracted": extracted_count}

    def remember_working_memory(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        content: str,
        importance: float = 0.5,
        tags: list[str] | None = None,
        profile: MemoryProfile | None = None,
        source_kind: str = "working_observation",
    ) -> str:
        resolved_profile = self._resolve_profile(profile)
        memory_id = self._persist_record(
            MemoryRecord(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                content=content,
                memory_type="working",
                importance=importance,
                tags=tags or [],
                source_kind=source_kind,
                source_confidence=0.7,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=resolved_profile.working_ttl_hours),
                metadata={"profile_id": resolved_profile.profile_id},
            ),
            conflict_strategy=resolved_profile.conflict_strategy,
        )
        if resolved_profile.graph_enabled:
            self._persist_extraction_result(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                profile=resolved_profile,
                extraction=self.extractor.extract_text(
                    text=content,
                    extraction_mode=resolved_profile.extraction_mode,
                    source_kind=source_kind,
                    schema_id=resolved_profile.schema_id,
                ),
                anchor_memory_id=memory_id,
                persist_candidates=False,
            )
        return memory_id

    def remember_fact(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        content: str,
        importance: float = 0.8,
        tags: list[str] | None = None,
        profile: MemoryProfile | None = None,
        source_kind: str = "fact",
    ) -> str:
        resolved_profile = self._resolve_profile(profile)
        candidate = MemoryCandidate(
            content=content,
            memory_type="semantic",
            importance=importance,
            tags=tags or [],
            source_kind=source_kind,
            source_confidence=0.84,
            canonical_key=self._derive_canonical_key(content, source_kind, tags or []),
            canonical_value=content,
        )
        memory_id = self._persist_candidate(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            candidate=candidate,
            profile=resolved_profile,
        )
        if resolved_profile.graph_enabled:
            self._persist_extraction_result(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                profile=resolved_profile,
                extraction=self.extractor.extract_text(
                    text=content,
                    extraction_mode=resolved_profile.extraction_mode,
                    source_kind=source_kind,
                    schema_id=resolved_profile.schema_id,
                ),
                anchor_memory_id=memory_id,
                persist_candidates=False,
            )
        return memory_id

    def remember_preference(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        content: str,
        importance: float = 0.88,
        tags: list[str] | None = None,
        profile: MemoryProfile | None = None,
    ) -> str:
        resolved_profile = self._resolve_profile(profile)
        candidate = MemoryCandidate(
            content=content,
            memory_type="semantic",
            importance=importance,
            tags=(tags or []) + ["preference"],
            source_kind="preference",
            source_confidence=0.9,
            canonical_key=self._derive_canonical_key(content, "preference", (tags or []) + ["preference"]),
            canonical_value=content,
        )
        memory_id = self._persist_candidate(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            candidate=candidate,
            profile=resolved_profile,
        )
        if resolved_profile.graph_enabled:
            self._persist_graph(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                entities=[MemoryEntity(entity_name=content, entity_type="preference_target", confidence=0.85)],
                relations=[MemoryRelation(source="user", relation="prefers", target=content, confidence=0.88)],
                memory_id=memory_id,
            )
        return memory_id

    def remember_document(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        title: str,
        content: str,
        profile: MemoryProfile | None = None,
        tags: list[str] | None = None,
        source_path: str = "",
    ) -> dict[str, int]:
        resolved_profile = self._resolve_profile(profile)
        stored = 0
        if resolved_profile.perceptual_enabled:
            excerpt = f"{title}\n\n{content[:1200]}".strip()
            self._persist_candidate(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                candidate=MemoryCandidate(
                    content=excerpt,
                    memory_type="perceptual",
                    importance=0.68,
                    tags=(tags or []) + ["document", "perceptual"],
                    source_kind="document_snapshot",
                    source_confidence=0.78,
                    canonical_key=f"document:{self._slug(title) or self._slug(excerpt)}",
                    canonical_value=title or excerpt,
                    metadata={"source_path": source_path} if source_path else {},
                ),
                profile=resolved_profile,
            )
            stored += 1

        extraction = self.extractor.extract_document(
            title=title,
            content=content,
            extraction_mode=resolved_profile.extraction_mode,
            schema_id=resolved_profile.schema_id,
        )
        extracted = self._persist_extraction_result(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            profile=resolved_profile,
            extraction=extraction,
        )
        return {"stored": stored, "extracted": extracted}

    def search_relevant_memories(
        self,
        *,
        query: str,
        app_id: str | None,
        session_id: str | None,
        user_id: str | None,
        limit: int = 5,
        memory_types: list[str] | None = None,
        min_importance: float = 0.0,
        type_weights: dict[str, float] | None = None,
        tag_filter: list[str] | None = None,
        retrieval_mode: str = "hybrid",
        include_graph: bool = False,
        graph_limit: int = 3,
    ) -> list[dict[str, object]]:
        resolved_weights = dict(DEFAULT_TYPE_WEIGHTS)
        if type_weights:
            resolved_weights.update(type_weights)
        query_embedding = self._encode(query) if retrieval_mode.lower() in {"vector", "hybrid"} else []
        records = self.store.search_records(
            MemoryQuery(
                query=query,
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                memory_types=memory_types or [],
                type_weights=resolved_weights,
                min_importance=min_importance,
                tag_filter=tag_filter or [],
                query_embedding=query_embedding,
                retrieval_mode=retrieval_mode,
                include_graph=include_graph,
                graph_limit=graph_limit,
                limit=limit,
            )
        )
        combined = list(records)
        if self.vector_index and self.vector_index.enabled and query_embedding and retrieval_mode.lower() in {"vector", "hybrid"}:
            try:
                qdrant_hits = self.vector_index.search(
                    query_vector=query_embedding,
                    limit=limit,
                    app_id=app_id,
                    session_id=session_id,
                    user_id=user_id,
                    memory_types=memory_types,
                )
            except Exception as exc:
                logger.warning("Vector search failed for app_id=%s session_id=%s: %s", app_id, session_id, exc)
            else:
                combined.extend(self._resolve_external_vector_hits(qdrant_hits))
        if include_graph and app_id:
            combined.extend(
                self.store.search_graph(
                    query=query,
                    app_id=app_id,
                    session_id=session_id,
                    user_id=user_id,
                    limit=graph_limit,
                )
            )
            if self.graph_backend and self.graph_backend.enabled:
                try:
                    combined.extend(
                        self.graph_backend.search(
                            query=query,
                            app_id=app_id,
                            session_id=session_id,
                            user_id=user_id,
                            limit=graph_limit,
                        )
                    )
                except Exception as exc:
                    logger.warning("Graph search failed for app_id=%s session_id=%s: %s", app_id, session_id, exc)
        deduped: dict[str, dict[str, object]] = {}
        anonymous: list[dict[str, object]] = []
        for item in combined:
            memory_id = str(item.get("memory_id", "") or "")
            if not memory_id:
                anonymous.append(item)
                continue
            current = deduped.get(memory_id)
            if current is None or float(item.get("score", 0.0)) > float(current.get("score", 0.0)):
                deduped[memory_id] = item
        ranked = list(deduped.values()) + anonymous
        ranked.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return ranked[:limit]

    def consolidate_memory(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        profile: MemoryProfile,
    ) -> dict[str, int]:
        return {
            "promoted_to_episodic": self._promote_working_to_episodic(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                profile=profile,
            ),
            "promoted_to_semantic": self._promote_episodic_to_semantic(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                profile=profile,
            ),
            "clustered_semantic": self._synthesize_semantic_clusters(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                profile=profile,
            ),
            "merged_duplicates": self._merge_duplicates(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
            ),
            "trimmed_working": self.store.prune_memory_type(
                app_id=app_id,
                session_id=session_id,
                memory_type="working",
                keep=profile.working_limit,
            ),
            "forgotten": self.store.apply_forgetting_policy(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
            ) if profile.forgetting_enabled else 0,
            "expired_removed": self.store.delete_expired_records(),
        }

    def summarize_memory(self, *, app_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        return self.store.summary(app_id=app_id, user_id=user_id)

    def list_memories(
        self,
        *,
        app_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        memory_types: list[str] | None = None,
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        return self.store.list_records(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            memory_types=memory_types,
            include_archived=include_archived,
            limit=limit,
        )

    def _promote_working_to_episodic(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        profile: MemoryProfile,
    ) -> int:
        candidates = self.store.list_records(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            memory_types=["working"],
            include_archived=False,
            status="active",
            limit=500,
        )
        promoted_ids: list[str] = []
        count = 0
        for item in candidates:
            if float(item["importance"]) < profile.promotion_threshold:
                continue
            metadata = dict(item["metadata"])
            if metadata.get("promoted_to_episodic"):
                continue
            self._persist_record(
                MemoryRecord(
                    app_id=app_id,
                    session_id=session_id,
                    user_id=user_id,
                    content=str(item["content"]),
                    memory_type="episodic",
                    importance=min(0.98, float(item["importance"]) + 0.08),
                    tags=list(item["tags"]),
                    metadata={
                        **metadata,
                        "promoted_from": item["memory_id"],
                        "promoted_from_type": "working",
                        "profile_id": profile.profile_id,
                    },
                    source_kind="consolidated",
                    source_confidence=max(0.7, float(item.get("source_confidence", 0.0))),
                    canonical_key=str(item.get("canonical_key", "")),
                    expires_at=datetime.now(timezone.utc) + timedelta(days=profile.episodic_ttl_days),
                ),
                conflict_strategy=profile.conflict_strategy,
            )
            promoted_ids.append(str(item["memory_id"]))
            count += 1
        if promoted_ids:
            self.store.archive_records(promoted_ids)
        return count

    def _promote_episodic_to_semantic(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        profile: MemoryProfile,
    ) -> int:
        candidates = self.store.list_records(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            memory_types=["episodic"],
            include_archived=False,
            status="active",
            limit=500,
        )
        promoted_ids: list[str] = []
        count = 0
        for item in candidates:
            if float(item["importance"]) < profile.semantic_threshold:
                continue
            metadata = dict(item["metadata"])
            if metadata.get("promoted_to_semantic"):
                continue
            self._persist_record(
                MemoryRecord(
                    app_id=app_id,
                    session_id=session_id,
                    user_id=user_id,
                    content=str(item["content"]),
                    memory_type="semantic",
                    importance=min(0.99, float(item["importance"]) + 0.05),
                    tags=list(item["tags"]),
                    metadata={
                        **metadata,
                        "promoted_from": item["memory_id"],
                        "promoted_from_type": "episodic",
                        "profile_id": profile.profile_id,
                    },
                    source_kind="consolidated",
                    source_confidence=max(0.72, float(item.get("source_confidence", 0.0))),
                    canonical_key=str(item.get("canonical_key", "")),
                ),
                conflict_strategy=profile.conflict_strategy,
            )
            promoted_ids.append(str(item["memory_id"]))
            count += 1
        if promoted_ids:
            self.store.archive_records(promoted_ids)
        return count

    def _synthesize_semantic_clusters(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        profile: MemoryProfile,
    ) -> int:
        episodic = self.store.list_records(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            memory_types=["episodic"],
            include_archived=False,
            status="active",
            limit=500,
        )
        groups: dict[str, list[dict[str, object]]] = defaultdict(list)
        for item in episodic:
            canonical_key = str(item.get("canonical_key", "")).strip()
            if canonical_key:
                groups[canonical_key].append(item)

        created = 0
        for canonical_key, items in groups.items():
            if len(items) < 2:
                continue
            existing = self.store.list_records(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                memory_types=["semantic"],
                canonical_key=canonical_key,
                include_archived=False,
                limit=3,
            )
            if existing:
                continue
            summary = self._summarize_cluster(canonical_key, items)
            self._persist_record(
                MemoryRecord(
                    app_id=app_id,
                    session_id=session_id,
                    user_id=user_id,
                    content=summary,
                    memory_type="semantic",
                    importance=min(0.95, max(float(item["importance"]) for item in items) + 0.04),
                    tags=self._merge_tags(items),
                    metadata={
                        "cluster_size": len(items),
                        "derived_from": [str(item["memory_id"]) for item in items[:6]],
                        "profile_id": profile.profile_id,
                    },
                    source_kind="cluster_consolidation",
                    source_confidence=0.78,
                    canonical_key=canonical_key,
                ),
                conflict_strategy=profile.conflict_strategy,
            )
            created += 1
        return created

    def _merge_duplicates(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
    ) -> int:
        records = self.store.list_records(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            include_archived=False,
            status="active",
            limit=1000,
        )
        grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
        for item in records:
            key = (str(item.get("checksum", "")), str(item.get("memory_type", "")))
            if key[0]:
                grouped[key].append(item)

        merged = 0
        for items in grouped.values():
            if len(items) < 2:
                continue
            items.sort(key=lambda item: (float(item.get("importance", 0.0)), float(item.get("source_confidence", 0.0))), reverse=True)
            primary = items[0]
            for duplicate in items[1:]:
                metadata = dict(primary["metadata"])
                metadata.setdefault("merged_from", []).append(str(duplicate["memory_id"]))
                self.store.update_record(
                    str(primary["memory_id"]),
                    importance=max(float(primary["importance"]), float(duplicate["importance"])),
                    tags=sorted(set(list(primary["tags"]) + list(duplicate["tags"]))),
                    metadata=metadata,
                    source_confidence=max(float(primary.get("source_confidence", 0.0)), float(duplicate.get("source_confidence", 0.0))),
                )
                self.store.mark_superseded(str(duplicate["memory_id"]), str(primary["memory_id"]))
                merged += 1
        return merged

    def _persist_extraction_result(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        profile: MemoryProfile,
        extraction: ExtractionResult,
        anchor_memory_id: str = "",
        persist_candidates: bool = True,
    ) -> int:
        stored = 0
        if persist_candidates:
            for candidate in extraction.candidates:
                if candidate.memory_type not in {"working", "episodic", "semantic", "perceptual"}:
                    continue
                if candidate.memory_type == "perceptual" and not profile.perceptual_enabled:
                    continue
                if candidate.memory_type not in profile.write_types and candidate.memory_type != "perceptual":
                    continue
                self._persist_candidate(
                    app_id=app_id,
                    session_id=session_id,
                    user_id=user_id,
                    candidate=candidate,
                    profile=profile,
                )
                stored += 1
        if profile.graph_enabled:
            self._persist_graph(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                entities=extraction.entities,
                relations=extraction.relations,
                memory_id=anchor_memory_id,
            )
        return stored

    def _persist_candidate(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        candidate: MemoryCandidate,
        profile: MemoryProfile,
    ) -> str:
        now = datetime.now(timezone.utc)
        expires_at = None
        if candidate.memory_type == "working":
            expires_at = now + timedelta(hours=profile.working_ttl_hours)
        elif candidate.memory_type == "episodic":
            expires_at = now + timedelta(days=profile.episodic_ttl_days)
        record = MemoryRecord(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            content=candidate.content,
            memory_type=candidate.memory_type,
            importance=candidate.importance,
            tags=candidate.tags,
            metadata={
                **candidate.metadata,
                "canonical_value": candidate.canonical_value,
                "profile_id": profile.profile_id,
            },
            source_kind=candidate.source_kind,
            source_confidence=candidate.source_confidence,
            canonical_key=candidate.canonical_key,
            expires_at=expires_at,
        )
        return self._persist_record(record, conflict_strategy=profile.conflict_strategy)

    def _persist_record(self, record: MemoryRecord, *, conflict_strategy: str) -> str:
        record.checksum = self.store.compute_checksum(record.content)
        record.embedding = self._encode(record.content)
        existing = self.store.list_records(
            app_id=record.app_id,
            session_id=record.session_id,
            user_id=record.user_id,
            memory_types=[record.memory_type],
            checksum=record.checksum,
            include_archived=False,
            limit=10,
        )
        if existing:
            primary = existing[0]
            metadata = dict(primary["metadata"])
            merged_from = list(metadata.get("merged_from", []))
            merged_from.append(record.source_kind)
            metadata["merged_from"] = list(dict.fromkeys(merged_from))
            self.store.update_record(
                str(primary["memory_id"]),
                importance=max(float(primary["importance"]), record.importance),
                tags=sorted(set(list(primary["tags"]) + record.tags)),
                metadata=metadata,
                source_confidence=max(float(primary.get("source_confidence", 0.0)), record.source_confidence),
                embedding=record.embedding or list(primary.get("embedding", [])),
                expires_at=record.expires_at,
            )
            memory_id = str(primary["memory_id"])
            self._sync_vector_index(memory_id=memory_id, record=record)
            return memory_id

        if record.canonical_key:
            related = self.store.list_records(
                app_id=record.app_id,
                session_id=record.session_id if record.memory_type != "semantic" else None,
                user_id=record.user_id,
                memory_types=[record.memory_type],
                canonical_key=record.canonical_key,
                include_archived=False,
                limit=20,
            )
            decision = self._resolve_conflict(record, related, conflict_strategy=conflict_strategy)
            if decision["action"] == "skip" and decision["memory_id"]:
                return decision["memory_id"]
            if decision["action"] == "conflict":
                record.status = "conflict"
                record.metadata["conflict_with"] = decision["conflict_with"]
            if decision["action"] == "supersede":
                record.metadata["supersedes"] = decision["conflict_with"]

        memory_id = self.store.add_record(record)
        if record.canonical_key and conflict_strategy == "confidence":
            related = self.store.list_records(
                app_id=record.app_id,
                session_id=record.session_id if record.memory_type != "semantic" else None,
                user_id=record.user_id,
                memory_types=[record.memory_type],
                canonical_key=record.canonical_key,
                include_archived=False,
                limit=20,
            )
            for item in related:
                existing_id = str(item["memory_id"])
                if existing_id == memory_id:
                    continue
                if float(item.get("source_confidence", 0.0)) < record.source_confidence - 0.05:
                    self.store.mark_superseded(existing_id, memory_id)
        self._sync_vector_index(memory_id=memory_id, record=record)
        return memory_id

    def _resolve_conflict(
        self,
        record: MemoryRecord,
        related: list[dict[str, object]],
        *,
        conflict_strategy: str,
    ) -> dict[str, object]:
        if not related:
            return {"action": "store", "memory_id": "", "conflict_with": []}
        active = [item for item in related if str(item.get("status", "active")) != "superseded"]
        if not active:
            return {"action": "store", "memory_id": "", "conflict_with": []}
        exact = [item for item in active if str(item.get("checksum", "")) == record.checksum]
        if exact:
            return {"action": "skip", "memory_id": str(exact[0]["memory_id"]), "conflict_with": []}
        if conflict_strategy != "confidence":
            return {"action": "conflict", "memory_id": "", "conflict_with": [str(item["memory_id"]) for item in active]}
        highest = max(active, key=lambda item: float(item.get("source_confidence", 0.0)))
        highest_confidence = float(highest.get("source_confidence", 0.0))
        if record.source_confidence > highest_confidence + 0.05:
            return {"action": "supersede", "memory_id": "", "conflict_with": [str(item["memory_id"]) for item in active]}
        return {"action": "conflict", "memory_id": "", "conflict_with": [str(item["memory_id"]) for item in active]}

    def _persist_graph(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        entities: list[MemoryEntity],
        relations: list[MemoryRelation],
        memory_id: str = "",
    ) -> None:
        for entity in entities:
            self.store.upsert_graph_node(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                entity=entity,
            )
        for relation in relations:
            self.store.upsert_graph_node(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                entity=MemoryEntity(entity_name=relation.source, entity_type="entity", confidence=relation.confidence),
            )
            self.store.upsert_graph_node(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                entity=MemoryEntity(entity_name=relation.target, entity_type="entity", confidence=relation.confidence),
            )
            self.store.upsert_graph_relation(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                relation=relation,
                memory_id=memory_id,
            )
        if self.graph_backend and self.graph_backend.enabled:
            try:
                self.graph_backend.upsert_entities_and_relations(
                    app_id=app_id,
                    session_id=session_id,
                    user_id=user_id,
                    entities=entities,
                    relations=relations,
                    memory_id=memory_id,
                )
            except Exception as exc:
                logger.warning("Graph backend sync failed for memory_id=%s: %s", memory_id, exc)

    def _merge_tags(self, items: list[dict[str, object]]) -> list[str]:
        merged: list[str] = []
        for item in items:
            merged.extend(str(tag) for tag in item.get("tags", []))
        return sorted(set(merged))

    def _summarize_cluster(self, canonical_key: str, items: list[dict[str, object]]) -> str:
        snippets = []
        for item in items[:3]:
            content = str(item["content"]).strip()
            snippets.append(content[:160])
        joined = " | ".join(snippets)
        return f"Persistent memory pattern for {canonical_key}: {joined}"

    def _resolve_profile(self, profile: MemoryProfile | None) -> MemoryProfile:
        if profile is not None:
            return profile
        return MemoryProfile(
            schema_id="default",
            enabled=True,
            write_types=["working", "episodic", "semantic"],
            extraction_mode=self.settings.extraction_mode if self.settings else "hybrid",
            retrieval_mode="hybrid",
            vector_backend="auto",
            graph_backend="auto",
            graph_enabled=self.settings.graph_enabled if self.settings else True,
            perceptual_enabled=self.settings.perceptual_enabled if self.settings else True,
            forgetting_enabled=self.settings.forgetting_enabled if self.settings else True,
            conflict_strategy=self.settings.conflict_strategy if self.settings else "confidence",
            consolidation_enabled=True,
        )

    def _encode(self, text: str) -> list[float]:
        try:
            return self.embedder.encode(text)
        except Exception:
            return []

    @staticmethod
    def _derive_canonical_key(content: str, source_kind: str, tags: list[str]) -> str:
        lowered = content.lower()
        if "preference" in tags or source_kind == "preference":
            if any(token in lowered for token in ["brief", "concise", "short", "detailed", "technical"]):
                return "user:preference:response_style"
            return "user:preference:general"
        if "constraint" in tags:
            return "user:constraint"
        return f"{source_kind}:{MemoryService._slug(content)[:48]}"

    @staticmethod
    def _slug(value: str) -> str:
        return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")

    def _sync_vector_index(self, *, memory_id: str, record: MemoryRecord) -> None:
        if not self.vector_index or not self.vector_index.enabled or not record.embedding:
            return
        if record.memory_type == "working":
            return
        try:
            self.vector_index.upsert_memory(
                memory_id=memory_id,
                vector=record.embedding,
                payload={
                    "memory_id": memory_id,
                    "app_id": record.app_id,
                    "session_id": record.session_id,
                    "user_id": record.user_id or "",
                    "memory_type": record.memory_type,
                    "importance": record.importance,
                    "source_kind": record.source_kind,
                    "status": record.status,
                    "archived": record.archived,
                },
            )
        except Exception as exc:
            logger.warning("Vector index sync failed for memory_id=%s: %s", memory_id, exc)

    def _resolve_external_vector_hits(self, hits: list[dict[str, object]]) -> list[dict[str, object]]:
        resolved: list[dict[str, object]] = []
        for hit in hits:
            memory_id = str(hit.get("memory_id", "") or "")
            if not memory_id:
                continue
            record = self.store.get_record(memory_id)
            if not record or record.get("archived") or str(record.get("status", "active")) == "superseded":
                continue
            payload = dict(record)
            payload["score"] = max(float(hit.get("score", 0.0)), float(payload.get("score", 0.0)))
            resolved.append(payload)
        return resolved
