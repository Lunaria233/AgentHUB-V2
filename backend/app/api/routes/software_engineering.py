from __future__ import annotations

import json
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.platform.runtime.orchestrator import get_orchestrator


router = APIRouter()


class SoftwareEngineeringRequest(BaseModel):
    session_id: str
    task: str = Field(min_length=2)
    mode: str = Field(default="requirement_to_code")
    user_id: str | None = None
    verify_command: str = Field(default="")
    allow_modify_tests: bool = Field(default=False)
    allow_install_dependency: bool = Field(default=False)
    max_iterations: int = Field(default=4, ge=1, le=12)
    allow_network: bool = Field(default=False)
    working_directory: str = Field(default="")


class SoftwareEngineeringResponse(BaseModel):
    session_id: str
    app_id: str
    status: str
    final_report: str


def _sse(events: Iterator[dict[str, object]]) -> Iterator[str]:
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _to_runtime_payload(request: SoftwareEngineeringRequest) -> str:
    payload: dict[str, Any] = {
        "task": request.task,
        "mode": request.mode,
        "verify_command": request.verify_command,
        "allow_modify_tests": request.allow_modify_tests,
        "allow_install_dependency": request.allow_install_dependency,
        "max_iterations": request.max_iterations,
        "allow_network": request.allow_network,
    }
    if request.working_directory.strip():
        payload["working_directory"] = request.working_directory.strip()
    return json.dumps(payload, ensure_ascii=False)


@router.post("", response_model=SoftwareEngineeringResponse)
def run_software_engineering(request: SoftwareEngineeringRequest) -> SoftwareEngineeringResponse:
    orchestrator = get_orchestrator()
    result = orchestrator.run_app(
        app_id="software_engineering",
        session_id=request.session_id,
        user_input=_to_runtime_payload(request),
        user_id=request.user_id,
    )
    return SoftwareEngineeringResponse(
        session_id=request.session_id,
        app_id="software_engineering",
        status=str(result.get("status", "failed")),
        final_report=str(result.get("final_report", "")),
    )


@router.post("/stream")
def stream_software_engineering(request: SoftwareEngineeringRequest) -> StreamingResponse:
    orchestrator = get_orchestrator()
    stream = orchestrator.stream_app(
        app_id="software_engineering",
        session_id=request.session_id,
        user_input=_to_runtime_payload(request),
        user_id=request.user_id,
    )
    return StreamingResponse(_sse(stream), media_type="text/event-stream")


@router.get("/history")
def list_se_history(limit: int = Query(default=30, ge=1, le=200)) -> dict[str, object]:
    orchestrator = get_orchestrator()
    return {"runs": orchestrator.se_run_store.list_runs(limit=limit)}


@router.get("/history/{session_id}")
def get_se_history(session_id: str) -> dict[str, object]:
    orchestrator = get_orchestrator()
    record = orchestrator.se_run_store.get_run(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Software engineering record not found")
    return record

