from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
import logging

from app.apps.deep_research.archive import ResearchRunStore
from app.apps.deep_research.models import ResearchState, ResearchTask
from app.apps.deep_research.planner import ResearchPlanner
from app.apps.deep_research.prompts import PLANNER_PROMPT, REPORTER_PROMPT, SUMMARIZER_PROMPT
from app.apps.deep_research.reporter import ReportWriter
from app.apps.deep_research.summarizer import TaskSummarizer
from app.platform.apps.profiles import ContextProfile, MemoryProfile, RAGProfile, SkillBinding
from app.platform.capabilities.contracts import BaseCapabilityContext
from app.platform.context.builder import ContextBuilder
from app.platform.context.types import ContextBuildRequest, ContextPacket
from app.platform.history.service import HistoryService
from app.platform.memory.service import MemoryService
from app.platform.models.base import BaseModelClient
from app.platform.observability.tracing import TraceService
from app.platform.runtime.events import EventType
from app.platform.runtime.factory import BaseRuntimeFactory, RuntimeBuildContext
from app.platform.runtime.workflow_runtime import WorkflowAgentRuntime
from app.platform.tools.base import ToolContext
from app.platform.tools.builtin_note import FileNoteStore
from app.platform.tools.executor import ToolExecutor
from app.platform.tools.registry import ToolRegistry


@dataclass(slots=True)
class TaskExecutionResult:
    task_id: int
    search_result: dict[str, object]
    summary: str
    sources: list[dict[str, str]]


logger = logging.getLogger(__name__)


