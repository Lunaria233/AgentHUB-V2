from __future__ import annotations

from fastapi import APIRouter, Query

from app.platform.runtime.orchestrator import get_orchestrator


router = APIRouter()


@router.get("/{session_id}")
def get_session_history(session_id: str, app_id: str | None = Query(default=None)) -> dict[str, object]:
    orchestrator = get_orchestrator()
    messages = orchestrator.history_service.get_recent_history(
        session_id=session_id,
        app_id=app_id,
        limit=100,
    )
    return {
        "session_id": session_id,
        "app_id": app_id,
        "messages": [message.to_dict() for message in messages],
    }


@router.get("")
def list_sessions(app_id: str | None = Query(default=None), limit: int = Query(default=30, ge=1, le=200)) -> dict[str, object]:
    orchestrator = get_orchestrator()
    sessions = orchestrator.history_service.list_sessions(app_id=app_id, limit=limit)
    return {
        "app_id": app_id,
        "sessions": [
            {
                "session_id": item.session_id,
                "app_id": item.app_id,
                "title": item.title,
                "preview": item.preview,
                "message_count": item.message_count,
                "updated_at": item.updated_at,
            }
            for item in sessions
        ],
    }
