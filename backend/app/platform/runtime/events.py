from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    MESSAGE_CHUNK = "message_chunk"
    MESSAGE_DONE = "message_done"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATUS = "status"
    CITATION = "citation"
    ERROR = "error"
    DONE = "done"


@dataclass(slots=True)
class RunEvent:
    event_type: EventType
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.event_type.value, **self.payload}


class EventEmitter:
    def emit(self, event_type: EventType, **payload: Any) -> dict[str, Any]:
        return RunEvent(event_type=event_type, payload=payload).as_dict()
