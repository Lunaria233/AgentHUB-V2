from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.platform.rag.document import Document, DocumentChunk, KnowledgeScopeSummary, RAGDocumentRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteRAGStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def upsert_document(self, *, document: Document, chunks: list[DocumentChunk]) -> None:
        timestamp = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM rag_chunks WHERE document_id = ?", (document.document_id,))
            conn.execute(
                """
                INSERT INTO rag_documents(
                    document_id, kb_id, title, raw_text, source_type, visibility, tenant_id, user_id, app_id, agent_id,
                    session_id, owner_id, is_temporary, file_name, mime_type, source_uri, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    kb_id=excluded.kb_id,
                    title=excluded.title,
                    raw_text=excluded.raw_text,
                    source_type=excluded.source_type,
                    visibility=excluded.visibility,
                    tenant_id=excluded.tenant_id,
                    user_id=excluded.user_id,
                    app_id=excluded.app_id,
                    agent_id=excluded.agent_id,
                    session_id=excluded.session_id,
                    owner_id=excluded.owner_id,
                    is_temporary=excluded.is_temporary,
                    file_name=excluded.file_name,
                    mime_type=excluded.mime_type,
                    source_uri=excluded.source_uri,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    document.document_id,
                    document.kb_id,
                    document.title,
                    document.text,
                    document.source_type,
                    document.visibility,
                    document.tenant_id,
                    document.user_id,
                    document.app_id,
                    document.agent_id,
                    document.session_id,
                    document.owner_id,
                    1 if document.is_temporary else 0,
                    document.file_name,
                    document.mime_type,
                    document.source_uri,
                    json.dumps(document.metadata, ensure_ascii=False),
                    document.created_at.isoformat(),
                    timestamp,
                ),
            )
            conn.executemany(
                """
                INSERT INTO rag_chunks(
                    chunk_id, document_id, kb_id, chunk_index, title, content, preview, page_or_section,
                    token_count, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.kb_id,
                        chunk.chunk_index,
                        chunk.title,
                        chunk.content,
                        chunk.preview,
                        chunk.page_or_section,
                        max(1, len(chunk.content.split())),
                        json.dumps(chunk.metadata, ensure_ascii=False),
                        timestamp,
                    )
                    for chunk in chunks
                ],
            )
            conn.commit()

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM rag_documents WHERE document_id = ?", (document_id,)).fetchone()
        return self._row_to_document(row) if row else None

    def list_documents(
        self,
        *,
        kb_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
        app_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        visibility: list[str] | None = None,
        source_types: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT d.*,
                   COUNT(c.chunk_id) AS chunk_count
            FROM rag_documents d
            LEFT JOIN rag_chunks c ON c.document_id = d.document_id
        """
        clauses: list[str] = []
        values: list[Any] = []
        if kb_ids:
            placeholders = ",".join("?" for _ in kb_ids)
            clauses.append(f"d.kb_id IN ({placeholders})")
            values.extend(kb_ids)
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            clauses.append(f"d.document_id IN ({placeholders})")
            values.extend(document_ids)
        if app_id:
            clauses.append("d.app_id = ?")
            values.append(app_id)
        if user_id:
            clauses.append("d.user_id = ?")
            values.append(user_id)
        if session_id:
            clauses.append("d.session_id = ?")
            values.append(session_id)
        if visibility:
            placeholders = ",".join("?" for _ in visibility)
            clauses.append(f"d.visibility IN ({placeholders})")
            values.extend(visibility)
        if source_types:
            placeholders = ",".join("?" for _ in source_types)
            clauses.append(f"d.source_type IN ({placeholders})")
            values.extend(source_types)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += """
            GROUP BY d.document_id, d.kb_id, d.title, d.raw_text, d.source_type, d.visibility, d.tenant_id, d.user_id,
                     d.app_id, d.agent_id, d.session_id, d.owner_id, d.is_temporary, d.file_name, d.mime_type,
                     d.source_uri, d.metadata_json, d.created_at, d.updated_at
            ORDER BY d.updated_at DESC
        """
        if limit:
            sql += " LIMIT ?"
            values.append(limit)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, values).fetchall()
        return [self._row_to_document(row) for row in rows]

    def list_chunks(
        self,
        *,
        chunk_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
        kb_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT c.*, d.visibility, d.source_type, d.tenant_id, d.user_id, d.app_id, d.agent_id, d.session_id,
                   d.owner_id, d.is_temporary, d.source_uri, d.file_name, d.mime_type
            FROM rag_chunks c
            JOIN rag_documents d ON d.document_id = c.document_id
        """
        clauses: list[str] = []
        values: list[Any] = []
        if chunk_ids:
            placeholders = ",".join("?" for _ in chunk_ids)
            clauses.append(f"c.chunk_id IN ({placeholders})")
            values.extend(chunk_ids)
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            clauses.append(f"c.document_id IN ({placeholders})")
            values.extend(document_ids)
        if kb_ids:
            placeholders = ",".join("?" for _ in kb_ids)
            clauses.append(f"c.kb_id IN ({placeholders})")
            values.extend(kb_ids)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY c.chunk_index ASC"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, values).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def delete_document(self, document_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM rag_chunks WHERE document_id = ?", (document_id,))
            cursor = conn.execute("DELETE FROM rag_documents WHERE document_id = ?", (document_id,))
            conn.commit()
        return cursor.rowcount > 0

    def summarize(
        self,
        *,
        app_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        documents = self.list_documents(app_id=app_id, user_id=user_id, session_id=session_id)
        summary = {
            "document_count": len(documents),
            "chunk_count": sum(int(item.get("chunk_count", 0)) for item in documents),
            "by_visibility": {},
            "by_source_type": {},
        }
        for document in documents:
            visibility = str(document.get("visibility", ""))
            source_type = str(document.get("source_type", ""))
            summary["by_visibility"][visibility] = int(summary["by_visibility"].get(visibility, 0)) + 1
            summary["by_source_type"][source_type] = int(summary["by_source_type"].get(source_type, 0)) + 1
        return summary

    def list_knowledge_scopes(
        self,
        *,
        app_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[KnowledgeScopeSummary]:
        sql = """
            SELECT kb_id, visibility, app_id, user_id, session_id, owner_id, is_temporary, COUNT(*) AS document_count
            FROM rag_documents
        """
        clauses: list[str] = []
        values: list[Any] = []
        if app_id:
            clauses.append("app_id = ?")
            values.append(app_id)
        if user_id:
            clauses.append("(user_id = ? OR user_id IS NULL)")
            values.append(user_id)
        elif session_id:
            clauses.append("(session_id = ? OR (user_id IS NULL AND session_id IS NULL))")
            values.append(session_id)
        else:
            clauses.append("user_id IS NULL AND session_id IS NULL")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " GROUP BY kb_id, visibility, app_id, user_id, session_id, owner_id, is_temporary ORDER BY visibility, kb_id"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, values).fetchall()
        return [
            KnowledgeScopeSummary(
                kb_id=str(row["kb_id"]),
                visibility=str(row["visibility"]),
                app_id=str(row["app_id"]),
                user_id=row["user_id"],
                session_id=row["session_id"],
                owner_id=str(row["owner_id"]),
                is_temporary=bool(row["is_temporary"]),
                document_count=int(row["document_count"]),
            )
            for row in rows
        ]

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_documents (
                    document_id TEXT PRIMARY KEY,
                    kb_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT,
                    app_id TEXT NOT NULL,
                    agent_id TEXT,
                    session_id TEXT,
                    owner_id TEXT NOT NULL,
                    is_temporary INTEGER NOT NULL DEFAULT 0,
                    file_name TEXT,
                    mime_type TEXT,
                    source_uri TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    kb_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    preview TEXT NOT NULL,
                    page_or_section TEXT,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES rag_documents(document_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_documents_kb_id ON rag_documents(kb_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_documents_app_id ON rag_documents(app_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_documents_user_id ON rag_documents(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_documents_session_id ON rag_documents(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_documents_visibility ON rag_documents(visibility)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_id ON rag_chunks(document_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_chunks_kb_id ON rag_chunks(kb_id)")
            conn.commit()

    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "document_id": row["document_id"],
            "kb_id": row["kb_id"],
            "title": row["title"],
            "raw_text": row["raw_text"],
            "source_type": row["source_type"],
            "visibility": row["visibility"],
            "tenant_id": row["tenant_id"],
            "user_id": row["user_id"],
            "app_id": row["app_id"],
            "agent_id": row["agent_id"],
            "session_id": row["session_id"],
            "owner_id": row["owner_id"],
            "is_temporary": bool(row["is_temporary"]),
            "file_name": row["file_name"],
            "mime_type": row["mime_type"],
            "source_uri": row["source_uri"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "chunk_count": int(row["chunk_count"]) if "chunk_count" in row.keys() and row["chunk_count"] is not None else 0,
        }

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> dict[str, Any]:
        payload = {
            "chunk_id": row["chunk_id"],
            "document_id": row["document_id"],
            "kb_id": row["kb_id"],
            "chunk_index": int(row["chunk_index"]),
            "title": row["title"],
            "content": row["content"],
            "preview": row["preview"],
            "page_or_section": row["page_or_section"] or "",
            "token_count": int(row["token_count"]),
            "metadata": json.loads(row["metadata_json"] or "{}"),
        }
        for key in [
            "visibility",
            "source_type",
            "tenant_id",
            "user_id",
            "app_id",
            "agent_id",
            "session_id",
            "owner_id",
            "is_temporary",
            "source_uri",
            "file_name",
            "mime_type",
        ]:
            if key in row.keys():
                payload[key] = row[key]
        if "is_temporary" in payload:
            payload["is_temporary"] = bool(payload["is_temporary"])
        return payload

    @staticmethod
    def to_record(payload: dict[str, Any]) -> RAGDocumentRecord:
        return RAGDocumentRecord(
            document_id=str(payload["document_id"]),
            kb_id=str(payload["kb_id"]),
            title=str(payload["title"]),
            source_type=str(payload["source_type"]),
            visibility=str(payload["visibility"]),
            tenant_id=str(payload["tenant_id"]),
            user_id=payload.get("user_id"),
            app_id=str(payload["app_id"]),
            agent_id=payload.get("agent_id"),
            session_id=payload.get("session_id"),
            owner_id=str(payload["owner_id"]),
            is_temporary=bool(payload["is_temporary"]),
            file_name=str(payload.get("file_name") or ""),
            mime_type=str(payload.get("mime_type") or ""),
            source_uri=str(payload.get("source_uri") or ""),
            metadata=dict(payload.get("metadata", {})),
            chunk_count=int(payload.get("chunk_count", 0) or 0),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )
