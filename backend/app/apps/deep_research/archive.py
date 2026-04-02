from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ResearchRunStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save_run(
        self,
        *,
        session_id: str,
        topic: str,
        user_id: str | None,
        status: str,
        report: str,
        tasks: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        current = self.get_run(session_id)
        created_at = str(current.get("created_at")) if current else self._now()
        payload = {
            "session_id": session_id,
            "app_id": "deep_research",
            "topic": topic,
            "user_id": user_id,
            "status": status,
            "report": report,
            "tasks": tasks,
            "events": events,
            "created_at": created_at,
            "updated_at": self._now(),
        }
        self._path(session_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def get_run(self, session_id: str) -> dict[str, Any] | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            records.append(
                {
                    "session_id": payload.get("session_id", ""),
                    "app_id": payload.get("app_id", "deep_research"),
                    "topic": payload.get("topic", ""),
                    "status": payload.get("status", "completed"),
                    "report_preview": self._clip(str(payload.get("report", "")), 200),
                    "task_count": len(payload.get("tasks", [])),
                    "created_at": payload.get("created_at", ""),
                    "updated_at": payload.get("updated_at", ""),
                }
            )
        records.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return records[:limit]

    def _path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    @staticmethod
    def _clip(value: str, limit: int) -> str:
        text = value.strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
