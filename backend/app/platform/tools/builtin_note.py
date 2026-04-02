from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.platform.tools.base import BaseTool, ToolContext, ToolParameter


@dataclass(slots=True)
class NoteRecord:
    note_id: str
    app_id: str
    session_id: str
    title: str
    content: str
    note_type: str
    tags: list[str]
    created_at: str
    updated_at: str


class FileNoteStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        app_id: str,
        session_id: str,
        title: str,
        content: str,
        note_type: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        note_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        record = NoteRecord(
            note_id=note_id,
            app_id=app_id,
            session_id=session_id,
            title=title,
            content=content,
            note_type=note_type,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._write(record)
        return asdict(record)

    def read(self, note_id: str) -> dict[str, Any] | None:
        path = self._path(note_id)
        if not path.exists():
            return None
        return self._parse(path.read_text(encoding="utf-8"))

    def update(self, note_id: str, **changes: Any) -> dict[str, Any] | None:
        current = self.read(note_id)
        if current is None:
            return None
        for key, value in changes.items():
            if value is not None:
                current[key] = value
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        record = NoteRecord(**current)
        self._write(record)
        return asdict(record)

    def list(self, *, app_id: str | None = None, session_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.md"), reverse=True):
            record = self._parse(path.read_text(encoding="utf-8"))
            if app_id and record.get("app_id") != app_id:
                continue
            if session_id and record.get("session_id") != session_id:
                continue
            notes.append(record)
            if len(notes) >= limit:
                break
        return notes

    def search(self, *, app_id: str, session_id: str | None, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_terms = self._tokenize(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for note in self.list(app_id=app_id, session_id=session_id, limit=200):
            haystack = f"{note.get('title', '')} {note.get('content', '')}"
            score = self._score(query_terms, haystack)
            if score > 0:
                scored.append((score, note))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [note for _, note in scored[:limit]]

    def summary(self, *, app_id: str, session_id: str | None) -> dict[str, Any]:
        notes = self.list(app_id=app_id, session_id=session_id, limit=200)
        by_type: dict[str, int] = {}
        for note in notes:
            note_type = str(note.get("note_type", "note"))
            by_type[note_type] = by_type.get(note_type, 0) + 1
        return {"count": len(notes), "by_type": by_type}

    def _write(self, record: NoteRecord) -> None:
        metadata = {
            "note_id": record.note_id,
            "app_id": record.app_id,
            "session_id": record.session_id,
            "title": record.title,
            "note_type": record.note_type,
            "tags": record.tags,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        body = f"---\n{json.dumps(metadata, ensure_ascii=False)}\n---\n{record.content}"
        self._path(record.note_id).write_text(body, encoding="utf-8")

    def _path(self, note_id: str) -> Path:
        return self.root / f"{note_id}.md"

    @staticmethod
    def _parse(text: str) -> dict[str, Any]:
        if not text.startswith("---\n"):
            return {}
        _, metadata_text, content = text.split("---\n", 2)
        metadata = json.loads(metadata_text.strip())
        metadata["content"] = content.strip()
        return metadata

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token.lower() for token in text.split() if token.strip()}

    def _score(self, query_terms: set[str], haystack: str) -> float:
        if not query_terms:
            return 0.0
        haystack_terms = self._tokenize(haystack)
        if not haystack_terms:
            return 0.0
        return len(query_terms & haystack_terms) / len(query_terms)


class BuiltinNoteTool(BaseTool):
    def __init__(self, store: FileNoteStore) -> None:
        self.store = store

    @property
    def name(self) -> str:
        return "note"

    @property
    def description(self) -> str:
        return "Create, read, update, search, and summarize notes."

    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="action", description="create/read/update/list/search/summary"),
            ToolParameter(name="note_id", description="Existing note id", required=False),
            ToolParameter(name="title", description="Note title", required=False),
            ToolParameter(name="content", description="Note content", required=False),
            ToolParameter(name="note_type", description="task_state/blocker/conclusion", required=False),
            ToolParameter(name="query", description="Search query", required=False),
        ]

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        action = str(arguments.get("action", "")).lower()
        if action == "create":
            return {
                "ok": True,
                "note": self.store.create(
                    app_id=context.app_id,
                    session_id=context.session_id,
                    title=str(arguments.get("title", "Untitled")),
                    content=str(arguments.get("content", "")),
                    note_type=str(arguments.get("note_type", "note")),
                    tags=list(arguments.get("tags", [])),
                ),
            }
        if action == "read":
            note = self.store.read(str(arguments["note_id"]))
            return {"ok": note is not None, "note": note}
        if action == "update":
            note = self.store.update(
                str(arguments["note_id"]),
                title=arguments.get("title"),
                content=arguments.get("content"),
                note_type=arguments.get("note_type"),
                tags=arguments.get("tags"),
            )
            return {"ok": note is not None, "note": note}
        if action == "list":
            return {
                "ok": True,
                "notes": self.store.list(app_id=context.app_id, session_id=context.session_id, limit=int(arguments.get("limit", 20))),
            }
        if action == "search":
            return {
                "ok": True,
                "notes": self.store.search(
                    app_id=context.app_id,
                    session_id=context.session_id,
                    query=str(arguments.get("query", "")),
                    limit=int(arguments.get("limit", 5)),
                ),
            }
        if action == "summary":
            return {"ok": True, "summary": self.store.summary(app_id=context.app_id, session_id=context.session_id)}
        return {"ok": False, "error": f"Unsupported note action: {action}"}
