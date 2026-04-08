from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.apps.software_engineering.archive import SERunStore
from app.apps.software_engineering.models import (
    Blackboard,
    Diagnosis,
    ExecutionRecord,
    PatchChange,
    PlannedStep,
    RetrievedSnippet,
    SEConstraints,
    SEState,
    SETaskMode,
    TaskPlan,
)
from app.apps.software_engineering.prompts import (
    CODER_PROMPT,
    DIAGNOSER_PROMPT,
    FINAL_REPORT_PROMPT,
    PLANNER_PROMPT,
    RETRIEVER_PROMPT,
)
from app.apps.software_engineering.tools import parse_json_payload
from app.platform.apps.profiles import ContextProfile, MemoryProfile, RAGProfile, SkillBinding
from app.platform.capabilities.contracts import BaseCapabilityContext
from app.platform.context.builder import ContextBuilder
from app.platform.context.types import ContextBuildRequest, ContextPacket
from app.platform.core.message import Message, MessageRole
from app.platform.history.service import HistoryService
from app.platform.memory.service import MemoryService
from app.platform.models.base import BaseModelClient, ModelRequest
from app.platform.observability.tracing import TraceService
from app.platform.runtime.agent import BaseAgentRuntime
from app.platform.runtime.events import EventEmitter, EventType
from app.platform.tools.base import ToolContext
from app.platform.tools.executor import ToolExecutor
from app.platform.tools.registry import ToolRegistry


