from __future__ import annotations

from app.apps.chat.prompts import CHAT_SYSTEM_PROMPT
from app.platform.apps.profiles import ContextProfile, MemoryProfile, RAGProfile, SkillBinding
from app.platform.context.builder import ContextBuilder
from app.platform.history.service import HistoryService
from app.platform.memory.service import MemoryService
from app.platform.models.base import BaseModelClient
from app.platform.observability.tracing import TraceService
from app.platform.rag.service import RAGService
from app.platform.runtime.factory import BaseRuntimeFactory, RuntimeBuildContext
from app.platform.runtime.chat_runtime import ChatAgentRuntime
from app.platform.tools.builtin_note import FileNoteStore
from app.platform.tools.executor import ToolExecutor
from app.platform.tools.registry import ToolRegistry


def build_chat_runtime(
    *,
    session_id: str,
    user_id: str | None,
    model_client: BaseModelClient,
    model_name: str,
    history_service: HistoryService,
    memory_service: MemoryService,
    rag_service: RAGService,
    note_store: FileNoteStore,
    context_builder: ContextBuilder,
    tool_registry: ToolRegistry,
    tool_executor: ToolExecutor,
    trace_service: TraceService,
    context_profile: ContextProfile,
    memory_profile: MemoryProfile,
    rag_profile: RAGProfile,
    skill_runtime,
    skill_bindings: list[SkillBinding],
    max_tool_iterations: int,
) -> ChatAgentRuntime:
    _ = rag_service
    _ = note_store
    return ChatAgentRuntime(
        app_id="chat",
        session_id=session_id,
        user_id=user_id,
        system_prompt=CHAT_SYSTEM_PROMPT,
        model_client=model_client,
        model_name=model_name,
        history_service=history_service,
        memory_service=memory_service,
        context_builder=context_builder,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        trace_service=trace_service,
        context_profile=context_profile,
        memory_profile=memory_profile,
        rag_profile=rag_profile,
        skill_runtime=skill_runtime,
        skill_bindings=skill_bindings,
        max_tool_iterations=max_tool_iterations,
    )


class ChatRuntimeFactory(BaseRuntimeFactory):
    @property
    def factory_id(self) -> str:
        return "chat"

    def create(self, build_context: RuntimeBuildContext) -> ChatAgentRuntime:
        app_config = build_context.settings.get_app_config(build_context.manifest.app_id)
        context_profile = build_context.manifest.profiles.get_context_profile("chat.reply")
        memory_profile = build_context.manifest.profiles.memory_profile
        rag_profile = build_context.manifest.profiles.rag_profile
        skill_bindings = build_context.manifest.profiles.skills
        return build_chat_runtime(
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
            context_profile=context_profile,
            memory_profile=memory_profile,
            rag_profile=rag_profile,
            skill_runtime=build_context.skill_runtime,
            skill_bindings=skill_bindings,
            max_tool_iterations=app_config.tool_iterations or build_context.settings.default_tool_iterations,
        )
