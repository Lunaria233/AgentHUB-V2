from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ResearchTask:
    task_id: int
    title: str
    query: str
    goal: str
    summary: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    note_id: str | None = None


@dataclass(slots=True)
class ResearchState:
    topic: str
    tasks: list[ResearchTask] = field(default_factory=list)
    report: str = ""
