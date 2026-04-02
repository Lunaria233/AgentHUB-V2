from __future__ import annotations

from app.platform.runtime.agent import BaseAgentRuntime
from app.platform.runtime.events import EventEmitter


class WorkflowAgentRuntime(BaseAgentRuntime):
    def __init__(self) -> None:
        self.events = EventEmitter()

    def run(self, *, user_input: str) -> dict[str, object]:
        events = list(self.stream(user_input=user_input))
        return dict(events[-1]) if events else {}
