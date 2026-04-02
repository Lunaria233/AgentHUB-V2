from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.platform.core.message import Message, MessageRole


@dataclass(slots=True)
class HistoryRecord:
    session_id: str
    app_id: str
    role: str
    content: str
    timestamp: datetime
    metadata: dict[str, object]


@dataclass(slots=True)
class SessionSummary:
    session_id: str
    app_id: str
    title: str
    preview: str
    message_count: int
    updated_at: str


class SQLiteHistoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def append_message(self, session_id: str, app_id: str, message: Message) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO history(session_id, app_id, role, content, timestamp, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    app_id,
                    message.role.value,
                    message.content,
                    message.timestamp.isoformat(),
                    json.dumps(message.metadata, ensure_ascii=False),
                ),
            )
            conn.commit()

    def list_messages(self, session_id: str, app_id: str | None, limit: int) -> list[Message]:
        sql = """
            SELECT role, content, timestamp, metadata_json
            FROM history
            WHERE session_id = ?
        """
        params: list[object] = [session_id]
        if app_id is not None:
            sql += " AND app_id = ?"
            params.append(app_id)
        sql += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        messages: list[Message] = []
        for role, content, timestamp_raw, metadata_json in reversed(rows):
            timestamp = datetime.fromisoformat(timestamp_raw)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            messages.append(
                Message(
                    role=MessageRole(role),
                    content=content,
                    timestamp=timestamp,
                    metadata=json.loads(metadata_json or "{}"),
                )
            )
        return messages

    def clear_session(self, session_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM history WHERE session_id = ?", (session_id,))
            conn.commit()

    def list_sessions(self, app_id: str | None, limit: int) -> list[SessionSummary]:
        sql = """
            SELECT session_id, app_id, COUNT(*) as message_count, MAX(timestamp) as updated_at
            FROM history
        """
        params: list[object] = []
        if app_id is not None:
            sql += " WHERE app_id = ?"
            params.append(app_id)
        sql += " GROUP BY session_id, app_id ORDER BY MAX(timestamp) DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()

            sessions: list[SessionSummary] = []
            for session_id, session_app_id, message_count, updated_at in rows:
                first_message = conn.execute(
                    """
                    SELECT content
                    FROM history
                    WHERE session_id = ? AND app_id = ? AND role = 'user'
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (session_id, session_app_id),
                ).fetchone()
                latest_message = conn.execute(
                    """
                    SELECT content
                    FROM history
                    WHERE session_id = ? AND app_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (session_id, session_app_id),
                ).fetchone()
                title = self._clip(first_message[0] if first_message else session_id, 72)
                preview = self._clip(latest_message[0] if latest_message else "", 120)
                sessions.append(
                    SessionSummary(
                        session_id=session_id,
                        app_id=session_app_id,
                        title=title,
                        preview=preview,
                        message_count=int(message_count),
                        updated_at=str(updated_at),
                    )
                )
        return sessions

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    app_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _clip(value: str, limit: int) -> str:
        text = value.strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."
