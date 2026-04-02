from __future__ import annotations

from fastapi import APIRouter, Body, Query

from app.platform.runtime.orchestrator import get_orchestrator


router = APIRouter()


@router.post("/explain")
def explain_context(
    payload: dict[str, object] = Body(...),
) -> dict[str, object]:
    orchestrator = get_orchestrator()
    return orchestrator.explain_context(
        app_id=str(payload.get("app_id", "chat")),
        stage=str(payload.get("stage", "chat.reply")),
        session_id=str(payload.get("session_id", "context-inspect")),
        user_id=str(payload.get("user_id")) if payload.get("user_id") else None,
        user_input=str(payload.get("user_input", "")),
    )


@router.get("/eval")
def run_context_eval() -> dict[str, object]:
    orchestrator = get_orchestrator()
    return orchestrator.run_context_eval()