MODULE_NOT_FOUND_PATTERN = re.compile(r"No module named ['\"](?P<module>[A-Za-z0-9_\-\.]+)['\"]")
MAX_STAGE_MCP_ACTIONS = 2
MAX_TOOL_HINTS = 24
DEPENDENCY_PACKAGE_ALIASES: dict[str, str] = {
    "skimage": "scikit-image",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "pil": "Pillow",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
}
PACKAGE_HINT_PATTERNS = (
    re.compile(r"(?:did you mean|maybe you meant)\s+['`\"]?(?P<package>[a-z0-9][a-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"please install\s+['`\"]?(?P<package>[a-z0-9][a-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"pip install\s+['`\"]?(?P<package>[a-z0-9][a-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"install\s+['`\"]?(?P<package>[a-z0-9][a-z0-9._\-]+)\s+to", re.IGNORECASE),
)


class SoftwareEngineeringRuntime(BaseAgentRuntime):
    def __init__(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        model_client: BaseModelClient,
        model_name: str,
        history_service: HistoryService,
        memory_service: MemoryService,
        rag_service,
        context_builder: ContextBuilder,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        trace_service: TraceService,
        context_profiles: dict[str, ContextProfile],
        memory_profile: MemoryProfile,
        rag_profile: RAGProfile,
        skill_runtime,
        skill_bindings: list[SkillBinding],
        run_store: SERunStore,
        repo_root: Path,
        default_max_iterations: int = 4,
    ) -> None:
        self.app_id = app_id
        self.session_id = session_id
        self.user_id = user_id
        self.model_client = model_client
        self.model_name = model_name
        self.history_service = history_service
        self.memory_service = memory_service
        self.rag_service = rag_service
        self.context_builder = context_builder
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.trace_service = trace_service
        self.context_profiles = context_profiles
        self.memory_profile = memory_profile
        self.rag_profile = rag_profile
        self.skill_runtime = skill_runtime
        self.skill_bindings = list(skill_bindings)
        self.run_store = run_store
        self.repo_root = repo_root.resolve()
        self.default_max_iterations = max(2, default_max_iterations)
        self.events = EventEmitter()
        self._last_model_error = ""

    def run(self, *, user_input: str) -> dict[str, object]:
        final_report = ""
        status = "failed"
        for event in self.stream(user_input=user_input):
            if event.get("type") == EventType.MESSAGE_DONE.value and isinstance(event.get("final_report"), str):
                final_report = str(event.get("final_report", ""))
                status = str(event.get("status", status))
        return {"status": status, "final_report": final_report}

    def stream(self, *, user_input: str) -> Iterator[dict[str, object]]:
        trace_id = self.trace_service.new_trace_id()
        request_payload = self._parse_user_input(user_input)
        board = self._build_blackboard(request_payload)
        tool_context = ToolContext(
            app_id=self.app_id,
            session_id=self.session_id,
            user_id=self.user_id,
            trace_id=trace_id,
            metadata={
                "repo_root": board.constraints.working_directory or str(self.repo_root),
                "allow_modify_tests": board.constraints.allow_modify_tests,
                "allow_install_dependency": board.constraints.allow_install_dependency,
                "allow_network": board.constraints.allow_network,
            },
        )
        event_log: list[dict[str, object]] = []

        def emit(event_type: EventType, **payload: object) -> dict[str, object]:
            event = self.events.emit(event_type, **payload)
            event_log.append(dict(event))
            return event

        self.history_service.add_user_message(self.session_id, self.app_id, board.task_goal)
        yield emit(EventType.STATUS, state=board.state.value, agent="Coordinator", iteration=board.iteration, message="Task initialized")

        board.state = SEState.PLANNING
        max_iterations = max(1, board.constraints.max_iterations)

        while board.state not in {SEState.SUCCESS, SEState.FAILED} and board.iteration < max_iterations:
            if board.state == SEState.PLANNING:
                yield from self._run_planner(board=board, trace_id=trace_id, emit=emit)
                continue
            if board.state == SEState.RETRIEVING:
                yield from self._run_retriever(board=board, tool_context=tool_context, trace_id=trace_id, emit=emit)
                continue
            if board.state == SEState.CODING:
                board.iteration += 1
                yield from self._run_coder(board=board, tool_context=tool_context, trace_id=trace_id, emit=emit)
                continue
            if board.state == SEState.RUNNING:
                yield from self._run_executor(board=board, tool_context=tool_context, emit=emit)
                continue
            if board.state == SEState.DIAGNOSING:
                yield from self._run_diagnoser(board=board, tool_context=tool_context, trace_id=trace_id, emit=emit)
                continue
            board.state = SEState.FAILED

        if board.state not in {SEState.SUCCESS, SEState.FAILED}:
            board.state = SEState.FAILED
            board.failed_attempts.append("max_iterations_reached")

        final_report = self._build_final_report(board=board, trace_id=trace_id)
        board.final_report = final_report
        board.final_result = "success" if board.state == SEState.SUCCESS else "failed"
        final_code_files = self._collect_final_code_files(board)
        self.history_service.add_assistant_message(self.session_id, self.app_id, final_report)
        self._remember_task_result(board)
        yield emit(
            EventType.MESSAGE_DONE,
            status=board.state.value.lower(),
            final_result=board.final_result,
            final_report=final_report,
            final_code_files=final_code_files,
            iteration_count=board.iteration,
            patches=[asdict(item) for item in board.patch_history],
            executions=[asdict(item) for item in board.execution_history],
        )
        yield emit(EventType.DONE, status=board.state.value.lower())
        self.run_store.save_run(
            session_id=self.session_id,
            payload={
                "mode": board.mode.value,
                "goal": board.task_goal,
                "status": board.state.value.lower(),
                "constraints": asdict(board.constraints),
                "plan": asdict(board.plan) if board.plan else {},
                "patches": [asdict(item) for item in board.patch_history],
                "executions": [asdict(item) for item in board.execution_history],
                "diagnoses": [asdict(item) for item in board.diagnosis_history],
                "trace": board.trace,
                "events": event_log,
                "final_code_files": final_code_files,
                "iteration_count": board.iteration,
                "final_result": board.final_result,
                "final_report": board.final_report,
            },
        )

    def _run_planner(self, *, board: Blackboard, trace_id: str, emit) -> Iterator[dict[str, object]]:
        skill_context = self._resolve_stage_skill_context("se.plan")
        prompt = self._build_context_prompt(
            profile_id="se.plan",
            system_prompt=PLANNER_PROMPT,
            user_input=(
                f"Task mode: {board.mode.value}\n"
                f"Task goal: {board.task_goal}\n"
                f"Constraints: {json.dumps(asdict(board.constraints), ensure_ascii=False)}\n"
                f"Active skills: {json.dumps(skill_context['skill_ids'], ensure_ascii=False)}\n"
                f"Preferred tools from skills: {json.dumps(skill_context['preferred_tools'], ensure_ascii=False)}\n"
                f"Available tools: {json.dumps(self._summarize_tool_specs(), ensure_ascii=False)}"
            ),
            trace_id=trace_id,
        )
        output = self._generate_text(prompt)
        payload = self._parse_agent_json(output)
        plan = TaskPlan(
            goal=str(payload.get("goal", board.task_goal)),
            summary=str(payload.get("summary", "Plan generated by Planner")).strip(),
            modules=[str(item) for item in payload.get("modules", []) if str(item).strip()],
            constraints=[str(item) for item in payload.get("constraints", []) if str(item).strip()],
            verify_command=str(payload.get("verify_command", board.constraints.verify_command)).strip(),
            steps=[
                PlannedStep(title=str(item.get("title", "Step")), detail=str(item.get("detail", "")))
                for item in payload.get("steps", [])
                if isinstance(item, dict)
            ],
        )
        if not plan.steps:
            plan.steps = [
                PlannedStep(title="Inspect repository context", detail="Identify relevant files, docs, and constraints."),
                PlannedStep(title="Apply minimal patch", detail="Modify only necessary files and keep scope small."),
                PlannedStep(title="Run verification command", detail="Use external command result as acceptance gate."),
            ]
        if plan.verify_command and not board.constraints.verify_command_user_supplied:
            fallback = self._default_verify_command(
                mode=board.mode,
                working_directory=board.constraints.working_directory,
                task_goal=board.task_goal,
            )
            board.constraints.verify_command = self._sanitize_verify_command(
                proposed=plan.verify_command,
                mode=board.mode,
                task_goal=board.task_goal,
                fallback=fallback,
            )
        board.plan = plan
        board.state = SEState.RETRIEVING
        self._remember_task_memory(board, f"Planner summary: {plan.summary}", tags=["se_agent", "planner"])
        self._trace_step(
            board,
            agent="Planner",
            summary=f"{plan.summary} | skills={','.join(skill_context['skill_ids']) or 'none'}",
        )
        yield emit(
            EventType.STATUS,
            state=board.state.value,
            agent="Planner",
            iteration=board.iteration,
            message=plan.summary,
            active_skills=skill_context["skill_ids"],
        )

    def _run_retriever(self, *, board: Blackboard, tool_context: ToolContext, trace_id: str, emit) -> Iterator[dict[str, object]]:
        plan = board.plan or TaskPlan(goal=board.task_goal, summary="", verify_command=board.constraints.verify_command)
        skill_context = self._resolve_stage_skill_context("se.retrieve")
        mcp_tools = self._list_mcp_tool_names()
        prompt = self._build_context_prompt(
            profile_id="se.retrieve",
            system_prompt=RETRIEVER_PROMPT,
            user_input=(
                f"Goal: {board.task_goal}\n"
                f"Plan modules: {', '.join(plan.modules)}\n"
                f"Recent failures: {' | '.join(board.failed_attempts[-3:])}\n"
                f"Active skills: {json.dumps(skill_context['skill_ids'], ensure_ascii=False)}\n"
                f"Preferred tools from skills: {json.dumps(skill_context['preferred_tools'], ensure_ascii=False)}\n"
                f"Available MCP tools: {json.dumps(mcp_tools, ensure_ascii=False)}\n"
                "Generate retrieval hints."
            ),
            trace_id=trace_id,
        )
        output = self._generate_text(prompt)
        payload = self._parse_agent_json(output)
        queries = [str(item).strip() for item in payload.get("queries", []) if str(item).strip()]
        if not queries:
            queries = [board.task_goal]
            if plan.modules:
                queries.append(plan.modules[0])

        snippets: list[RetrievedSnippet] = []
        for query in queries[:3]:
            yield emit(EventType.TOOL_CALL, state=SEState.RETRIEVING.value, agent="Retriever", tool_name="repo_search_tool", arguments={"query": query, "limit": 5})
            result = self.tool_executor.safe_execute_tool("repo_search_tool", {"query": query, "limit": 5}, tool_context)
            yield emit(EventType.TOOL_RESULT, state=SEState.RETRIEVING.value, agent="Retriever", tool_name="repo_search_tool", result=result)
            for item in result.get("results", [])[:3] if isinstance(result, dict) else []:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path", "")).strip()
                if not path:
                    continue
                read_result = self.tool_executor.safe_execute_tool("file_read_tool", {"path": path, "max_chars": 1600}, tool_context)
                content = str(read_result.get("content", "")).strip()
                if not content:
                    continue
                snippets.append(RetrievedSnippet(source=path, content=content[:1600], reason=f"query:{query}"))

        mcp_action_count = 0
        mcp_actions = self._parse_mcp_actions(payload)
        if mcp_actions and mcp_tools:
            for action in mcp_actions[:MAX_STAGE_MCP_ACTIONS]:
                tool_name = action["tool_name"]
                arguments = action["arguments"]
                purpose = action["purpose"]
                yield emit(
                    EventType.TOOL_CALL,
                    state=SEState.RETRIEVING.value,
                    agent="Retriever",
                    tool_name=tool_name,
                    arguments=arguments,
                )
                result = self.tool_executor.safe_execute_tool(tool_name, arguments, tool_context)
                yield emit(
                    EventType.TOOL_RESULT,
                    state=SEState.RETRIEVING.value,
                    agent="Retriever",
                    tool_name=tool_name,
                    result=result,
                )
                mcp_action_count += 1
                mcp_text = self._extract_mcp_text(result)
                if mcp_text:
                    snippets.append(
                        RetrievedSnippet(
                            source=tool_name,
                            content=mcp_text[:1600],
                            reason=f"mcp:{purpose or 'extra_context'}",
                        )
                    )

        if self.rag_profile.enabled:
            rag_results = self.rag_service.retrieve(scope=self.app_id, query=board.task_goal, limit=min(3, self.rag_profile.retrieval_limit))
            for item in rag_results:
                snippets.append(
                    RetrievedSnippet(
                        source=str(item.get("title", "rag_chunk")),
                        content=str(item.get("content", "")).strip(),
                        reason="rag_retrieve",
                    )
                )

        board.retrieved_context = snippets[:12]
        board.state = SEState.CODING
        summary = (
            f"Retriever collected {len(board.retrieved_context)} context snippets "
            f"(mcp_actions={mcp_action_count})"
        )
        self._remember_task_memory(board, summary, tags=["se_agent", "retriever"])
        self._trace_step(
            board,
            agent="Retriever",
            summary=f"{summary} | skills={','.join(skill_context['skill_ids']) or 'none'}",
        )
        yield emit(
            EventType.STATUS,
            state=board.state.value,
            agent="Retriever",
            iteration=board.iteration,
            message=summary,
            active_skills=skill_context["skill_ids"],
            mcp_actions=mcp_action_count,
        )

    def _run_coder(self, *, board: Blackboard, tool_context: ToolContext, trace_id: str, emit) -> Iterator[dict[str, object]]:
        plan = board.plan or TaskPlan(goal=board.task_goal, summary="", verify_command=board.constraints.verify_command)
        skill_context = self._resolve_stage_skill_context("se.code")
        context_blocks = "\n\n".join(
            f"[{item.source}] ({item.reason})\n{item.content[:900]}"
            for item in board.retrieved_context[:6]
        )
        prompt = self._build_context_prompt(
            profile_id="se.code",
            system_prompt=CODER_PROMPT,
            user_input=(
                f"Goal: {board.task_goal}\n"
                f"Constraints: {json.dumps(asdict(board.constraints), ensure_ascii=False)}\n"
                f"Plan summary: {plan.summary}\n"
                f"Recent failures: {' | '.join(board.failed_attempts[-3:])}\n\n"
                f"Active skills: {json.dumps(skill_context['skill_ids'], ensure_ascii=False)}\n"
                f"Preferred tools from skills: {json.dumps(skill_context['preferred_tools'], ensure_ascii=False)}\n\n"
                f"Retrieved context:\n{context_blocks}"
            ),
            trace_id=trace_id,
        )
        output = self._generate_text(prompt)
        payload = self._parse_agent_json(output)
        edits = payload.get("edits", [])
        verify_command = str(payload.get("verify_command", "")).strip()
        summary = str(payload.get("summary", "Coder finished patch generation")).strip()
        model_error = self._last_model_error.strip()
        if verify_command and not board.constraints.verify_command_user_supplied:
            fallback = self._default_verify_command(
                mode=board.mode,
                working_directory=board.constraints.working_directory,
                task_goal=board.task_goal,
            )
            board.constraints.verify_command = self._sanitize_verify_command(
                proposed=verify_command,
                mode=board.mode,
                task_goal=board.task_goal,
                fallback=fallback,
            )
        if not isinstance(edits, list):
            edits = []

        if not edits and model_error:
            board.failed_attempts.append(f"model_call_error:{model_error}")
            board.state = SEState.FAILED
            summary = f"Model call failed in Coder: {model_error}"

        # One strict retry for requirement tasks when the model returns no patch payload.
        if board.state != SEState.FAILED and not edits and board.mode == SETaskMode.REQUIREMENT_TO_CODE:
            retry_prompt = (
                f"{prompt}\n\n"
                "Your previous response did not include usable edits.\n"
                "Return strict JSON only with at least one edit.\n"
                "If target file is unknown, write to 'generated/image_metrics.py' with a callable function."
            )
            retry_output = self._generate_text(retry_prompt)
            retry_payload = self._parse_agent_json(retry_output)
            retry_edits = retry_payload.get("edits", [])
            if isinstance(retry_edits, list) and retry_edits:
                edits = retry_edits
                retry_verify = str(retry_payload.get("verify_command", "")).strip()
                if retry_verify and not board.constraints.verify_command_user_supplied:
                    fallback = self._default_verify_command(
                        mode=board.mode,
                        working_directory=board.constraints.working_directory,
                        task_goal=board.task_goal,
                    )
                    board.constraints.verify_command = self._sanitize_verify_command(
                        proposed=retry_verify,
                        mode=board.mode,
                        task_goal=board.task_goal,
                        fallback=fallback,
                    )
                summary = str(retry_payload.get("summary", summary)).strip() or summary
            elif self._last_model_error.strip():
                model_error = self._last_model_error.strip()
                board.failed_attempts.append(f"model_call_error:{model_error}")
                board.state = SEState.FAILED
                summary = f"Model call failed in Coder retry: {model_error}"

        if board.state == SEState.FAILED:
            pass
        elif edits:
            yield emit(EventType.TOOL_CALL, state=SEState.CODING.value, agent="Coder", tool_name="patch_write_tool", arguments={"files": edits})
            patch_result = self.tool_executor.safe_execute_tool("patch_write_tool", {"files": edits}, tool_context)
            yield emit(EventType.TOOL_RESULT, state=SEState.CODING.value, agent="Coder", tool_name="patch_write_tool", result=patch_result)
            for item in patch_result.get("applied", []) if isinstance(patch_result, dict) else []:
                if not isinstance(item, dict):
                    continue
                board.patch_history.append(
                    PatchChange(
                        path=str(item.get("path", "")),
                        mode=str(item.get("mode", "replace")),
                        summary=str(item.get("summary", "")).strip() or str(payload.get("summary", "Patch applied")),
                        diff_preview=str(item.get("diff_preview", "")),
                    )
                )
            board.state = SEState.RUNNING
        else:
            board.failed_attempts.append("coder_returned_no_edits")
            # Avoid running identical verification command repeatedly with zero edits.
            board.state = SEState.RETRIEVING
        self._remember_task_memory(board, f"Coder summary: {summary}", tags=["se_agent", "coder"])
        self._trace_step(
            board,
            agent="Coder",
            summary=f"{summary} | skills={','.join(skill_context['skill_ids']) or 'none'}",
        )
        yield emit(
            EventType.STATUS,
            state=board.state.value,
            agent="Coder",
            iteration=board.iteration,
            message=summary if edits else f"{summary} (no edits, routing back to retrieval)",
            active_skills=skill_context["skill_ids"],
        )

    def _run_executor(self, *, board: Blackboard, tool_context: ToolContext, emit) -> Iterator[dict[str, object]]:
        command = board.constraints.verify_command.strip()
        if not command:
            board.state = SEState.FAILED
            board.failed_attempts.append("missing_verify_command")
            yield emit(EventType.ERROR, state=board.state.value, agent="Executor", message="verify_command is required")
            return

        arguments: dict[str, Any] = {"command": command, "timeout_seconds": 240}
        if board.constraints.working_directory:
            arguments["cwd"] = "."
        yield emit(EventType.TOOL_CALL, state=SEState.RUNNING.value, agent="Executor", tool_name="command_run_tool", arguments=arguments)
        result = self.tool_executor.safe_execute_tool("command_run_tool", arguments, tool_context)
        yield emit(EventType.TOOL_RESULT, state=SEState.RUNNING.value, agent="Executor", tool_name="command_run_tool", result=result)
        record = ExecutionRecord(
            iteration=board.iteration,
            command=command,
            exit_code=int(result.get("exit_code", -1)),
            duration_seconds=float(result.get("duration_seconds", 0.0)),
            stdout=str(result.get("stdout", "")),
            stderr=str(result.get("stderr", "")),
        )
        board.execution_history.append(record)

        package = self._extract_missing_dependency(board=board, stderr=record.stderr)
        if package:
            candidates = self._build_dependency_candidates(package)
            attempted: set[str] = set()
            installed_package = ""

            # Prefer MCP dependency install tools when available.
            for mcp_tool_name in self._list_mcp_dependency_install_tools():
                if installed_package:
                    break
                for candidate in candidates:
                    lowered_candidate = candidate.lower()
                    if lowered_candidate in attempted:
                        continue
                    attempted.add(lowered_candidate)
                    mcp_arguments = self._build_mcp_dependency_install_arguments(mcp_tool_name, candidate)
                    if not mcp_arguments:
                        continue
                    yield emit(
                        EventType.TOOL_CALL,
                        state=SEState.RUNNING.value,
                        agent="Executor",
                        tool_name=mcp_tool_name,
                        arguments=mcp_arguments,
                    )
                    mcp_result = self.tool_executor.safe_execute_tool(mcp_tool_name, mcp_arguments, tool_context)
                    yield emit(
                        EventType.TOOL_RESULT,
                        state=SEState.RUNNING.value,
                        agent="Executor",
                        tool_name=mcp_tool_name,
                        result=mcp_result,
                    )
                    if self._is_install_result_success(mcp_result):
                        installed_package = candidate
                        break
                    hint = self._extract_package_hint_from_result(mcp_result)
                    if hint and hint.lower() not in attempted and hint.lower() not in {item.lower() for item in candidates}:
                        candidates.append(hint)

            # Fallback to local dependency tool when MCP path is unavailable/failed.
            if not installed_package:
                for candidate in candidates:
                    lowered_candidate = candidate.lower()
                    if lowered_candidate in attempted:
                        continue
                    attempted.add(lowered_candidate)
                    yield emit(
                        EventType.TOOL_CALL,
                        state=SEState.RUNNING.value,
                        agent="Executor",
                        tool_name="dependency_tool",
                        arguments={"package": candidate},
                    )
                    dep_result = self.tool_executor.safe_execute_tool("dependency_tool", {"package": candidate}, tool_context)
                    yield emit(
                        EventType.TOOL_RESULT,
                        state=SEState.RUNNING.value,
                        agent="Executor",
                        tool_name="dependency_tool",
                        result=dep_result,
                    )
                    if bool(dep_result.get("ok")):
                        installed_package = candidate
                        break
                    hint = self._extract_package_hint_from_result(dep_result)
                    if hint and hint.lower() not in attempted and hint.lower() not in {item.lower() for item in candidates}:
                        candidates.append(hint)

            if installed_package:
                record.installed_dependencies.append(installed_package)
                board.state = SEState.RUNNING
                self._trace_step(board, agent="Executor", summary=f"Dependency fix attempted: {installed_package}")
                yield emit(
                    EventType.STATUS,
                    state=board.state.value,
                    agent="Executor",
                    iteration=board.iteration,
                    message=f"Dependency installed ({installed_package}), re-running command",
                )
                return

        if record.exit_code == 0:
            if board.mode == SETaskMode.REQUIREMENT_TO_CODE and not board.patch_history:
                board.state = SEState.RETRIEVING
                board.failed_attempts.append("verify_passed_but_no_code_change")
                self._trace_step(board, agent="Executor", summary="Verification passed but no code change detected")
                yield emit(
                    EventType.STATUS,
                    state=board.state.value,
                    agent="Executor",
                    iteration=board.iteration,
                    message="Verification passed but no code changes detected, requesting new patch",
                )
                return
            board.state = SEState.SUCCESS
            self._trace_step(board, agent="Executor", summary=record.summary())
            yield emit(EventType.STATUS, state=board.state.value, agent="Executor", iteration=board.iteration, message="Verification passed")
            return

        board.state = SEState.DIAGNOSING
        self._trace_step(board, agent="Executor", summary=record.summary())
        yield emit(EventType.STATUS, state=board.state.value, agent="Executor", iteration=board.iteration, message="Verification failed, routing to Diagnoser")

    def _run_diagnoser(self, *, board: Blackboard, tool_context: ToolContext, trace_id: str, emit) -> Iterator[dict[str, object]]:
        last = board.latest_execution()
        if last is None:
            board.state = SEState.FAILED
            return
        skill_context = self._resolve_stage_skill_context("se.diagnose")
        prompt = self._build_context_prompt(
            profile_id="se.diagnose",
            system_prompt=DIAGNOSER_PROMPT,
            user_input=(
                f"Goal: {board.task_goal}\n"
                f"Exit code: {last.exit_code}\n"
                f"Command: {last.command}\n"
                f"STDOUT:\n{last.stdout[-2000:]}\n\n"
                f"STDERR:\n{last.stderr[-2000:]}\n\n"
                f"Constraints: {json.dumps(asdict(board.constraints), ensure_ascii=False)}\n"
                f"Active skills: {json.dumps(skill_context['skill_ids'], ensure_ascii=False)}"
            ),
            trace_id=trace_id,
        )
        output = self._generate_text(prompt)
        payload = self._parse_agent_json(output)
        mcp_action_count = 0
        mcp_actions = self._parse_mcp_actions(payload)
        if mcp_actions:
            for action in mcp_actions[:MAX_STAGE_MCP_ACTIONS]:
                yield emit(
                    EventType.TOOL_CALL,
                    state=SEState.DIAGNOSING.value,
                    agent="Diagnoser",
                    tool_name=action["tool_name"],
                    arguments=action["arguments"],
                )
                result = self.tool_executor.safe_execute_tool(action["tool_name"], action["arguments"], tool_context)
                yield emit(
                    EventType.TOOL_RESULT,
                    state=SEState.DIAGNOSING.value,
                    agent="Diagnoser",
                    tool_name=action["tool_name"],
                    result=result,
                )
                mcp_action_count += 1
                mcp_text = self._extract_mcp_text(result)
                if mcp_text:
                    board.retrieved_context.append(
                        RetrievedSnippet(
                            source=action["tool_name"],
                            content=mcp_text[:1200],
                            reason=f"mcp_diagnose:{action['purpose'] or 'extra_context'}",
                        )
                    )
        diagnosis = self._resolve_diagnosis(payload=payload, board=board, execution=last)
        board.diagnosis_history.append(diagnosis)
        board.failed_attempts.append(diagnosis.reason)
        board.state = diagnosis.next_state
        self._remember_task_memory(board, f"Diagnosis: {diagnosis.reason}", tags=["se_agent", "diagnoser"])
        self._trace_step(
            board,
            agent="Diagnoser",
            summary=f"{diagnosis.next_state.value}: {diagnosis.reason} | skills={','.join(skill_context['skill_ids']) or 'none'}",
        )
        yield emit(
            EventType.STATUS,
            state=board.state.value,
            agent="Diagnoser",
            iteration=board.iteration,
            message=diagnosis.reason,
            diagnosis={"failure_type": diagnosis.failure_type, "proposed_action": diagnosis.proposed_action},
            active_skills=skill_context["skill_ids"],
            mcp_actions=mcp_action_count,
        )

    def _resolve_diagnosis(self, *, payload: dict[str, Any], board: Blackboard, execution: ExecutionRecord) -> Diagnosis:
        raw_state = str(payload.get("next_state", "")).strip().upper()
        next_state = {
            "RETRIEVING": SEState.RETRIEVING,
            "CODING": SEState.CODING,
            "RUNNING": SEState.RUNNING,
            "SUCCESS": SEState.SUCCESS,
            "FAILED": SEState.FAILED,
        }.get(raw_state)
        if next_state is None:
            next_state = self._heuristic_next_state(board=board, execution=execution)
        reason = str(payload.get("reason", "")).strip() or self._heuristic_reason(execution)
        if next_state == SEState.CODING and self._is_stuck_without_patches(board=board, execution=execution):
            next_state = SEState.RETRIEVING
            reason = f"{reason} (repeated failure without effective patch, forcing retrieval refresh)"
        if self._is_hard_stuck(board=board, execution=execution):
            next_state = SEState.FAILED
            reason = f"{reason} (stopped after repeated identical failures)"
        return Diagnosis(
            next_state=next_state,
            reason=reason,
            failure_type=str(payload.get("failure_type", "")).strip(),
            proposed_action=str(payload.get("proposed_action", "")).strip(),
        )

    @staticmethod
    def _is_stuck_without_patches(*, board: Blackboard, execution: ExecutionRecord) -> bool:
        if len(board.execution_history) < 2:
            return False
        prev = board.execution_history[-2]
        same_exit = prev.exit_code == execution.exit_code
        same_tail = (prev.stderr.strip().splitlines()[-1:] == execution.stderr.strip().splitlines()[-1:])
        return same_exit and same_tail and not board.patch_history

    @staticmethod
    def _is_hard_stuck(*, board: Blackboard, execution: ExecutionRecord) -> bool:
        if len(board.diagnosis_history) < 3:
            return False
        if len(board.execution_history) < 3:
            return False
        tails = []
        for item in board.execution_history[-3:]:
            tail = item.stderr.strip().splitlines()[-1] if item.stderr.strip().splitlines() else ""
            tails.append((item.exit_code, tail))
        return len(set(tails)) == 1 and not board.patch_history

    @staticmethod
    def _heuristic_next_state(*, board: Blackboard, execution: ExecutionRecord) -> SEState:
        if execution.exit_code == 0:
            return SEState.SUCCESS
        stderr_lower = execution.stderr.lower()
        if "no module named" in stderr_lower and board.constraints.allow_install_dependency:
            return SEState.RUNNING
        if "syntaxerror" in stderr_lower or "assert" in stderr_lower or "traceback" in stderr_lower:
            return SEState.CODING
        if "file not found" in stderr_lower or "not found" in stderr_lower:
            return SEState.RETRIEVING
        return SEState.CODING

    @staticmethod
    def _heuristic_reason(execution: ExecutionRecord) -> str:
        if execution.exit_code == 0:
            return "External verification command passed"
        if execution.stderr.strip():
            return execution.stderr.strip().splitlines()[-1][:240]
        return f"Command failed with exit code {execution.exit_code}"

    def _extract_missing_dependency(self, *, board: Blackboard, stderr: str) -> str:
        if not board.constraints.allow_install_dependency:
            return ""
        if not board.constraints.allow_network:
            return ""
        match = MODULE_NOT_FOUND_PATTERN.search(stderr or "")
        if not match:
            return ""
        module_name = match.group("module").strip()
        if "." in module_name:
            module_name = module_name.split(".", 1)[0]
        return module_name

    @staticmethod
    def _build_dependency_candidates(module_name: str) -> list[str]:
        raw = module_name.strip()
        if not raw:
            return []
        lower = raw.lower()
        candidates = [raw]
        if lower in DEPENDENCY_PACKAGE_ALIASES:
            candidates.append(DEPENDENCY_PACKAGE_ALIASES[lower])
        if "_" in raw:
            candidates.append(raw.replace("_", "-"))
        deduped: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            normalized = item.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped

    def _build_final_report(self, *, board: Blackboard, trace_id: str) -> str:
        latest_exec = board.latest_execution()
        summary = {
            "goal": board.task_goal,
            "mode": board.mode.value,
            "status": board.state.value,
            "iterations": board.iteration,
            "patch_count": len(board.patch_history),
            "latest_execution": asdict(latest_exec) if latest_exec else {},
            "latest_diagnosis": asdict(board.latest_diagnosis()) if board.latest_diagnosis() else {},
        }
        prompt = self._build_context_prompt(
            profile_id="se.report",
            system_prompt=FINAL_REPORT_PROMPT,
            user_input=f"Create final report from this run summary:\n{json.dumps(summary, ensure_ascii=False, indent=2)}",
            trace_id=trace_id,
        )
        response = self._generate_text(prompt).strip()
        if response:
            return response
        return (
            f"Status: {board.state.value}\n"
            f"Goal: {board.task_goal}\n"
            f"Iterations: {board.iteration}\n"
            f"Patches: {len(board.patch_history)}\n"
            f"Latest verify: {latest_exec.summary() if latest_exec else 'n/a'}"
        )

    def _build_context_prompt(
        self,
        *,
        profile_id: str,
        system_prompt: str,
        user_input: str,
        trace_id: str,
        inline_packets: list[ContextPacket] | None = None,
    ) -> str:
        profile = self._get_context_profile(profile_id)
        result = self.context_builder.build(
            ContextBuildRequest(
                app_id=self.app_id,
                session_id=self.session_id,
                user_id=self.user_id,
                user_input=user_input,
                system_prompt=system_prompt,
                profile=profile.profile_id,
                max_tokens=profile.max_tokens,
                history_limit=profile.history_limit,
                knowledge_scopes=profile.knowledge_scopes or [self.app_id],
                provider_order=profile.provider_order,
                inline_packets=inline_packets or [],
                metadata={
                    "trace_id": trace_id,
                    "memory_scope": self.memory_profile.retrieval_scope or profile.memory_scope,
                    "memory_limit": self.memory_profile.retrieval_limit,
                    "memory_types": self.memory_profile.retrieval_types,
                    "memory_min_importance": self.memory_profile.min_importance,
                    "memory_retrieval_mode": self.memory_profile.retrieval_mode,
                    "memory_include_graph": self.memory_profile.graph_enabled,
                    "rag_limit": self.rag_profile.retrieval_limit,
                    "rag_retrieval_mode": self.rag_profile.retrieval_mode,
                    "rag_include_public": self.rag_profile.include_public,
                    "rag_include_app_shared": self.rag_profile.include_app_shared,
                    "rag_include_user_private": self.rag_profile.include_user_private,
                    "rag_include_session_temporary": self.rag_profile.include_session_temporary,
                    "rag_query_rewrite_enabled": self.rag_profile.query_rewrite_enabled,
                    "rag_query_rewrite_mode": self.rag_profile.query_rewrite_mode,
                    "rag_mqe_variants": self.rag_profile.mqe_variants,
                    "rag_hyde_enabled": self.rag_profile.hyde_enabled,
                    "rag_hyde_mode": self.rag_profile.hyde_mode,
                    "rag_rerank_enabled": self.rag_profile.rerank_enabled,
                    "rag_rerank_strategy": self.rag_profile.rerank_strategy,
                    "rag_rerank_top_n": self.rag_profile.rerank_top_n,
                    "note_scope": profile.note_scope,
                },
            )
        )
        self.trace_service.log_event(
            trace_id=trace_id,
            event_type="context_build",
            payload={
                "app_id": self.app_id,
                "profile": profile.profile_id,
                "packet_count": len(result.packets),
                "max_tokens": profile.max_tokens,
            },
        )
        fragments = [result.prompt]
        if self.skill_bindings:
            fragments = self.skill_runtime.apply(
                BaseCapabilityContext(
                    app_id=self.app_id,
                    session_id=self.session_id,
                    user_id=self.user_id,
                    stage=profile.profile_id,
                ),
                prompt_fragments=fragments,
                bindings=self.skill_bindings,
                available_tool_names={tool.name for tool in self.tool_registry.list_tools()},
            )
        return "\n\n".join(part for part in fragments if part and part.strip())

    def _generate_text(self, prompt: str) -> str:
        self._last_model_error = ""
        request = ModelRequest(
            model=self.model_name,
            messages=[
                Message(role=MessageRole.SYSTEM, content="You are a pragmatic software engineering assistant.").to_openai_dict(),
                Message(role=MessageRole.USER, content=prompt).to_openai_dict(),
            ],
            temperature=0.1,
            max_tokens=1400,
        )
        try:
            response = self.model_client.generate(request)
            return response.text
        except Exception as exc:
            self._last_model_error = str(exc).strip()[:600]
            return ""

    @staticmethod
    def _parse_agent_json(text: str) -> dict[str, Any]:
        parsed = parse_json_payload(text)
        if parsed:
            return parsed
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return parse_json_payload(text[start : end + 1])
        return {}

    def _resolve_stage_skill_context(self, stage: str) -> dict[str, list[str]]:
        if not self.skill_bindings:
            return {"skill_ids": [], "preferred_tools": []}
        resolved = self.skill_runtime.resolve(
            BaseCapabilityContext(
                app_id=self.app_id,
                session_id=self.session_id,
                user_id=self.user_id,
                stage=stage,
            ),
            bindings=self.skill_bindings,
            available_tool_names={tool.name for tool in self.tool_registry.list_tools()},
        )
        skill_ids = [item.skill_id for item in resolved]
        preferred_tools: list[str] = []
        for item in resolved:
            preferred_tools.extend(item.tool_names)
        return {
            "skill_ids": list(dict.fromkeys(skill_ids)),
            "preferred_tools": list(dict.fromkeys(preferred_tools)),
        }

    def _summarize_tool_specs(self) -> list[dict[str, object]]:
        specs: list[dict[str, object]] = []
        for tool in self.tool_registry.list_tools()[:MAX_TOOL_HINTS]:
            specs.append(
                {
                    "name": tool.name,
                    "description": tool.description[:160],
                    "params": [param.name for param in tool.parameters()[:8]],
                }
            )
        return specs

    def _list_mcp_tool_names(self) -> list[str]:
        return sorted(tool.name for tool in self.tool_registry.list_tools() if tool.name.startswith("mcp_"))

    def _list_mcp_dependency_install_tools(self) -> list[str]:
        names: list[str] = []
        for tool in self.tool_registry.list_tools():
            if not tool.name.startswith("mcp_"):
                continue
            lowered = tool.name.lower()
            if lowered.endswith("_install_package") or "install_package" in lowered:
                names.append(tool.name)
        return sorted(dict.fromkeys(names))

    def _build_mcp_dependency_install_arguments(self, tool_name: str, package: str) -> dict[str, Any]:
        tool = self.tool_registry.get(tool_name)
        if tool is None:
            return {}
        params = tool.parameters()
        if not params:
            return {}
        arguments: dict[str, Any] = {}
        names = [item.name for item in params]
        if "package_name" in names:
            arguments["package_name"] = package
        elif "package" in names:
            arguments["package"] = package
        else:
            required = [item for item in params if item.required]
            target = required[0].name if required else params[0].name
            arguments[target] = package
        return arguments

    @staticmethod
    def _is_install_result_success(result: dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            return False
        if not bool(result.get("ok")):
            return False
        text = str(result.get("text", "")).strip()
        if not text:
            text = SoftwareEngineeringRuntime._extract_mcp_text(result)
        lowered = text.lower()
        if text:
            failure_markers = [
                "error",
                "failed",
                "exception",
                "traceback",
                "not found",
                "please install",
                "no module named",
                "module not found",
                "no matching distribution found",
            ]
            if any(marker in lowered for marker in failure_markers):
                return False
        return True

    @staticmethod
    def _extract_package_hint_from_result(result: dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return ""
        chunks: list[str] = []
        for key in ("text", "stdout", "stderr"):
            value = str(result.get(key, "")).strip()
            if value:
                chunks.append(value)
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type", "")).strip() != "text":
                    continue
                text = str(item.get("text", "")).strip()
                if text:
                    chunks.append(text)
        raw = result.get("raw")
        if isinstance(raw, dict):
            content = raw.get("content")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("type", "")).strip() != "text":
                        continue
                    text = str(item.get("text", "")).strip()
                    if text:
                        chunks.append(text)
        merged = "\n".join(chunks)
        if not merged:
            return ""
        lowered = merged.lower()
        for pattern in PACKAGE_HINT_PATTERNS:
            match = pattern.search(lowered)
            if not match:
                continue
            package = str(match.group("package")).strip()
            if package:
                return package
        return ""

    def _parse_mcp_actions(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_actions = payload.get("mcp_actions", [])
        if not isinstance(raw_actions, list):
            return []
        allowed = set(self._list_mcp_tool_names())
        actions: list[dict[str, Any]] = []
        for item in raw_actions:
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name", "")).strip()
            if not tool_name.startswith("mcp_"):
                continue
            if tool_name not in allowed:
                continue
            arguments = item.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            actions.append(
                {
                    "tool_name": tool_name,
                    "arguments": dict(arguments),
                    "purpose": str(item.get("purpose", "")).strip(),
                }
            )
            if len(actions) >= MAX_STAGE_MCP_ACTIONS:
                break
        return actions

    @staticmethod
    def _extract_mcp_text(result: dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return ""
        direct_text = str(result.get("text", "")).strip()
        if direct_text:
            return direct_text
        structured = result.get("structured_content")
        if structured is not None:
            try:
                rendered = json.dumps(structured, ensure_ascii=False)
            except Exception:
                rendered = str(structured)
            if rendered.strip():
                return rendered
        content = result.get("content")
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type", "")).strip() == "text":
                    text = str(item.get("text", "")).strip()
                    if text:
                        text_parts.append(text)
            if text_parts:
                return "\n".join(text_parts)
        raw = result.get("raw")
        if isinstance(raw, dict):
            raw_content = raw.get("content")
            if isinstance(raw_content, list):
                text_parts: list[str] = []
                for item in raw_content:
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("type", "")).strip() == "text":
                        text = str(item.get("text", "")).strip()
                        if text:
                            text_parts.append(text)
                if text_parts:
                    return "\n".join(text_parts)
        return ""

    def _build_blackboard(self, payload: dict[str, Any]) -> Blackboard:
        mode_raw = str(payload.get("mode", SETaskMode.REQUIREMENT_TO_CODE.value)).strip().lower()
        if mode_raw not in {SETaskMode.REQUIREMENT_TO_CODE.value, SETaskMode.FEEDBACK_TO_FIX.value}:
            mode_raw = SETaskMode.REQUIREMENT_TO_CODE.value
        task_goal = str(payload.get("task", "")).strip()
        if not task_goal:
            task_goal = "Analyze repository task and produce verified code changes."
        working_directory = str(payload.get("working_directory", "")).strip() or str(self.repo_root)
        mode = SETaskMode(mode_raw)
        raw_verify_command = str(payload.get("verify_command", "")).strip()
        verify_command_user_supplied = bool(raw_verify_command)
        verify_command = raw_verify_command
        if not verify_command:
            verify_command = self._default_verify_command(mode=mode, working_directory=working_directory, task_goal=task_goal)
        constraints = SEConstraints(
            verify_command=verify_command,
            verify_command_user_supplied=verify_command_user_supplied,
            allow_modify_tests=bool(payload.get("allow_modify_tests", False)),
            allow_install_dependency=bool(payload.get("allow_install_dependency", False)),
            allow_network=bool(payload.get("allow_network", False)),
            max_iterations=max(1, int(payload.get("max_iterations", self.default_max_iterations))),
            working_directory=working_directory,
        )
        return Blackboard(
            session_id=self.session_id,
            app_id=self.app_id,
            user_id=self.user_id,
            mode=mode,
            task_goal=task_goal,
            constraints=constraints,
        )

    @staticmethod
    def _default_verify_command(*, mode: SETaskMode, working_directory: str, task_goal: str) -> str:
        _ = working_directory
        task_lower = task_goal.lower()
        if mode == SETaskMode.FEEDBACK_TO_FIX:
            return 'python -m unittest discover -s tests -p "test_*.py"'
        if any(keyword in task_lower for keyword in ("test", "failing", "bug", "error", "修复", "报错")):
            return 'python -m unittest discover -s tests -p "test_*.py"'
        return "python -m compileall ."

    @staticmethod
    def _sanitize_verify_command(*, proposed: str, mode: SETaskMode, task_goal: str, fallback: str) -> str:
        command = proposed.strip()
        if not command:
            return fallback
        if mode == SETaskMode.FEEDBACK_TO_FIX:
            return command
        lower = command.lower()
        task_lower = task_goal.lower()
        fix_like_goal = any(keyword in task_lower for keyword in ("test", "failing", "bug", "error", "修复", "报错"))
        if ("unittest discover" in lower or "pytest" in lower) and not fix_like_goal:
            return fallback
        return command

    def _collect_final_code_files(self, board: Blackboard) -> list[dict[str, str]]:
        if not board.patch_history:
            return []
        workspace_root = Path(board.constraints.working_directory or str(self.repo_root)).resolve()
        unique_paths: list[str] = list(dict.fromkeys(item.path for item in board.patch_history if item.path))
        files: list[dict[str, str]] = []
        for relative_path in unique_paths:
            target = (workspace_root / relative_path).resolve()
            if workspace_root not in target.parents and target != workspace_root:
                continue
            if not target.exists() or not target.is_file():
                continue
            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            files.append(
                {
                    "path": relative_path.replace("\\", "/"),
                    "content": content[:20000],
                }
            )
            if len(files) >= 10:
                break
        return files

    @staticmethod
    def _parse_user_input(user_input: str) -> dict[str, Any]:
        parsed = parse_json_payload(user_input)
        if parsed:
            return parsed
        return {"mode": "requirement_to_code", "task": user_input}

    def _remember_task_memory(self, board: Blackboard, content: str, *, tags: list[str]) -> None:
        if not self.memory_profile.enabled:
            return
        self.memory_service.remember_working_memory(
            app_id=self.app_id,
            session_id=self.session_id,
            user_id=self.user_id,
            content=content,
            importance=0.65,
            tags=tags,
            profile=self.memory_profile,
            source_kind="se_task",
        )

    def _remember_task_result(self, board: Blackboard) -> None:
        if not self.memory_profile.enabled:
            return
        self.memory_service.remember_fact(
            app_id=self.app_id,
            session_id=self.session_id,
            user_id=self.user_id,
            content=(
                f"Software engineering task completed with status {board.state.value}. "
                f"Goal: {board.task_goal}. Iterations: {board.iteration}. "
                f"Patches: {len(board.patch_history)}."
            ),
            importance=0.9 if board.state == SEState.SUCCESS else 0.75,
            tags=["se_agent", "final_result"],
            profile=self.memory_profile,
            source_kind="se_final",
        )

    def _trace_step(self, board: Blackboard, *, agent: str, summary: str) -> None:
        board.trace.append(
            {
                "iteration": board.iteration,
                "state": board.state.value,
                "agent": agent,
                "summary": summary,
            }
        )

    def _get_context_profile(self, profile_id: str) -> ContextProfile:
        if profile_id in self.context_profiles:
            return self.context_profiles[profile_id]
        if self.context_profiles:
            return next(iter(self.context_profiles.values()))
        return ContextProfile(profile_id=profile_id)
