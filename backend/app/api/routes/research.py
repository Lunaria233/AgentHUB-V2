from __future__ import annotations

import json
from typing import Iterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.platform.runtime.orchestrator import get_orchestrator


router = APIRouter()


class ResearchRequest(BaseModel):
    session_id: str
    topic: str = Field(min_length=2)
    user_id: str | None = None


class ResearchResponse(BaseModel):
    session_id: str
    app_id: str
    report: str


def _sse(events: Iterator[dict[str, object]]) -> Iterator[str]:
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("", response_model=ResearchResponse)
def run_research(request: ResearchRequest) -> ResearchResponse:
    orchestrator = get_orchestrator()
    result = orchestrator.run_app(
        app_id="deep_research",
        session_id=request.session_id,
        user_input=request.topic,
        user_id=request.user_id,
    )
    return ResearchResponse(
        session_id=request.session_id,
        app_id="deep_research",
        report=str(result.get("report", "")),
    )


@router.post("/stream")
def stream_research(request: ResearchRequest) -> StreamingResponse:
    orchestrator = get_orchestrator()
    stream = orchestrator.stream_app(
        app_id="deep_research",
        session_id=request.session_id,
        user_input=request.topic,
        user_id=request.user_id,
    )
    return StreamingResponse(_sse(stream), media_type="text/event-stream")


@router.get("/history")
def list_research_history(limit: int = Query(default=30, ge=1, le=200)) -> dict[str, object]:
    orchestrator = get_orchestrator()
    return {"runs": orchestrator.research_run_store.list_runs(limit=limit)}


@router.get("/history/{session_id}")
def get_research_history(session_id: str) -> dict[str, object]:
    orchestrator = get_orchestrator()
    record = orchestrator.research_run_store.get_run(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Research record not found")
    return record
