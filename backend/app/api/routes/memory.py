from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.platform.memory.evaluation import MemoryEvaluator, isolated_memory_service
from app.platform.runtime.orchestrator import get_orchestrator


router = APIRouter()


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    app_id: str = Field(min_length=1)
    session_id: str | None = None
    user_id: str | None = None
    limit: int = Field(default=10, ge=1, le=100)
    include_graph: bool = True
    retrieval_mode: str = "hybrid"


@router.get("/status")
def get_memory_status() -> dict[str, object]:
    orchestrator = get_orchestrator()
    return {
        "memory_backend": orchestrator.settings.memory_backend,
        "extraction_mode": orchestrator.settings.memory_extraction_mode,
        "embedding_mode": orchestrator.settings.memory_embedding_mode,
        "vector_backend": {
            "enabled": bool(orchestrator.memory_vector_index and orchestrator.memory_vector_index.enabled),
            "collection": orchestrator.memory_vector_index.collection if orchestrator.memory_vector_index else "",
            "base_url": orchestrator.memory_vector_index.base_url if orchestrator.memory_vector_index else "",
        },
        "graph_backend": {
            "enabled": bool(orchestrator.memory_graph_backend and orchestrator.memory_graph_backend.enabled),
            "active_uri": getattr(orchestrator.memory_graph_backend, "active_uri", ""),
        },
        "llm_extraction": {
            "configured_model": orchestrator.settings.llm_model,
            "configured": bool(orchestrator.settings.llm_api_key),
        },
    }


@router.get("/summary")
def get_memory_summary(
    app_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> dict[str, object]:
    orchestrator = get_orchestrator()
    return {
        "app_id": app_id,
        "user_id": user_id,
        "summary": orchestrator.memory_service.summarize_memory(app_id=app_id, user_id=user_id),
    }


@router.get("/records")
def list_memory_records(
    app_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    memory_type: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    orchestrator = get_orchestrator()
    memory_types = [memory_type] if memory_type else None
    records = orchestrator.memory_service.list_memories(
        app_id=app_id,
        session_id=session_id,
        user_id=user_id,
        memory_types=memory_types,
        include_archived=include_archived,
        limit=limit,
    )
    return {"records": records}


@router.post("/search")
def search_memories(request: MemorySearchRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    app_manifest = orchestrator.app_registry.get(request.app_id)
    memory_profile = app_manifest.profiles.memory_profile
    resolved_session_id = request.session_id
    resolved_user_id = request.user_id
    if memory_profile.retrieval_scope == "user":
        if resolved_user_id:
            resolved_session_id = None
        elif resolved_session_id:
            # Fall back to current session only when user identity is unavailable.
            resolved_user_id = None
        else:
            return {"results": []}
    results = orchestrator.memory_service.search_relevant_memories(
        query=request.query,
        app_id=request.app_id,
        session_id=resolved_session_id if memory_profile.retrieval_scope in {"session", "user"} else None,
        user_id=resolved_user_id,
        limit=request.limit,
        memory_types=memory_profile.retrieval_types,
        min_importance=memory_profile.min_importance,
        retrieval_mode=request.retrieval_mode or memory_profile.retrieval_mode,
        include_graph=request.include_graph and memory_profile.graph_enabled,
    )
    return {"results": results}


@router.post("/eval")
def run_memory_eval(app_id: str = Query(default="chat")) -> dict[str, object]:
    orchestrator = get_orchestrator()
    profile = orchestrator.app_registry.get(app_id).profiles.memory_profile
    with isolated_memory_service(orchestrator.memory_service) as eval_service:
        evaluator = MemoryEvaluator(eval_service)
        summary = evaluator.run_default_suite(app_id=app_id, profile=profile)
    return summary.to_dict()