class DeepResearchRuntime(WorkflowAgentRuntime):
    def __init__(
        self,
        *,
        session_id: str,
        user_id: str | None,
        model_client: BaseModelClient,
        model_name: str,
        history_service: HistoryService,
        memory_service: MemoryService,
        rag_service,
        note_store: FileNoteStore,
        tool_executor: ToolExecutor,
        tool_registry: ToolRegistry,
        context_builder: ContextBuilder,
        trace_service: TraceService,
        research_run_store: ResearchRunStore,
        context_profiles: dict[str, ContextProfile],
        memory_profile: MemoryProfile,
        rag_profile: RAGProfile,
        skill_runtime,
        skill_bindings: list[SkillBinding],
        default_task_count: int,
        sources_per_task: int,
        max_parallel_tasks: int = 2,
    ) -> None:
        super().__init__()
        self.session_id = session_id
        self.user_id = user_id
        self.history_service = history_service
        self.memory_service = memory_service
        self.rag_service = rag_service
        self.note_store = note_store
        self.tool_executor = tool_executor
        self.tool_registry = tool_registry
        self.context_builder = context_builder
        self.trace_service = trace_service
        self.research_run_store = research_run_store
        self.context_profiles = context_profiles
        self.memory_profile = memory_profile
        self.rag_profile = rag_profile
        self.skill_runtime = skill_runtime
        self.skill_bindings = list(skill_bindings)
        self.default_task_count = max(2, default_task_count)
        self.sources_per_task = max(1, sources_per_task)
        self.max_parallel_tasks = max(1, max_parallel_tasks)
        self.planner = ResearchPlanner(model_client, model_name)
        self.summarizer = TaskSummarizer(model_client, model_name)
        self.reporter = ReportWriter(model_client, model_name)
        self._background_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="deep-research-bg")

    def run(self, *, user_input: str) -> dict[str, object]:
        report = ""
        tasks: list[dict[str, object]] = []
        for event in self.stream(user_input=user_input):
            if event["type"] == EventType.STATUS.value and "tasks" in event:
                tasks = list(event["tasks"])
            if event["type"] == EventType.MESSAGE_DONE.value and "report" in event:
                report = str(event["report"])
        return {"report": report, "tasks": tasks}

    def stream(self, *, user_input: str) -> Iterator[dict[str, object]]:
        topic = user_input.strip()
        trace_id = self.trace_service.new_trace_id()
        tool_context = ToolContext(app_id="deep_research", session_id=self.session_id, user_id=self.user_id, trace_id=trace_id)
        event_log: list[dict[str, object]] = []

        def emit(event_type: EventType, **payload: object) -> dict[str, object]:
            event = self.events.emit(event_type, **payload)
            event_log.append(deepcopy(event))
            return event

        self.history_service.add_user_message(self.session_id, "deep_research", topic)
        if self.memory_profile.enabled:
            self.memory_service.remember_working_memory(
                app_id="deep_research",
                session_id=self.session_id,
                user_id=self.user_id,
                content=f"Research session started for topic: {topic}",
                importance=0.72,
                tags=["deep_research", "topic"],
                profile=self.memory_profile,
                source_kind="research_topic",
            )
        yield emit(EventType.STATUS, message="planning tasks")
        planning_prompt = self._build_context_prompt(
            trace_id=trace_id,
            profile="research.plan",
            system_prompt=PLANNER_PROMPT,
            user_input=f"Research topic: {topic}\nCreate at most {self.default_task_count} complementary research tasks.",
        )
        planned_tasks = self.planner.plan_tasks_from_prompt(planning_prompt, topic=topic)
        state = ResearchState(topic=topic, tasks=planned_tasks[: self.default_task_count])
        yield emit(
            EventType.STATUS,
            message="tasks planned",
            tasks=[{"task_id": task.task_id, "title": task.title, "query": task.query} for task in state.tasks],
        )

        for task in state.tasks:
            yield emit(
                EventType.STATUS,
                message=f"researching task {task.task_id}",
                task_id=task.task_id,
                title=task.title,
            )
            yield emit(
                EventType.TOOL_CALL,
                tool_name="search",
                arguments={"query": task.query, "max_results": self.sources_per_task},
                task_id=task.task_id,
            )

        task_results = self._execute_tasks_concurrently(topic=topic, tasks=state.tasks, tool_context=tool_context)
        for task in state.tasks:
            task_result = task_results.get(task.task_id)
            if task_result is None:
                task_result = self._execute_single_task(topic=topic, task=task, tool_context=tool_context)

            yield emit(
                EventType.TOOL_RESULT,
                tool_name="search",
                result=task_result.search_result,
                task_id=task.task_id,
            )
            task.sources = list(task_result.sources)
            for item in task.sources:
                yield emit(
                    EventType.CITATION,
                    task_id=task.task_id,
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                )

            task.summary = task_result.summary
            note = self.note_store.create(
                app_id="deep_research",
                session_id=self.session_id,
                title=f"Task {task.task_id}: {task.title}",
                content=task.summary,
                note_type="task_state",
                tags=["deep_research", f"task_{task.task_id}"],
            )
            task.note_id = str(note["note_id"])
            if self.memory_profile.enabled:
                self._submit_background(
                    self.memory_service.remember_fact,
                    app_id="deep_research",
                    session_id=self.session_id,
                    user_id=self.user_id,
                    content=f"{task.title}: {task.summary}",
                    tags=["deep_research", f"task_{task.task_id}"],
                    profile=self.memory_profile,
                    source_kind="task_summary",
                )
            yield emit(
                EventType.MESSAGE_DONE,
                task_id=task.task_id,
                title=task.title,
                content=task.summary,
                note_id=task.note_id,
            )
            if self.rag_profile.enabled:
                self._submit_background(
                    self.rag_service.ingest_generated_text,
                    app_id="deep_research",
                    session_id=self.session_id,
                    user_id=self.user_id,
                    title=f"{topic} - task {task.task_id} summary",
                    text=task.summary,
                    source_type="generated_summary",
                    document_id=f"generated::{self.session_id}::task::{task.task_id}",
                    metadata={"task_id": task.task_id, "task_title": task.title},
                    trace_id=trace_id,
                )

        yield emit(EventType.STATUS, message="writing final report")
        report_prompt = self._build_context_prompt(
            trace_id=trace_id,
            profile="research.report",
            system_prompt=REPORTER_PROMPT,
            user_input=f"Research topic: {topic}\nWrite the final markdown report.",
            inline_packets=self._build_report_packets(state),
        )
        state.report = self.reporter.write_report_from_prompt(report_prompt, state=state)
        self.history_service.add_assistant_message(self.session_id, "deep_research", state.report)
        self.note_store.create(
            app_id="deep_research",
            session_id=self.session_id,
            title=f"Research report: {topic}",
            content=state.report,
            note_type="conclusion",
            tags=["deep_research", "report"],
        )
        if self.memory_profile.enabled:
            self._submit_background(
                self.memory_service.remember_fact,
                app_id="deep_research",
                session_id=self.session_id,
                user_id=self.user_id,
                content=f"Research report for {topic}\n\n{state.report}",
                importance=0.92,
                tags=["deep_research", "report"],
                profile=self.memory_profile,
                source_kind="report",
            )
        if self.memory_profile.enabled and self.memory_profile.consolidation_enabled:
            self._submit_background(
                self.memory_service.consolidate_memory,
                app_id="deep_research",
                session_id=self.session_id,
                user_id=self.user_id,
                profile=self.memory_profile,
            )
        if self.rag_profile.enabled:
            self._submit_background(
                self.rag_service.ingest_generated_text,
                app_id="deep_research",
                session_id=self.session_id,
                user_id=self.user_id,
                title=f"{topic} - final report",
                text=state.report,
                source_type="generated_report",
                document_id=f"generated::{self.session_id}::report",
                metadata={"topic": topic, "record_type": "final_report"},
                trace_id=trace_id,
            )
        yield emit(EventType.MESSAGE_DONE, content=state.report, report=state.report)
        self._submit_background(
            self.research_run_store.save_run,
            session_id=self.session_id,
            topic=topic,
            user_id=self.user_id,
            status="completed",
            report=state.report,
            tasks=[
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "query": task.query,
                    "goal": task.goal,
                    "summary": task.summary,
                    "note_id": task.note_id,
                    "sources": task.sources,
                }
                for task in state.tasks
            ],
            events=event_log,
        )
        yield emit(EventType.DONE)

    def _execute_tasks_concurrently(
        self,
        *,
        topic: str,
        tasks: list[ResearchTask],
        tool_context: ToolContext,
    ) -> dict[int, TaskExecutionResult]:
        if not tasks:
            return {}

        max_workers = min(self.max_parallel_tasks, len(tasks))
        if max_workers <= 1:
            return {task.task_id: self._execute_single_task(topic=topic, task=task, tool_context=tool_context) for task in tasks}

        results: dict[int, TaskExecutionResult] = {}
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="deep-research-task") as executor:
            future_map = {
                executor.submit(self._execute_single_task, topic=topic, task=task, tool_context=tool_context): task.task_id
                for task in tasks
            }
            for future in as_completed(future_map):
                task_id = future_map[future]
                try:
                    results[task_id] = future.result()
                except Exception as exc:
                    results[task_id] = TaskExecutionResult(
                        task_id=task_id,
                        search_result={"ok": False, "provider": "internal", "error": str(exc)},
                        summary=f"Task {task_id} execution failed: {exc}",
                        sources=[],
                    )
        return results

    def _execute_single_task(
        self,
        *,
        topic: str,
        task: ResearchTask,
        tool_context: ToolContext,
    ) -> TaskExecutionResult:
        search_result = self.tool_executor.safe_execute_tool(
            "search",
            {"query": task.query, "max_results": self.sources_per_task},
            tool_context,
        )
        raw_sources = search_result.get("results", []) if isinstance(search_result, dict) else []
        sources = [item for item in raw_sources if isinstance(item, dict)]
        task.sources = list(sources)
        if self.memory_profile.enabled:
            snippet_titles = ", ".join(str(item.get("title", "")) for item in sources[:3] if item.get("title"))
            self.memory_service.remember_working_memory(
                app_id="deep_research",
                session_id=self.session_id,
                user_id=self.user_id,
                content=f"Task {task.task_id} search observation for {task.title}: {snippet_titles or 'no high-signal sources yet'}",
                importance=0.68,
                tags=["deep_research", f"task_{task.task_id}", "search_observation"],
                profile=self.memory_profile,
                source_kind="search_observation",
            )
        summary_prompt = self._build_context_prompt(
            trace_id=tool_context.trace_id or self.trace_service.new_trace_id(),
            profile="research.summarize",
            system_prompt=SUMMARIZER_PROMPT,
            user_input=self._build_task_instruction(topic, task),
            inline_packets=self._build_search_packets(search_result),
        )
        summary = self.summarizer.summarize_from_prompt(summary_prompt, task=task)
        return TaskExecutionResult(
            task_id=task.task_id,
            search_result=search_result if isinstance(search_result, dict) else {"ok": False, "error": "invalid search result"},
            summary=summary,
            sources=sources,
        )

    def _submit_background(self, func, /, *args, **kwargs) -> None:
        def runner() -> None:
            try:
                func(*args, **kwargs)
            except Exception as exc:
                logger.warning("Deep research background task failed: %s", exc)

        self._background_executor.submit(runner)

    def _build_context_prompt(
        self,
        *,
        trace_id: str,
        profile: str,
        system_prompt: str,
        user_input: str,
        inline_packets: list[ContextPacket] | None = None,
    ) -> str:
        context_profile = self._get_context_profile(profile)
        result = self.context_builder.build(
            ContextBuildRequest(
                app_id="deep_research",
                session_id=self.session_id,
                user_id=self.user_id,
                user_input=user_input,
                system_prompt=system_prompt,
                profile=context_profile.profile_id,
                max_tokens=context_profile.max_tokens,
                history_limit=context_profile.history_limit,
                knowledge_scopes=context_profile.knowledge_scopes or ["deep_research"],
                provider_order=context_profile.provider_order,
                inline_packets=inline_packets or [],
                metadata={
                    "memory_scope": self.memory_profile.retrieval_scope or context_profile.memory_scope,
                    "trace_id": trace_id,
                    "memory_limit": self.memory_profile.retrieval_limit,
                    "memory_types": self.memory_profile.retrieval_types,
                    "memory_min_importance": self.memory_profile.min_importance,
                    "memory_type_weights": {"semantic": 0.16, "episodic": 0.1, "working": 0.04, "perceptual": 0.08, "graph": 0.14},
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
                    "note_scope": context_profile.note_scope,
                },
            )
        )
        self.trace_service.log_event(
            trace_id=trace_id,
            event_type="context_build",
            payload={
                "app_id": "deep_research",
                "profile": context_profile.profile_id,
                "packet_count": len(result.packets),
                "knowledge_scopes": context_profile.knowledge_scopes or ["deep_research"],
            },
        )
        prompt_fragments = [result.prompt]
        if self.skill_bindings:
            prompt_fragments = self.skill_runtime.apply(
                BaseCapabilityContext(
                    app_id="deep_research",
                    session_id=self.session_id,
                    user_id=self.user_id,
                    stage=profile,
                ),
                prompt_fragments=prompt_fragments,
                bindings=self.skill_bindings,
                available_tool_names={tool.name for tool in self.tool_registry.list_tools()},
            )
        return "\n\n".join(fragment for fragment in prompt_fragments if fragment.strip())

    def _build_search_packets(self, search_result: dict[str, object]) -> list[ContextPacket]:
        packets: list[ContextPacket] = []
        answer = str(search_result.get("answer", "")).strip()
        if answer:
            packets.append(
                ContextPacket(
                    content=f"[search answer] {answer}",
                    token_count=self._estimate_tokens(answer),
                    relevance_score=0.98,
                    metadata={"source": "search"},
                )
            )
        for item in search_result.get("results", []):
            if not isinstance(item, dict):
                continue
            content = "\n".join(
                part
                for part in [
                    f"Title: {item.get('title', '')}".strip(),
                    f"URL: {item.get('url', '')}".strip(),
                    f"Snippet: {item.get('snippet', '')}".strip(),
                ]
                if part
            )
            if not content:
                continue
            packets.append(
                ContextPacket(
                    content=content,
                    token_count=self._estimate_tokens(content),
                    relevance_score=max(0.8, float(item.get("score", 0.8) or 0.8)),
                    metadata={"source": "search", "url": item.get("url", "")},
                )
            )
        return packets

    def _build_report_packets(self, state: ResearchState) -> list[ContextPacket]:
        packets: list[ContextPacket] = []
        for task in state.tasks:
            content = f"Task: {task.title}\nGoal: {task.goal}\nSummary:\n{task.summary}".strip()
            packets.append(
                ContextPacket(
                    content=content,
                    token_count=self._estimate_tokens(content),
                    relevance_score=0.95,
                    metadata={"source": "task_summary", "task_id": task.task_id},
                )
            )
        return packets

    @staticmethod
    def _build_task_instruction(topic: str, task: ResearchTask) -> str:
        return (
            f"Research topic: {topic}\n"
            f"Task title: {task.title}\n"
            f"Task goal: {task.goal}\n"
            f"Task query: {task.query}\n"
            "Write a grounded task summary based on the retrieved evidence."
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text.split()))

    def _get_context_profile(self, profile_id: str) -> ContextProfile:
        if profile_id in self.context_profiles:
            return self.context_profiles[profile_id]
        if self.context_profiles:
            return next(iter(self.context_profiles.values()))
        return ContextProfile(profile_id=profile_id)


