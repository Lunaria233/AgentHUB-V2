from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Iterator

from app.platform.apps.profiles import SkillBinding
from app.platform.capabilities.contracts import BaseCapabilityContext
from app.platform.apps.profiles import ContextProfile, MemoryProfile, RAGProfile
from app.platform.context.builder import ContextBuilder
from app.platform.context.types import ContextBuildRequest
from app.platform.core.message import Message, MessageRole
from app.platform.core.types import ParsedToolCall
from app.platform.history.service import HistoryService
from app.platform.memory.service import MemoryService
from app.platform.models.base import BaseModelClient, ModelRequest
from app.platform.observability.tracing import TraceService
from app.platform.runtime.agent import BaseAgentRuntime
from app.platform.runtime.events import EventEmitter, EventType
from app.platform.tools.base import ToolContext
from app.platform.tools.executor import ToolExecutor
from app.platform.tools.registry import ToolRegistry


TOOL_CALL_PATTERN = re.compile(r"\[TOOL_CALL:(?P<tool>[a-zA-Z0-9_\-]+):(?P<args>\{.*?\})\]")
logger = logging.getLogger(__name__)


class ChatAgentRuntime(BaseAgentRuntime):
    def __init__(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str | None,
        system_prompt: str,
        model_client: BaseModelClient,
        model_name: str,
        history_service: HistoryService,
        memory_service: MemoryService,
        context_builder: ContextBuilder,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        trace_service: TraceService,
        context_profile: ContextProfile,
        memory_profile: MemoryProfile,
        rag_profile: RAGProfile,
        skill_runtime,
        skill_bindings: list[SkillBinding] | None = None,
        max_tool_iterations: int = 2,
    ) -> None:
        self.app_id = app_id
        self.session_id = session_id
        self.user_id = user_id
        self.system_prompt = system_prompt
        self.model_client = model_client
        self.model_name = model_name
        self.history_service = history_service
        self.memory_service = memory_service
        self.context_builder = context_builder
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.trace_service = trace_service
        self.context_profile = context_profile
        self.memory_profile = memory_profile
        self.rag_profile = rag_profile
        self.skill_runtime = skill_runtime
        self.skill_bindings = list(skill_bindings or [])
        self.max_tool_iterations = max_tool_iterations
        self.events = EventEmitter()

    def run(self, *, user_input: str) -> dict[str, object]:
        answer = ""
        for event in self.stream(user_input=user_input):
            if event["type"] == EventType.MESSAGE_DONE.value:
                answer = str(event.get("content", ""))
        return {"answer": answer}

    def stream(self, *, user_input: str) -> Iterator[dict[str, object]]:
        trace_id = self.trace_service.new_trace_id()
        self.history_service.add_user_message(self.session_id, self.app_id, user_input)
        yield self.events.emit(EventType.STATUS, message="building context")

        context_request = self._build_context_request(user_input=user_input, trace_id=trace_id)
        context_result = self.context_builder.build(context_request)
        self.trace_service.log_event(
            trace_id=trace_id,
            event_type="context_build",
            payload={
                "app_id": self.app_id,
                "profile": context_request.profile,
                "packet_count": len(context_result.packets),
                "provider_order": context_request.provider_order,
                "max_tokens": context_request.max_tokens,
                "light_mode": bool(context_request.metadata.get("light_mode")),
            },
        )
        messages = [
            Message(role=MessageRole.SYSTEM, content=self._build_system_prompt()),
            Message(role=MessageRole.USER, content=self._render_user_context(context_result)),
        ]
        tool_context = ToolContext(app_id=self.app_id, session_id=self.session_id, user_id=self.user_id, trace_id=trace_id)

        final_text = ""
        for _ in range(self.max_tool_iterations + 1):
            request = ModelRequest(model=self.model_name, messages=[message.to_openai_dict() for message in messages])
            try:
                response_text = yield from self._stream_model_response(request=request, trace_id=trace_id)
            except Exception as exc:
                error_message = f"Model call failed: {exc}"
                self.history_service.add_assistant_message(self.session_id, self.app_id, error_message)
                yield self.events.emit(EventType.ERROR, message=error_message)
                yield self.events.emit(EventType.MESSAGE_DONE, content=error_message)
                yield self.events.emit(EventType.DONE)
                return
            final_text = response_text
            tool_calls = self._parse_tool_calls(response_text)
            if not tool_calls:
                break
            messages.append(Message(role=MessageRole.ASSISTANT, content=response_text))
            for tool_call in tool_calls:
                yield self.events.emit(EventType.TOOL_CALL, tool_name=tool_call.tool_name, arguments=tool_call.arguments)
                result = self.tool_executor.safe_execute_tool(tool_call.tool_name, tool_call.arguments, tool_context)
                yield self.events.emit(EventType.TOOL_RESULT, tool_name=tool_call.tool_name, result=result)
                messages.append(
                    Message(
                        role=MessageRole.TOOL_RESULT,
                        content=json.dumps({"tool_name": tool_call.tool_name, "result": result}, ensure_ascii=False),
                        metadata={"tool_name": tool_call.tool_name},
                    )
                )
        cleaned_text = self._remove_tool_calls(final_text).strip()
        self.history_service.add_assistant_message(self.session_id, self.app_id, cleaned_text)
        yield self.events.emit(EventType.MESSAGE_DONE, content=cleaned_text)
        if self.memory_profile.enabled:
            self._persist_memory_async(user_input=user_input, cleaned_text=cleaned_text)
        yield self.events.emit(EventType.DONE)

    def _build_system_prompt(self) -> str:
        tools_prompt = self.tool_registry.build_prompt_fragment()
        fragments = [self.system_prompt.strip(), tools_prompt]
        if self.skill_bindings:
            fragments = self.skill_runtime.apply(
                BaseCapabilityContext(
                    app_id=self.app_id,
                    session_id=self.session_id,
                    user_id=self.user_id,
                    stage=self.context_profile.profile_id,
                ),
                prompt_fragments=fragments,
                bindings=self.skill_bindings,
                available_tool_names={tool.name for tool in self.tool_registry.list_tools()},
            )
        return "\n\n".join(part for part in fragments if part)

    def _build_context_request(self, *, user_input: str, trace_id: str) -> ContextBuildRequest:
        light_mode = self._should_use_light_context(user_input)
        history_limit = self.context_profile.history_limit
        max_tokens = self.context_profile.max_tokens
        provider_order = list(self.context_profile.provider_order)
        memory_limit = self.memory_profile.retrieval_limit
        memory_types = list(self.memory_profile.retrieval_types)
        source_budgets = None
        rag_enabled = True
        rag_limit = self.rag_profile.retrieval_limit
        rag_query_rewrite_enabled = self.rag_profile.query_rewrite_enabled
        rag_hyde_enabled = self.rag_profile.hyde_enabled
        rag_rerank_enabled = self.rag_profile.rerank_enabled

        if light_mode:
            history_limit = min(history_limit, 4)
            max_tokens = min(max_tokens, 1400)
            provider_order = ["history", "memory", "rag"]
            memory_limit = min(memory_limit, 1)
            memory_types = [memory_type for memory_type in memory_types if memory_type in {"semantic", "episodic"}]
            source_budgets = {"history": 0.55, "memory": 0.35, "rag": 0.1}
            rag_enabled = self._looks_like_knowledge_request(user_input)
            rag_limit = 1 if rag_enabled else 0
            rag_query_rewrite_enabled = False
            rag_hyde_enabled = False
            rag_rerank_enabled = False

        metadata = {
            "trace_id": trace_id,
            "light_mode": light_mode,
            "memory_scope": self.memory_profile.retrieval_scope or self.context_profile.memory_scope,
            "memory_limit": memory_limit,
            "memory_types": memory_types,
            "memory_min_importance": self.memory_profile.min_importance,
            "memory_type_weights": {"semantic": 0.16, "episodic": 0.1, "working": 0.04, "perceptual": 0.08, "graph": 0.14},
            "memory_retrieval_mode": "lexical" if light_mode else self.memory_profile.retrieval_mode,
            "memory_include_graph": False if light_mode else self.memory_profile.graph_enabled,
            "rag_limit": rag_limit,
            "rag_retrieval_mode": self.rag_profile.retrieval_mode,
            "rag_include_public": self.rag_profile.include_public,
            "rag_include_app_shared": self.rag_profile.include_app_shared,
            "rag_include_user_private": self.rag_profile.include_user_private,
            "rag_include_session_temporary": self.rag_profile.include_session_temporary,
            "rag_query_rewrite_enabled": rag_query_rewrite_enabled,
            "rag_query_rewrite_mode": self.rag_profile.query_rewrite_mode,
            "rag_mqe_variants": 1 if light_mode else self.rag_profile.mqe_variants,
            "rag_hyde_enabled": rag_hyde_enabled,
            "rag_hyde_mode": self.rag_profile.hyde_mode,
            "rag_rerank_enabled": rag_rerank_enabled,
            "rag_rerank_strategy": self.rag_profile.rerank_strategy,
            "rag_rerank_top_n": self.rag_profile.rerank_top_n,
            "note_scope": self.context_profile.note_scope,
            "history_compact_after": 3 if light_mode else 5,
            "rag_chunk_char_limit": 320 if light_mode else 420,
        }
        if source_budgets:
            metadata["source_budgets"] = source_budgets
        if not rag_enabled:
            provider_order = [provider for provider in provider_order if provider != "rag"]

        return ContextBuildRequest(
            app_id=self.app_id,
            session_id=self.session_id,
            user_id=self.user_id,
            user_input=user_input,
            system_prompt=self._build_system_prompt(),
            profile=self.context_profile.profile_id,
            max_tokens=max_tokens,
            history_limit=history_limit,
            knowledge_scopes=self.context_profile.knowledge_scopes or [self.app_id],
            provider_order=provider_order,
            metadata=metadata,
        )

    @staticmethod
    def _should_use_light_context(user_input: str) -> bool:
        stripped = user_input.strip()
        if len(stripped) > 180:
            return False
        lowered = stripped.lower()
        heavy_markers = [
            "根据文档",
            "根据知识库",
            "参考资料",
            "上传",
            "附件",
            "pdf",
            "文档",
            "资料",
            "source",
            "citation",
            "report",
            "总结",
            "分析",
            "research",
            "rag",
        ]
        return not any(marker in lowered for marker in heavy_markers)

    @staticmethod
    def _looks_like_knowledge_request(user_input: str) -> bool:
        lowered = user_input.strip().lower()
        markers = [
            "根据",
            "文档",
            "知识库",
            "上传",
            "资料",
            "附件",
            "source",
            "citation",
            "pdf",
            "report",
        ]
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _render_user_context(context_result) -> str:
        return "\n\n".join(
            f"[{section.title}]\n{section.content}"
            for section in context_result.sections
            if section.title != "Role & Policies" and section.content.strip()
        ).strip()

    def _parse_tool_calls(self, text: str) -> list[ParsedToolCall]:
        calls: list[ParsedToolCall] = []
        for match in TOOL_CALL_PATTERN.finditer(text):
            try:
                calls.append(ParsedToolCall(tool_name=match.group("tool"), arguments=json.loads(match.group("args"))))
            except json.JSONDecodeError:
                continue
        return calls

    @staticmethod
    def _remove_tool_calls(text: str) -> str:
        return TOOL_CALL_PATTERN.sub("", text)

    def _stream_model_response(self, *, request: ModelRequest, trace_id: str) -> Iterator[dict[str, object] | str]:
        self.trace_service.log_model_call(
            trace_id=trace_id,
            model=self.model_name,
            payload={"messages": request.messages, "stream": True},
        )
        streamed_parts: list[str] = []
        saw_stream_chunk = False
        try:
            for chunk in self.model_client.stream_generate(request):
                if not chunk.text:
                    continue
                saw_stream_chunk = True
                streamed_parts.append(chunk.text)
                yield self.events.emit(EventType.MESSAGE_CHUNK, content=chunk.text)
            streamed_text = "".join(streamed_parts).strip()
            if streamed_text:
                return streamed_text
            if saw_stream_chunk:
                return "".join(streamed_parts)
        except Exception as exc:
            if saw_stream_chunk:
                raise exc

        self.trace_service.log_model_call(
            trace_id=trace_id,
            model=self.model_name,
            payload={"messages": request.messages, "stream": False, "fallback": "generate"},
        )
        response = self.model_client.generate(request)
        return response.text

    def _persist_memory_async(self, *, user_input: str, cleaned_text: str) -> None:
        def worker() -> None:
            try:
                self.memory_service.remember_interaction(
                    app_id=self.app_id,
                    session_id=self.session_id,
                    user_id=self.user_id,
                    content=f"User: {user_input}\nAssistant: {cleaned_text}",
                    user_message=user_input,
                    assistant_message=cleaned_text,
                    profile=self.memory_profile,
                )
                if self.memory_profile.consolidation_enabled:
                    self.memory_service.consolidate_memory(
                        app_id=self.app_id,
                        session_id=self.session_id,
                        user_id=self.user_id,
                        profile=self.memory_profile,
                    )
            except Exception as exc:
                logger.warning(
                    "Memory persistence failed for app_id=%s session_id=%s user_id=%s: %s",
                    self.app_id,
                    self.session_id,
                    self.user_id,
                    exc,
                )

        threading.Thread(
            target=worker,
            name=f"chat-memory-{self.session_id}",
            daemon=True,
        ).start()
