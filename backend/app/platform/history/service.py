from __future__ import annotations

from app.platform.core.message import Message, MessageRole
from app.platform.history.store import SQLiteHistoryStore, SessionSummary


class HistoryService:
    def __init__(self, store: SQLiteHistoryStore) -> None:
        self.store = store

    def add_user_message(self, session_id: str, app_id: str, content: str) -> None:
        self.store.append_message(session_id, app_id, Message(role=MessageRole.USER, content=content))

    def add_assistant_message(self, session_id: str, app_id: str, content: str) -> None:
        self.store.append_message(session_id, app_id, Message(role=MessageRole.ASSISTANT, content=content))

    def add_system_message(self, session_id: str, app_id: str, content: str) -> None:
        self.store.append_message(session_id, app_id, Message(role=MessageRole.SYSTEM, content=content))

    def add_tool_message(self, session_id: str, app_id: str, content: str) -> None:
        self.store.append_message(session_id, app_id, Message(role=MessageRole.TOOL, content=content))

    def get_recent_history(self, session_id: str, app_id: str | None, limit: int) -> list[Message]:
        return self.store.list_messages(session_id=session_id, app_id=app_id, limit=limit)

    def clear_session(self, session_id: str) -> None:
        self.store.clear_session(session_id)

    def list_sessions(self, app_id: str | None, limit: int) -> list[SessionSummary]:
        return self.store.list_sessions(app_id=app_id, limit=limit)