def build_deep_research_runtime(
    *,
    session_id: str,
    user_id: str | None,
    model_client: BaseModelClient,
    model_name: str,
    history_service: HistoryService,
    memory_service: MemoryService,
    rag_service,
    note_store: FileNoteStore,
    context_builder: ContextBuilder,
    tool_registry: ToolRegistry,
    tool_executor: ToolExecutor,
    trace_service: TraceService,
    research_run_store: ResearchRunStore,
    context_profiles: dict[str, ContextProfile],
    memory_profile: MemoryProfile,
    rag_profile: RAGProfile,
    skill_runtime,
    skill_bindings: list[SkillBinding],
    default_task_count: int,
    sources_per_task: int,
    max_parallel_tasks: int = 2,
) -> DeepResearchRuntime:
    _ = rag_service
    return DeepResearchRuntime(
        session_id=session_id,
        user_id=user_id,
        model_client=model_client,
        model_name=model_name,
        history_service=history_service,
        memory_service=memory_service,
        rag_service=rag_service,
        note_store=note_store,
        tool_executor=tool_executor,
        tool_registry=tool_registry,
        context_builder=context_builder,
        trace_service=trace_service,
        research_run_store=research_run_store,
        context_profiles=context_profiles,
        memory_profile=memory_profile,
        rag_profile=rag_profile,
        skill_runtime=skill_runtime,
        skill_bindings=skill_bindings,
        default_task_count=default_task_count,
        sources_per_task=sources_per_task,
        max_parallel_tasks=max_parallel_tasks,
    )


