from __future__ import annotations

import json
from typing import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.platform.runtime.orchestrator import get_orchestrator


router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)
    user_id: str = Field(min_length=1)


class ChatResponse(BaseModel):
    session_id: str
    app_id: str
    answer: str


def _sse(events: Iterator[dict[str, object]]) -> Iterator[str]:
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("", response_model=ChatResponse)
def run_chat(request: ChatRequest) -> ChatResponse:
    orchestrator = get_orchestrator()
    result = orchestrator.run_app(
        app_id="chat",
        session_id=request.session_id,
        user_input=request.message,
        user_id=request.user_id,
    )
    return ChatResponse(
        session_id=request.session_id,
        app_id="chat",
        answer=str(result.get("answer", "")),
    )


@router.post("/stream")
def stream_chat(request: ChatRequest) -> StreamingResponse:
    orchestrator = get_orchestrator()
    stream = orchestrator.stream_app(
        app_id="chat",
        session_id=request.session_id,
        user_input=request.message,
        user_id=request.user_id,
    )
    return StreamingResponse(_sse(stream), media_type="text/event-stream")
