from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.platform.tools.base import ToolContext


@dataclass(slots=True)
class TraceRecord:
    trace_id: str
    event_type: str
    payload: dict[str, Any]
    timestamp: datetime


class TraceStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def append(self, event_type: str, payload: dict[str, Any], trace_id: str | None = None) -> str:
        resolved_trace_id = trace_id or str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO traces(trace_id, event_type, payload_json, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (resolved_trace_id, event_type, json.dumps(payload, ensure_ascii=False), timestamp),
            )
            conn.commit()
        return resolved_trace_id

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.commit()


class TraceService:
    def __init__(self, store: TraceStore) -> None:
        self.store = store

    def new_trace_id(self) -> str:
        return str(uuid.uuid4())

    def log_model_call(self, *, trace_id: str, model: str, payload: dict[str, Any]) -> None:
        self.store.append("model_call", {"model": model, "payload": payload}, trace_id=trace_id)

    def log_tool_call(
        self,
        *,
        context: ToolContext,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        payload = {
            "app_id": context.app_id,
            "session_id": context.session_id,
            "user_id": context.user_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
        }
        self.store.append("tool_call", payload, trace_id=context.trace_id)

    def log_event(self, *, trace_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.store.append(event_type, payload, trace_id=trace_id)