class DeepResearchRuntimeFactory(BaseRuntimeFactory):
    @property
    def factory_id(self) -> str:
        return "deep_research"

    def create(self, build_context: RuntimeBuildContext) -> DeepResearchRuntime:
        app_config = build_context.settings.get_app_config(build_context.manifest.app_id)
        return build_deep_research_runtime(
            session_id=build_context.session_id,
            user_id=build_context.user_id,
            model_client=build_context.model_client,
            model_name=build_context.model_name,
            history_service=build_context.history_service,
            memory_service=build_context.memory_service,
            rag_service=build_context.rag_service,
            note_store=build_context.note_store,
            context_builder=build_context.context_builder,
            tool_registry=build_context.tool_registry,
            tool_executor=build_context.tool_executor,
            trace_service=build_context.trace_service,
            research_run_store=build_context.dependencies["research_run_store"],
            context_profiles=build_context.manifest.profiles.context_profiles,
            memory_profile=build_context.manifest.profiles.memory_profile,
            rag_profile=build_context.manifest.profiles.rag_profile,
            skill_runtime=build_context.skill_runtime,
            skill_bindings=build_context.manifest.profiles.skills,
            default_task_count=build_context.settings.research_default_task_count,
            sources_per_task=app_config.search_max_results or build_context.settings.research_sources_per_task,
            max_parallel_tasks=build_context.settings.research_max_parallel_tasks,
        )
