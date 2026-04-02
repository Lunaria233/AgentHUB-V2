from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.platform.memory.base import MemoryEntity, MemoryQuery, MemoryRecord, MemoryRelation


class SQLiteMemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def add_record(self, record: MemoryRecord) -> str:
        memory_id = record.memory_id or str(uuid.uuid4())
        checksum = record.checksum or self.compute_checksum(record.content)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO memory(
                    memory_id, app_id, session_id, user_id, memory_type, importance, tags_json,
                    metadata_json, source_kind, source_confidence, canonical_key, checksum,
                    status, superseded_by, embedding_json, content, access_count, last_accessed_at,
                    expires_at, archived, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    record.app_id,
                    record.session_id,
                    record.user_id,
                    record.memory_type,
                    record.importance,
                    json.dumps(record.tags, ensure_ascii=False),
                    json.dumps(record.metadata, ensure_ascii=False),
                    record.source_kind,
                    record.source_confidence,
                    record.canonical_key,
                    checksum,
                    record.status,
                    record.superseded_by,
                    json.dumps(record.embedding, ensure_ascii=False),
                    record.content,
                    record.access_count,
                    self._to_iso(record.last_accessed_at),
                    self._to_iso(record.expires_at),
                    int(record.archived),
                    record.created_at.isoformat(),
                ),
            )
            conn.commit()
        return memory_id

    def search_records(self, query: MemoryQuery) -> list[dict[str, Any]]:
        sql = """
            SELECT
                memory_id, app_id, session_id, user_id, memory_type, importance, tags_json,
                metadata_json, source_kind, source_confidence, canonical_key, checksum, status,
                superseded_by, embedding_json, content, access_count, last_accessed_at,
                expires_at, archived, created_at
            FROM memory
            WHERE 1 = 1
        """
        params: list[Any] = []
        if query.app_id:
            sql += " AND app_id = ?"
            params.append(query.app_id)
        if query.session_id:
            sql += " AND session_id = ?"
            params.append(query.session_id)
        if query.user_id:
            sql += " AND user_id = ?"
            params.append(query.user_id)
        if query.memory_types:
            placeholders = ", ".join("?" for _ in query.memory_types)
            sql += f" AND memory_type IN ({placeholders})"
            params.extend(query.memory_types)
        if query.min_importance > 0:
            sql += " AND importance >= ?"
            params.append(query.min_importance)
        if not query.include_archived:
            sql += " AND archived = 0"

        now = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()

        scored: list[tuple[float, dict[str, Any]]] = []
        query_terms = self._tokenize(query.query)
        for row in rows:
            payload = self._row_to_payload(row)
            if not query.include_expired and self._is_expired(payload, now):
                continue
            if query.tag_filter and not set(query.tag_filter).issubset(set(payload["tags"])):
                continue
            score = self._score(query_terms, payload, query.type_weights, query.query_embedding, query.retrieval_mode, now)
            if score <= 0:
                continue
            payload["score"] = score
            scored.append((score, payload))

        scored.sort(key=lambda item: item[0], reverse=True)
        top_records = [payload for _, payload in scored[: query.limit]]
        if top_records:
            self.touch_records([str(record["memory_id"]) for record in top_records if record.get("memory_id")])
        return top_records

    def list_records(
        self,
        *,
        app_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        memory_types: list[str] | None = None,
        canonical_key: str | None = None,
        checksum: str | None = None,
        status: str | None = None,
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT
                memory_id, app_id, session_id, user_id, memory_type, importance, tags_json,
                metadata_json, source_kind, source_confidence, canonical_key, checksum, status,
                superseded_by, embedding_json, content, access_count, last_accessed_at,
                expires_at, archived, created_at
            FROM memory
            WHERE 1 = 1
        """
        params: list[Any] = []
        if app_id:
            sql += " AND app_id = ?"
            params.append(app_id)
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)
        if memory_types:
            placeholders = ", ".join("?" for _ in memory_types)
            sql += f" AND memory_type IN ({placeholders})"
            params.extend(memory_types)
        if canonical_key:
            sql += " AND canonical_key = ?"
            params.append(canonical_key)
        if checksum:
            sql += " AND checksum = ?"
            params.append(checksum)
        if status:
            sql += " AND status = ?"
            params.append(status)
        if not include_archived:
            sql += " AND archived = 0"
        sql += " ORDER BY datetime(created_at) DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_payload(row) for row in rows]

    def get_record(self, memory_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT
                    memory_id, app_id, session_id, user_id, memory_type, importance, tags_json,
                    metadata_json, source_kind, source_confidence, canonical_key, checksum, status,
                    superseded_by, embedding_json, content, access_count, last_accessed_at,
                    expires_at, archived, created_at
                FROM memory
                WHERE memory_id = ?
                """,
                (memory_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_payload(row)

    def update_record(
        self,
        memory_id: str,
        *,
        importance: float | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        source_confidence: float | None = None,
        canonical_key: str | None = None,
        status: str | None = None,
        superseded_by: str | None = None,
        embedding: list[float] | None = None,
        access_count: int | None = None,
        expires_at: datetime | None = None,
        archived: bool | None = None,
    ) -> None:
        updates: list[str] = []
        params: list[Any] = []
        if importance is not None:
            updates.append("importance = ?")
            params.append(importance)
        if tags is not None:
            updates.append("tags_json = ?")
            params.append(json.dumps(tags, ensure_ascii=False))
        if metadata is not None:
            updates.append("metadata_json = ?")
            params.append(json.dumps(metadata, ensure_ascii=False))
        if source_confidence is not None:
            updates.append("source_confidence = ?")
            params.append(source_confidence)
        if canonical_key is not None:
            updates.append("canonical_key = ?")
            params.append(canonical_key)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if superseded_by is not None:
            updates.append("superseded_by = ?")
            params.append(superseded_by)
        if embedding is not None:
            updates.append("embedding_json = ?")
            params.append(json.dumps(embedding, ensure_ascii=False))
        if access_count is not None:
            updates.append("access_count = ?")
            params.append(access_count)
        if expires_at is not None:
            updates.append("expires_at = ?")
            params.append(self._to_iso(expires_at))
        if archived is not None:
            updates.append("archived = ?")
            params.append(int(archived))
        if not updates:
            return
        params.append(memory_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE memory SET {', '.join(updates)} WHERE memory_id = ?", params)
            conn.commit()

    def archive_records(self, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        placeholders = ", ".join("?" for _ in memory_ids)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE memory SET archived = 1 WHERE memory_id IN ({placeholders})", memory_ids)
            conn.commit()

    def mark_superseded(self, memory_id: str, superseded_by: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE memory SET status = 'superseded', superseded_by = ?, archived = 1 WHERE memory_id = ?",
                (superseded_by, memory_id),
            )
            conn.commit()

    def prune_memory_type(self, *, app_id: str, session_id: str, memory_type: str, keep: int) -> int:
        rows = self.list_records(app_id=app_id, session_id=session_id, memory_types=[memory_type], limit=500, include_archived=False)
        if len(rows) <= keep:
            return 0
        to_archive = [str(row["memory_id"]) for row in rows[keep:]]
        self.archive_records(to_archive)
        return len(to_archive)

    def apply_forgetting_policy(self, *, app_id: str, session_id: str, user_id: str | None) -> int:
        now = datetime.now(timezone.utc)
        candidates = self.list_records(app_id=app_id, session_id=session_id, user_id=user_id, include_archived=False, limit=1000)
        to_archive: list[str] = []
        for item in candidates:
            memory_type = str(item["memory_type"])
            if memory_type == "semantic":
                continue
            age_days = self._age_in_days(str(item.get("created_at", "")), now)
            access_count = int(item.get("access_count", 0))
            importance = float(item.get("importance", 0.0))
            if memory_type == "working" and (age_days > 3 or (age_days > 1 and access_count == 0 and importance < 0.55)):
                to_archive.append(str(item["memory_id"]))
            if memory_type == "episodic" and age_days > 45 and access_count == 0 and importance < 0.6:
                to_archive.append(str(item["memory_id"]))
        if to_archive:
            self.archive_records(to_archive)
        return len(to_archive)

    def delete_expired_records(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM memory WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
            conn.commit()
        return int(cursor.rowcount or 0)

    def summary(self, *, app_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
        records = self.list_records(app_id=app_id, user_id=user_id, include_archived=True, limit=5000)
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        archived = 0
        for record in records:
            memory_type = str(record["memory_type"])
            by_type[memory_type] = by_type.get(memory_type, 0) + 1
            status = str(record.get("status", "active"))
            by_status[status] = by_status.get(status, 0) + 1
            if record["archived"]:
                archived += 1
        graph_nodes, graph_edges = self._graph_counts(app_id=app_id, user_id=user_id)
        return {
            "count": len(records),
            "archived": archived,
            "by_type": by_type,
            "by_status": by_status,
            "graph": {"nodes": graph_nodes, "edges": graph_edges},
        }

    def touch_records(self, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        placeholders = ", ".join("?" for _ in memory_ids)
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"""
                UPDATE memory
                SET access_count = COALESCE(access_count, 0) + 1,
                    last_accessed_at = ?
                WHERE memory_id IN ({placeholders})
                """,
                [now, *memory_ids],
            )
            conn.commit()

    def upsert_graph_node(
        self,
        *,
        app_id: str,
        session_id: str | None,
        user_id: str | None,
        entity: MemoryEntity,
    ) -> str:
        entity_key = self._entity_key(entity.entity_name, entity.entity_type)
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO memory_graph_nodes(
                    entity_key, app_id, session_id, user_id, entity_name, entity_type,
                    confidence, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_key) DO UPDATE SET
                    confidence = MAX(confidence, excluded.confidence),
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    entity_key,
                    app_id,
                    session_id or "",
                    user_id or "",
                    entity.entity_name,
                    entity.entity_type,
                    entity.confidence,
                    json.dumps(entity.metadata, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
        return entity_key

    def upsert_graph_relation(
        self,
        *,
        app_id: str,
        session_id: str | None,
        user_id: str | None,
        relation: MemoryRelation,
        memory_id: str = "",
    ) -> str:
        source_key = self._entity_key(relation.source, "entity")
        target_key = self._entity_key(relation.target, "entity")
        edge_id = self.compute_checksum(f"{app_id}|{session_id}|{user_id}|{source_key}|{relation.relation}|{target_key}")
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO memory_graph_edges(
                    edge_id, app_id, session_id, user_id, source_entity_key, relation,
                    target_entity_key, confidence, memory_id, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(edge_id) DO UPDATE SET
                    confidence = MAX(confidence, excluded.confidence),
                    memory_id = CASE WHEN excluded.memory_id != '' THEN excluded.memory_id ELSE memory_graph_edges.memory_id END,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    edge_id,
                    app_id,
                    session_id or "",
                    user_id or "",
                    source_key,
                    relation.relation,
                    target_key,
                    relation.confidence,
                    memory_id,
                    json.dumps(relation.metadata, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
        return edge_id

    def search_graph(
        self,
        *,
        query: str,
        app_id: str,
        session_id: str | None,
        user_id: str | None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        query_terms = self._tokenize(query)
        sql = """
            SELECT
                e.edge_id, e.relation, e.confidence, e.memory_id,
                s.entity_name, t.entity_name
            FROM memory_graph_edges e
            JOIN memory_graph_nodes s ON s.entity_key = e.source_entity_key
            JOIN memory_graph_nodes t ON t.entity_key = e.target_entity_key
            WHERE e.app_id = ?
        """
        params: list[Any] = [app_id]
        if session_id:
            sql += " AND e.session_id IN (?, '')"
            params.append(session_id)
        if user_id:
            sql += " AND e.user_id IN (?, '')"
            params.append(user_id)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()

        scored: list[tuple[float, dict[str, Any]]] = []
        for edge_id, relation, confidence, memory_id, source_name, target_name in rows:
            content = f"{source_name} {relation} {target_name}"
            score = self._overlap_score(query_terms, content) + float(confidence or 0.0) * 0.2
            if score <= 0:
                continue
            scored.append(
                (
                    score,
                    {
                        "memory_id": memory_id,
                        "memory_type": "graph",
                        "source_kind": "graph_relation",
                        "content": content,
                        "score": score,
                        "edge_id": edge_id,
                        "relation": relation,
                        "source": source_name,
                        "target": target_name,
                    },
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [payload for _, payload in scored[:limit]]

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT UNIQUE,
                    app_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    memory_type TEXT NOT NULL,
                    importance REAL NOT NULL,
                    tags_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    source_kind TEXT NOT NULL DEFAULT 'manual',
                    source_confidence REAL NOT NULL DEFAULT 0.6,
                    canonical_key TEXT,
                    checksum TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    superseded_by TEXT,
                    embedding_json TEXT NOT NULL DEFAULT '[]',
                    content TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    last_accessed_at TEXT,
                    expires_at TEXT,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_graph_nodes (
                    entity_key TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    user_id TEXT NOT NULL DEFAULT '',
                    entity_name TEXT NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT 'entity',
                    confidence REAL NOT NULL DEFAULT 0.6,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_graph_edges (
                    edge_id TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    user_id TEXT NOT NULL DEFAULT '',
                    source_entity_key TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    target_entity_key TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.6,
                    memory_id TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        self._ensure_columns(
            {
                "memory_id": "TEXT",
                "source_kind": "TEXT NOT NULL DEFAULT 'manual'",
                "source_confidence": "REAL NOT NULL DEFAULT 0.6",
                "canonical_key": "TEXT",
                "checksum": "TEXT",
                "status": "TEXT NOT NULL DEFAULT 'active'",
                "superseded_by": "TEXT",
                "embedding_json": "TEXT NOT NULL DEFAULT '[]'",
                "access_count": "INTEGER NOT NULL DEFAULT 0",
                "last_accessed_at": "TEXT",
                "expires_at": "TEXT",
                "archived": "INTEGER NOT NULL DEFAULT 0",
            }
        )
        self._ensure_memory_ids()
        self._ensure_checksums()
        self._ensure_unique_index()
        self._ensure_indexes()

    def _ensure_columns(self, columns: dict[str, str]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            existing = {row[1] for row in conn.execute("PRAGMA table_info(memory)").fetchall()}
            for column, ddl in columns.items():
                if column in existing:
                    continue
                conn.execute(f"ALTER TABLE memory ADD COLUMN {column} {ddl}")
            conn.commit()

    def _ensure_memory_ids(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT id, content FROM memory WHERE memory_id IS NULL OR memory_id = ''").fetchall()
            for row_id, _ in rows:
                conn.execute("UPDATE memory SET memory_id = ? WHERE id = ?", (str(uuid.uuid4()), row_id))
            conn.commit()

    def _ensure_checksums(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT id, content FROM memory WHERE checksum IS NULL OR checksum = ''").fetchall()
            for row_id, content in rows:
                conn.execute("UPDATE memory SET checksum = ? WHERE id = ?", (self.compute_checksum(str(content)), row_id))
            conn.commit()

    def _ensure_unique_index(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_memory_id ON memory(memory_id)")
            conn.commit()

    def _ensure_indexes(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_lookup_scope ON memory(app_id, session_id, user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_canonical_key ON memory(canonical_key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_checksum ON memory(checksum)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_status ON memory(status)")
            conn.commit()

    def _graph_counts(self, *, app_id: str | None, user_id: str | None) -> tuple[int, int]:
        node_sql = "SELECT COUNT(*) FROM memory_graph_nodes WHERE 1 = 1"
        edge_sql = "SELECT COUNT(*) FROM memory_graph_edges WHERE 1 = 1"
        node_params: list[Any] = []
        edge_params: list[Any] = []
        if app_id:
            node_sql += " AND app_id = ?"
            edge_sql += " AND app_id = ?"
            node_params.append(app_id)
            edge_params.append(app_id)
        if user_id:
            node_sql += " AND user_id IN (?, '')"
            edge_sql += " AND user_id IN (?, '')"
            node_params.append(user_id)
            edge_params.append(user_id)
        with sqlite3.connect(self.db_path) as conn:
            node_count = int(conn.execute(node_sql, node_params).fetchone()[0])
            edge_count = int(conn.execute(edge_sql, edge_params).fetchone()[0])
        return node_count, edge_count

    @staticmethod
    def _row_to_payload(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "memory_id": row[0],
            "app_id": row[1],
            "session_id": row[2],
            "user_id": row[3],
            "memory_type": row[4],
            "importance": row[5],
            "tags": json.loads(row[6] or "[]"),
            "metadata": json.loads(row[7] or "{}"),
            "source_kind": row[8],
            "source_confidence": float(row[9] or 0.0),
            "canonical_key": row[10] or "",
            "checksum": row[11] or "",
            "status": row[12] or "active",
            "superseded_by": row[13] or "",
            "embedding": [float(value) for value in json.loads(row[14] or "[]")],
            "content": row[15],
            "access_count": int(row[16] or 0),
            "last_accessed_at": row[17],
            "expires_at": row[18],
            "archived": bool(row[19]),
            "created_at": row[20],
        }

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        cleaned = "".join(char.lower() if char.isalnum() else " " for char in text)
        return {token for token in cleaned.split() if token}

    def _score(
        self,
        query_terms: set[str],
        payload: dict[str, Any],
        type_weights: dict[str, float],
        query_embedding: list[float],
        retrieval_mode: str,
        now: datetime,
    ) -> float:
        lexical_score = self._overlap_score(query_terms, str(payload["content"]))
        vector_score = self._vector_score(query_embedding, list(payload.get("embedding", [])))
        importance_score = float(payload["importance"]) * 0.22
        type_score = float(type_weights.get(str(payload["memory_type"]), 0.0))
        access_score = min(int(payload.get("access_count", 0)), 5) * 0.02
        recency_score = self._recency_score(str(payload.get("created_at", "")), now)
        confidence_score = float(payload.get("source_confidence", 0.0)) * 0.08
        status_penalty = 0.0 if str(payload.get("status", "active")) == "active" else -0.08
        if not query_terms and not query_embedding:
            lexical_score = 0.05
        retrieval_mode = retrieval_mode.lower()
        if retrieval_mode == "vector":
            lexical_score = 0.0
        elif retrieval_mode == "lexical":
            vector_score = 0.0
        return lexical_score + vector_score + importance_score + type_score + access_score + recency_score + confidence_score + status_penalty

    def _vector_score(self, query_embedding: list[float], stored_embedding: list[float]) -> float:
        if not query_embedding or not stored_embedding:
            return 0.0
        if len(query_embedding) != len(stored_embedding):
            return 0.0
        dot = sum(left * right for left, right in zip(query_embedding, stored_embedding))
        return max(0.0, dot) * 0.32

    def _recency_score(self, created_at_raw: str, now: datetime) -> float:
        try:
            created_at = datetime.fromisoformat(created_at_raw)
        except ValueError:
            return 0.0
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age = now - created_at
        if age <= timedelta(days=1):
            return 0.1
        if age <= timedelta(days=7):
            return 0.05
        return 0.0

    def _is_expired(self, payload: dict[str, Any], now: datetime) -> bool:
        expires_at_raw = payload.get("expires_at")
        if not expires_at_raw:
            return False
        try:
            expires_at = datetime.fromisoformat(str(expires_at_raw))
        except ValueError:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at < now

    def _age_in_days(self, created_at_raw: str, now: datetime) -> int:
        try:
            created_at = datetime.fromisoformat(created_at_raw)
        except ValueError:
            return 0
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return max(0, (now - created_at).days)

    def _overlap_score(self, query_terms: set[str], content: str) -> float:
        if not query_terms:
            return 0.0
        content_terms = self._tokenize(content)
        if not content_terms:
            return 0.0
        return len(query_terms & content_terms) / len(query_terms)

    @staticmethod
    def _entity_key(entity_name: str, entity_type: str) -> str:
        normalized = "".join(char.lower() if char.isalnum() else "-" for char in entity_name).strip("-")
        return f"{entity_type}:{normalized}"[:160]

    @staticmethod
    def _to_iso(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def compute_checksum(content: str) -> str:
        return hashlib.sha256(content.strip().lower().encode("utf-8")).hexdigest()
