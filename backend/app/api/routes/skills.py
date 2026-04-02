from __future__ import annotations

from fastapi import APIRouter, Query

from app.platform.runtime.orchestrator import get_orchestrator


router = APIRouter()


@router.get("/catalog")
def list_skill_catalog() -> dict[str, object]:
    orchestrator = get_orchestrator()
    return {"skills": orchestrator.list_skills()}


@router.post("/reload")
def reload_skills() -> dict[str, object]:
    orchestrator = get_orchestrator()
    return orchestrator.reload_skills()


@router.get("/resolve")
def resolve_app_skills(
    app_id: str = Query(...),
    stage: str = Query("default"),
    session_id: str = Query("skill-inspect"),
    user_id: str | None = Query(default=None),
) -> dict[str, object]:
    orchestrator = get_orchestrator()
    return {
        "app_id": app_id,
        "stage": stage,
        "skills": orchestrator.describe_app_skills(app_id=app_id, stage=stage, session_id=session_id, user_id=user_id),
    }


@router.get("/bindings")
def get_app_skill_bindings(
    app_id: str = Query(...),
) -> dict[str, object]:
    orchestrator = get_orchestrator()
    return orchestrator.describe_app_skill_bindings(app_id=app_id)


@router.get("/eval")
def run_skills_eval() -> dict[str, object]:
    orchestrator = get_orchestrator()
    return orchestrator.run_skills_eval()
