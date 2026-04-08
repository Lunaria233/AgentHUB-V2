from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class SEState(StrEnum):
    INIT = "INIT"
    PLANNING = "PLANNING"
    RETRIEVING = "RETRIEVING"
    CODING = "CODING"
    RUNNING = "RUNNING"
    DIAGNOSING = "DIAGNOSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class SETaskMode(StrEnum):
    REQUIREMENT_TO_CODE = "requirement_to_code"
    FEEDBACK_TO_FIX = "feedback_to_fix"


@dataclass(slots=True)
class SEConstraints:
    verify_command: str
    verify_command_user_supplied: bool = False
    allow_modify_tests: bool = False
    allow_install_dependency: bool = False
    allow_network: bool = False
    max_iterations: int = 4
    working_directory: str = ""


@dataclass(slots=True)
class PlannedStep:
    title: str
    detail: str


@dataclass(slots=True)
class TaskPlan:
    goal: str
    summary: str
    modules: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    verify_command: str = ""
    steps: list[PlannedStep] = field(default_factory=list)


@dataclass(slots=True)
class RetrievedSnippet:
    source: str
    content: str
    reason: str = ""


@dataclass(slots=True)
class PatchChange:
    path: str
    mode: str
    summary: str
    diff_preview: str = ""


@dataclass(slots=True)
class ExecutionRecord:
    iteration: int
    command: str
    exit_code: int
    duration_seconds: float
    stdout: str
    stderr: str
    installed_dependencies: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def summary(self) -> str:
        status = "ok" if self.exit_code == 0 else "failed"
        return f"{status} | code={self.exit_code} | {self.command}"


@dataclass(slots=True)
class Diagnosis:
    next_state: SEState
    reason: str
    failure_type: str = ""
    proposed_action: str = ""


@dataclass(slots=True)
class Blackboard:
    session_id: str
    app_id: str
    user_id: str | None
    mode: SETaskMode
    task_goal: str
    constraints: SEConstraints
    state: SEState = SEState.INIT
    iteration: int = 0
    plan: TaskPlan | None = None
    retrieved_context: list[RetrievedSnippet] = field(default_factory=list)
    patch_history: list[PatchChange] = field(default_factory=list)
    execution_history: list[ExecutionRecord] = field(default_factory=list)
    diagnosis_history: list[Diagnosis] = field(default_factory=list)
    failed_attempts: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    final_result: str = ""
    final_report: str = ""

    def latest_execution(self) -> ExecutionRecord | None:
        return self.execution_history[-1] if self.execution_history else None

    def latest_diagnosis(self) -> Diagnosis | None:
        return self.diagnosis_history[-1] if self.diagnosis_history else None
