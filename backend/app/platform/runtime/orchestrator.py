from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from app.apps.chat.agent import ChatRuntimeFactory
from app.apps.chat.prompts import CHAT_SYSTEM_PROMPT
from app.apps.deep_research.archive import ResearchRunStore
from app.apps.deep_research.agent import DeepResearchRuntimeFactory
from app.apps.deep_research.prompts import PLANNER_PROMPT, REPORTER_PROMPT, SUMMARIZER_PROMPT
from app.apps.software_engineering.agent import SoftwareEngineeringRuntimeFactory
from app.apps.software_engineering.archive import SERunStore
from app.apps.software_engineering.tools import build_software_engineering_tools
from app.config import get_settings
from app.platform.apps.registry import get_app_registry
from app.platform.apps.profiles import ContextProfile
from app.platform.capabilities.contracts import BaseCapabilityContext
from app.platform.context.builder import ContextBuilder
from app.platform.context.types import ContextBuildRequest, ContextPacket
from app.platform.context.providers import HistoryContextProvider, MemoryContextProvider, NotesContextProvider, RAGContextProvider
from app.platform.context.registry import ContextProviderRegistry
from app.platform.history.service import HistoryService
from app.platform.history.store import SQLiteHistoryStore
from app.platform.memory.embedding import build_memory_embedder
from app.platform.memory.graph_backends import Neo4jGraphMemoryStore
from app.platform.memory.service import MemoryService
from app.platform.memory.store import SQLiteMemoryStore
from app.platform.memory.vector_index import QdrantMemoryIndex
from app.platform.models.factory import build_model_client
from app.platform.observability.tracing import TraceService, TraceStore
from app.platform.protocols.mcp.manager import MCPConnectionManager, MCPServerConfig
from app.platform.protocols.mcp.store import MCPServerStore
from app.platform.rag.chunking import StructuredChunker
from app.platform.rag.embedding import build_rag_embedder
from app.platform.rag.index import QdrantRAGIndex
from app.platform.rag.parsers import DocumentParser
from app.platform.rag.service import RAGService
from app.platform.rag.store import SQLiteRAGStore
from app.platform.runtime.factory import RuntimeBuildContext, RuntimeFactoryRegistry
from app.platform.skills.evaluation import SkillEvaluator
from app.platform.skills.loader import SkillFileLoader
from app.platform.skills.registry import SkillRegistry
from app.platform.skills.runtime import PlatformSkillRuntime
from app.platform.tools.builtin_note import BuiltinNoteTool, FileNoteStore
from app.platform.tools.builtin_search import BuiltinSearchTool
from app.platform.tools.executor import ToolExecutor
from app.platform.tools.mcp_adapter import MCPToolAdapter, build_mcp_tool_name
from app.platform.tools.registry import ToolRegistry


class AppOrchestrator:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.app_registry = get_app_registry()
        self.model_client = build_model_client(settings)
        self.memory_embedder = build_memory_embedder(settings)
        self.memory_vector_index = (
            QdrantMemoryIndex(
                base_url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                collection=settings.qdrant_collection,
            )
            if settings.qdrant_url
            else None
        )
        self.memory_graph_backend = (
            Neo4jGraphMemoryStore(
                uri=settings.neo4j_uri,
                username=settings.neo4j_username,
                password=settings.neo4j_password,
            )
            if settings.neo4j_uri and settings.neo4j_username and settings.neo4j_password
            else None
        )
        self.history_service = HistoryService(SQLiteHistoryStore(settings.history_db_path))
        self.memory_service = MemoryService(
            SQLiteMemoryStore(settings.memory_db_path),
            settings=settings.memory,
            model_client=self.model_client,
            model_name=settings.llm_model,
            embedder=self.memory_embedder,
            vector_index=self.memory_vector_index,
            graph_backend=self.memory_graph_backend,
        )
        self.trace_service = TraceService(TraceStore(settings.trace_db_path))
        self.rag_embedder = build_rag_embedder(settings)
        self.rag_vector_index = (
            QdrantRAGIndex(
                base_url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                collection=settings.rag_qdrant_collection,
            )
            if settings.qdrant_url
            else None
        )
        self.rag_service = RAGService(
            store=SQLiteRAGStore(settings.rag_store_path / "rag.db"),
            parser=DocumentParser(),
            chunker=StructuredChunker(chunk_size=settings.rag_chunk_size, chunk_overlap=settings.rag_chunk_overlap),
            embedder=self.rag_embedder,
            vector_index=self.rag_vector_index,
            model_client=self.model_client,
            model_name=settings.llm_model,
            trace_service=self.trace_service,
            uploads_root=settings.rag_store_path / "uploads",
            query_rewrite_mode=settings.rag_query_rewrite_mode,
            hyde_max_tokens=settings.rag_hyde_max_tokens,
            mqe_variants=settings.rag_mqe_variants,
            rerank_strategy=settings.rag_rerank_strategy,
            rerank_top_n=settings.rag_rerank_top_n,
            url_timeout_seconds=settings.rag_url_timeout_seconds,
        )
        self.note_store = FileNoteStore(settings.notes_path)
        self.research_run_store = ResearchRunStore(settings.research_runs_path)
        self.se_run_store = SERunStore(settings.storage.root / "se_runs")
        self.skills_root = Path(__file__).resolve().parents[4] / "skills"
        self.skill_loader = SkillFileLoader(self.skills_root)
        self.skill_registry = SkillRegistry(self.skill_loader)
        self.skill_registry.scan()
        self.skill_runtime = PlatformSkillRuntime(self.skill_registry)
        self.mcp_manager = MCPConnectionManager()
        self.mcp_store = MCPServerStore(settings.storage.root / "mcp" / "servers.json")
        self._static_mcp_server_names: set[str] = set()
        self.runtime_factories = RuntimeFactoryRegistry()
        self.runtime_factories.register(ChatRuntimeFactory())
        self.runtime_factories.register(DeepResearchRuntimeFactory())
        self.runtime_factories.register(SoftwareEngineeringRuntimeFactory())
        if settings.mcp.enabled:
            for server in settings.mcp.enabled_servers():
                self._register_settings_server(server)
            self._load_custom_mcp_servers()

    def _register_settings_server(self, server) -> None:
        server_env = dict(server.env)
        if server.name == "github" and self.settings.github_personal_access_token:
            server_env.setdefault("GITHUB_PERSONAL_ACCESS_TOKEN", self.settings.github_personal_access_token)
        self._static_mcp_server_names.add(server.name)
        self.mcp_manager.register_server(
            MCPServerConfig(
                server_name=server.name,
                enabled=server.enabled,
                transport=server.transport,
                command=server.command,
                args=server.args,
                url=server.url,
                env=server_env,
                headers=server.headers,
                description=server.description,
                allowed_app_ids=list(getattr(server, "allowed_app_ids", [])),
                source="static",
            )
        )

    def _load_custom_mcp_servers(self) -> None:
        for config in self.mcp_store.list_servers():
            if config.server_name in self._static_mcp_server_names:
                continue
            config.source = "custom"
            self.mcp_manager.register_server(config)

    def list_mcp_servers(self) -> list[MCPServerConfig]:
        return self.mcp_manager.list_configs()

    def upsert_custom_mcp_server(self, config: MCPServerConfig) -> MCPServerConfig:
        if config.server_name in self._static_mcp_server_names:
            raise ValueError(f"MCP server '{config.server_name}' is defined in platform.toml and cannot be overwritten")
        config.source = "custom"
        self.mcp_store.upsert_server(config)
        self.mcp_manager.register_server(config)
        return config

    def set_custom_mcp_server_enabled(self, server_name: str, enabled: bool) -> MCPServerConfig:
        if server_name in self._static_mcp_server_names:
            raise ValueError(f"MCP server '{server_name}' is managed by platform.toml and cannot be modified here")
        config = self.mcp_store.get_server(server_name)
        if config is None:
            raise ValueError(f"MCP server '{server_name}' was not found")
        config.enabled = enabled
        self.mcp_store.upsert_server(config)
        self.mcp_manager.set_enabled(server_name, enabled)
        return config

    def delete_custom_mcp_server(self, server_name: str) -> bool:
        if server_name in self._static_mcp_server_names:
            raise ValueError(f"MCP server '{server_name}' is managed by platform.toml and cannot be deleted here")
        deleted = self.mcp_store.delete_server(server_name)
        if deleted:
            self.mcp_manager.unregister_server(server_name)
        return deleted

    def get_allowed_mcp_servers(self, app_id: str) -> list[str]:
        manifest = self.app_registry.get(app_id)
        app_config = self.settings.get_app_config(app_id)
        mcp_profile = manifest.profiles.mcp_profile
        allowed = list(
            mcp_profile.allowed_servers
            or app_config.allowed_mcp_servers
            or manifest.permissions.allowed_mcp_servers
        )
        for config in self.mcp_manager.list_configs():
            if not config.enabled:
                continue
            if config.allowed_app_ids and app_id not in config.allowed_app_ids:
                continue
            if config.server_name not in allowed:
                allowed.append(config.server_name)
        return allowed

    def build_tool_registry(self, app_id: str) -> ToolRegistry:
        manifest = self.app_registry.get(app_id)
        app_config = self.settings.get_app_config(app_id)
        mcp_profile = manifest.profiles.mcp_profile
        search_provider = self.settings.search.get_provider(self.settings.search.provider)
        registry = ToolRegistry()
        if "search" in manifest.permissions.allowed_tools:
            registry.register(
                BuiltinSearchTool(
                    provider=self.settings.search.provider,
                    default_max_results=app_config.search_max_results or self.settings.search.max_results,
                    provider_base_url=search_provider.base_url if search_provider else "",
                    provider_api_key=search_provider.api_key if search_provider else "",
                    searxng_url=self.settings.search_searxng_url,
                )
            )
        if "note" in manifest.permissions.allowed_tools:
            registry.register(BuiltinNoteTool(self.note_store))
        if app_id == "software_engineering":
            se_repo_root = Path(__file__).resolve().parents[4]
            for tool in build_software_engineering_tools(se_repo_root):
                if tool.name in manifest.permissions.allowed_tools:
                    registry.register(tool)
        if manifest.capabilities.mcp and self.settings.mcp.enabled and mcp_profile.enabled:
            allowed_servers = self.get_allowed_mcp_servers(app_id)
            allowed_tools = set(mcp_profile.allowed_tools)
            for server_name in allowed_servers:
                for descriptor in self.mcp_manager.discover_tools(server_name):
                    exposed_name = build_mcp_tool_name(server_name, descriptor.name)
                    if allowed_tools and descriptor.name not in allowed_tools and exposed_name not in allowed_tools:
                        continue
                    registry.register(
                        MCPToolAdapter(
                            self.mcp_manager,
                            descriptor,
                            exposed_name=exposed_name,
                        )
                    )
        return registry

    def build_context_builder(self, app_id: str) -> ContextBuilder:
        manifest = self.app_registry.get(app_id)
        provider_registry = ContextProviderRegistry()
        if manifest.capabilities.history:
            provider_registry.register(HistoryContextProvider(self.history_service))
        if manifest.capabilities.memory:
            provider_registry.register(MemoryContextProvider(self.memory_service))
        if manifest.capabilities.rag:
            provider_registry.register(RAGContextProvider(self.rag_service))
        if manifest.capabilities.notes:
            provider_registry.register(NotesContextProvider(self.note_store))
        return ContextBuilder(provider_registry=provider_registry)

    def list_skills(self) -> list[dict[str, object]]:
        return [
            {
                "skill_id": item.skill_id,
                "name": item.name,
                "description": item.description,
                "tags": item.tags,
                "tool_names": item.tool_names,
                "stage_configs": sorted(item.stage_configs.keys()),
                "source_dir": item.source_dir,
                "hydrated": item.hydrated,
                "resource_counts": {
                    "references": len(item.references),
                    "scripts": len(item.scripts),
                    "assets": len(item.assets),
                },
            }
            for item in self.skill_registry.list_skills()
        ]

    def reload_skills(self) -> dict[str, object]:
        self.skill_registry = SkillRegistry(self.skill_loader)
        self.skill_registry.scan()
        self.skill_runtime = PlatformSkillRuntime(self.skill_registry)
        return {
            "skills_root": str(self.skills_root),
            "skill_count": len(self.skill_registry.list_skills()),
        }

    def describe_app_skills(
        self,
        *,
        app_id: str,
        stage: str = "default",
        session_id: str = "skill-inspect",
        user_id: str | None = None,
    ) -> list[dict[str, object]]:
        manifest = self.app_registry.get(app_id)
        tool_registry = self.build_tool_registry(app_id)
        return self.skill_runtime.describe(
            context=BaseCapabilityContext(
                app_id=app_id,
                session_id=session_id,
                user_id=user_id,
                stage=stage,
            ),
            bindings=manifest.profiles.skills,
            available_tool_names={tool.name for tool in tool_registry.list_tools()},
        )

    def describe_app_skill_bindings(self, *, app_id: str) -> dict[str, object]:
        manifest = self.app_registry.get(app_id)
        context_profiles = sorted(manifest.profiles.context_profiles.keys())
        bindings = [
            {
                "skill_id": binding.skill_id,
                "stage": binding.stage,
                "enabled": binding.enabled,
                "priority": binding.priority,
                "metadata": binding.metadata,
            }
            for binding in sorted(manifest.profiles.skills, key=lambda item: (item.stage, item.priority, item.skill_id))
        ]
        return {
            "app_id": app_id,
            "app_name": manifest.name,
            "runtime_factory": manifest.runtime_factory,
            "context_profiles": context_profiles,
            "bindings": bindings,
        }

    def run_skills_eval(self) -> dict[str, object]:
        evaluator = SkillEvaluator(self.skill_registry, self.skill_runtime, self)
        return evaluator.evaluate()

    def explain_context(
        self,
        *,
        app_id: str,
        stage: str,
        session_id: str,
        user_id: str | None,
        user_input: str,
    ) -> dict[str, object]:
        runtime = self._build_runtime(app_id=app_id, session_id=session_id, user_id=user_id)
        if app_id == "chat" and hasattr(runtime, "_build_context_request"):
            request = runtime._build_context_request(user_input=user_input, trace_id=self.trace_service.new_trace_id())  # type: ignore[attr-defined]
            context_result = runtime.context_builder.build(request)  # type: ignore[attr-defined]
        else:
            manifest = self.app_registry.get(app_id)
            request = self._build_generic_context_request(
                app_id=app_id,
                stage=stage,
                session_id=session_id,
                user_id=user_id,
                user_input=user_input,
                context_profile=manifest.profiles.get_context_profile(stage),
                system_prompt=self._resolve_system_prompt(app_id, stage),
            )
            context_result = self.build_context_builder(app_id).build(request)

        tool_names = {tool.name for tool in self.build_tool_registry(app_id).list_tools()}
        skill_descriptions = self.skill_runtime.describe(
            BaseCapabilityContext(app_id=app_id, session_id=session_id, user_id=user_id, stage=stage),
            bindings=self.app_registry.get(app_id).profiles.skills,
            available_tool_names=tool_names,
        )
        return {
            "app_id": app_id,
            "stage": stage,
            "profile": request.profile,
            "request_metadata": request.metadata,
            "system_prompt_preview": request.system_prompt[:400],
            "sections": [{"title": section.title, "content": section.content} for section in context_result.sections],
            "packets": [
                {
                    "source": packet.metadata.get("source", "context"),
                    "token_count": packet.token_count,
                    "relevance_score": packet.relevance_score,
                    "metadata": packet.metadata,
                    "content_preview": packet.content[:300],
                }
                for packet in context_result.packets
            ],
            "prompt_preview": context_result.prompt[:2000],
            "diagnostics": context_result.diagnostics,
            "skills": skill_descriptions,
        }

    def run_context_eval(self) -> dict[str, object]:
        cases = [
            {"case_id": "chat.simple", "app_id": "chat", "stage": "chat.reply", "session_id": "ctx-eval-chat", "user_id": "ctx-eval-user", "user_input": "你好"},
            {
                "case_id": "chat.knowledge",
                "app_id": "chat",
                "stage": "chat.reply",
                "session_id": "ctx-eval-chat",
                "user_id": "ctx-eval-user",
                "user_input": "请根据我上传的文档总结这个PDF的关键结论",
            },
            {
                "case_id": "research.plan",
                "app_id": "deep_research",
                "stage": "research.plan",
                "session_id": "ctx-eval-research",
                "user_id": "ctx-eval-user",
                "user_input": "Research topic: AI agent platform architecture",
            },
            {
                "case_id": "research.report",
                "app_id": "deep_research",
                "stage": "research.report",
                "session_id": "ctx-eval-research",
                "user_id": "ctx-eval-user",
                "user_input": "Research topic: AI agent platform architecture\nWrite the final report.",
            },
        ]
        results: list[dict[str, object]] = []
        utilization_sum = 0.0
        dedupe_sum = 0.0
        compression_sum = 0.0
        source_diversity_sum = 0.0

        for case in cases:
            explained = self._explain_eval_case(case)
            diagnostics = dict(explained["diagnostics"])
            selected_tokens = float(diagnostics.get("selected_tokens", 0) or 0)
            compressed_tokens = float(diagnostics.get("compressed_tokens", 0) or 0)
            max_tokens = float(diagnostics.get("max_tokens", 1) or 1)
            selection = dict(diagnostics.get("selection", {}))
            gathered_count = int(diagnostics.get("gathered_count", 0) or 0)
            dropped_by_dedupe = int(selection.get("dropped_by_dedupe", 0) or 0)
            utilization = selected_tokens / max(1.0, max_tokens)
            dedupe_rate = dropped_by_dedupe / max(1, gathered_count)
            compression_gain = max(0.0, 1.0 - (compressed_tokens / max(1.0, selected_tokens)))
            source_diversity = len(dict(diagnostics.get("sources", {})))
            utilization_sum += utilization
            dedupe_sum += dedupe_rate
            compression_sum += compression_gain
            source_diversity_sum += source_diversity
            results.append(
                {
                    "case_id": case["case_id"],
                    "app_id": case["app_id"],
                    "stage": case["stage"],
                    "light_mode": bool(dict(explained.get("request_metadata", {})).get("light_mode", False)),
                    "selected_tokens": selected_tokens,
                    "compressed_tokens": compressed_tokens,
                    "max_tokens": max_tokens,
                    "utilization": utilization,
                    "dedupe_rate": dedupe_rate,
                    "compression_gain": compression_gain,
                    "source_diversity": source_diversity,
                    "sections": explained["diagnostics"].get("sections", []),
                    "sources": explained["diagnostics"].get("sources", {}),
                }
            )

        denominator = max(1, len(results))
        return {
            "average_utilization": utilization_sum / denominator,
            "average_dedupe_rate": dedupe_sum / denominator,
            "average_compression_gain": compression_sum / denominator,
            "average_source_diversity": source_diversity_sum / denominator,
            "cases": results,
        }

    def _explain_eval_case(self, case: dict[str, object]) -> dict[str, object]:
        app_id = str(case["app_id"])
        stage = str(case["stage"])
        session_id = str(case["session_id"])
        user_id = str(case["user_id"]) if case.get("user_id") else None
        user_input = str(case["user_input"])
        manifest = self.app_registry.get(app_id)
        context_profile = manifest.profiles.get_context_profile(stage)
        if app_id == "chat":
            runtime = self._build_runtime(app_id=app_id, session_id=session_id, user_id=user_id)
            request = runtime._build_context_request(user_input=user_input, trace_id=self.trace_service.new_trace_id())  # type: ignore[attr-defined]
        else:
            request = self._build_generic_context_request(
                app_id=app_id,
                stage=stage,
                session_id=session_id,
                user_id=user_id,
                user_input=user_input,
                context_profile=context_profile,
                system_prompt=self._resolve_system_prompt(app_id, stage),
            )
        request.inline_packets = self._build_eval_packets(case_id=str(case["case_id"]), app_id=app_id)
        context_result = self.build_context_builder(app_id).build(request)
        return {
            "app_id": app_id,
            "stage": stage,
            "profile": request.profile,
            "request_metadata": request.metadata,
            "sections": [{"title": section.title, "content": section.content} for section in context_result.sections],
            "diagnostics": context_result.diagnostics,
        }

    def run_app(self, *, app_id: str, session_id: str, user_input: str, user_id: str | None) -> dict[str, object]:
        runtime = self._build_runtime(app_id=app_id, session_id=session_id, user_id=user_id)
        return runtime.run(user_input=user_input)

    def stream_app(
        self,
        *,
        app_id: str,
        session_id: str,
        user_input: str,
        user_id: str | None,
    ) -> Iterator[dict[str, object]]:
        runtime = self._build_runtime(app_id=app_id, session_id=session_id, user_id=user_id)
        return runtime.stream(user_input=user_input)

    def _build_runtime(self, *, app_id: str, session_id: str, user_id: str | None):
        manifest = self.app_registry.get(app_id)
        tool_registry = self.build_tool_registry(app_id)
        context_builder = self.build_context_builder(app_id)
        tool_executor = ToolExecutor(tool_registry, trace_service=self.trace_service)
        app_config = self.settings.get_app_config(app_id)
        model_name = app_config.default_model or self.settings.llm_model
        build_context = RuntimeBuildContext(
            manifest=manifest,
            session_id=session_id,
            user_id=user_id,
            model_client=self.model_client,
            model_name=model_name,
            history_service=self.history_service,
            memory_service=self.memory_service,
            rag_service=self.rag_service,
            note_store=self.note_store,
            context_builder=context_builder,
            skill_runtime=self.skill_runtime,
            tool_registry=tool_registry,
            tool_executor=tool_executor,
            trace_service=self.trace_service,
            settings=self.settings,
            dependencies={
                "research_run_store": self.research_run_store,
                "mcp_manager": self.mcp_manager,
                "se_run_store": self.se_run_store,
                "repo_root": Path(__file__).resolve().parents[4],
            },
        )
        return self.runtime_factories.create(manifest.runtime_factory, build_context)

    def _build_generic_context_request(
        self,
        *,
        app_id: str,
        stage: str,
        session_id: str,
        user_id: str | None,
        user_input: str,
        context_profile: ContextProfile,
        system_prompt: str,
    ) -> ContextBuildRequest:
        manifest = self.app_registry.get(app_id)
        memory_profile = manifest.profiles.memory_profile
        rag_profile = manifest.profiles.rag_profile
        return ContextBuildRequest(
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            user_input=user_input,
            system_prompt=system_prompt,
            profile=context_profile.profile_id,
            max_tokens=context_profile.max_tokens,
            history_limit=context_profile.history_limit,
            knowledge_scopes=context_profile.knowledge_scopes or [app_id],
            provider_order=context_profile.provider_order,
            metadata={
                "trace_id": self.trace_service.new_trace_id(),
                "memory_scope": memory_profile.retrieval_scope or context_profile.memory_scope,
                "memory_limit": memory_profile.retrieval_limit,
                "memory_types": memory_profile.retrieval_types,
                "memory_min_importance": memory_profile.min_importance,
                "memory_type_weights": {"semantic": 0.16, "episodic": 0.1, "working": 0.04, "perceptual": 0.08, "graph": 0.14},
                "memory_retrieval_mode": memory_profile.retrieval_mode,
                "memory_include_graph": memory_profile.graph_enabled,
                "rag_limit": rag_profile.retrieval_limit,
                "rag_retrieval_mode": rag_profile.retrieval_mode,
                "rag_include_public": rag_profile.include_public,
                "rag_include_app_shared": rag_profile.include_app_shared,
                "rag_include_user_private": rag_profile.include_user_private,
                "rag_include_session_temporary": rag_profile.include_session_temporary,
                "rag_query_rewrite_enabled": rag_profile.query_rewrite_enabled,
                "rag_query_rewrite_mode": rag_profile.query_rewrite_mode,
                "rag_mqe_variants": rag_profile.mqe_variants,
                "rag_hyde_enabled": rag_profile.hyde_enabled,
                "rag_hyde_mode": rag_profile.hyde_mode,
                "rag_rerank_enabled": rag_profile.rerank_enabled,
                "rag_rerank_strategy": rag_profile.rerank_strategy,
                "rag_rerank_top_n": rag_profile.rerank_top_n,
                "note_scope": context_profile.note_scope,
            },
        )

    @staticmethod
    def _resolve_system_prompt(app_id: str, stage: str) -> str:
        if app_id == "chat":
            return CHAT_SYSTEM_PROMPT
        if stage == "research.plan":
            return PLANNER_PROMPT
        if stage == "research.summarize":
            return SUMMARIZER_PROMPT
        if stage == "research.report":
            return REPORTER_PROMPT
        return ""

    @staticmethod
    def _build_eval_packets(*, case_id: str, app_id: str) -> list[ContextPacket]:
        if case_id == "chat.simple":
            return [
                ContextPacket(content="user: 我喜欢徒步旅行和轻小说。", token_count=8, relevance_score=0.62, metadata={"source": "history"}),
                ContextPacket(content="assistant: 已记住你的爱好偏好。", token_count=6, relevance_score=0.58, metadata={"source": "history"}),
                ContextPacket(content="[memory] user prefers hiking and light novels", token_count=7, relevance_score=0.84, metadata={"source": "memory"}),
            ]
        if case_id == "chat.knowledge":
            return [
                ContextPacket(content="[memory] user is preparing a report about agent systems", token_count=9, relevance_score=0.72, metadata={"source": "memory"}),
                ContextPacket(content="Chunk: c1\nSection: Intro\nA PDF summary says the platform uses modular runtimes and tool registries for agent apps.", token_count=18, relevance_score=0.91, metadata={"source": "rag", "chunk_id": "c1"}),
                ContextPacket(content="Chunk: c1\nSection: Intro\nA PDF summary says the platform uses modular runtimes and tool registries for agent apps.", token_count=18, relevance_score=0.78, metadata={"source": "rag", "chunk_id": "c1"}),
            ]
        if case_id == "research.plan":
            return [
                ContextPacket(content="[memory] previous research emphasized platform modularity", token_count=8, relevance_score=0.7, metadata={"source": "memory"}),
                ContextPacket(content="[note:goal] compare orchestration, context, memory, and protocol integration", token_count=10, relevance_score=0.82, metadata={"source": "notes"}),
                ContextPacket(content="Chunk: rp1\nSection: Survey\nRecent agent platform papers focus on orchestration, tool ecosystems, and observability.", token_count=15, relevance_score=0.88, metadata={"source": "rag", "chunk_id": "rp1"}),
            ]
        return [
            ContextPacket(content="[task_summary] Task 1 found that modular runtimes reduce coupling between apps.", token_count=12, relevance_score=0.9, metadata={"source": "task_summary"}),
            ContextPacket(content="[task_summary] Task 2 found that context budgets reduce prompt bloat.", token_count=12, relevance_score=0.87, metadata={"source": "task_summary"}),
            ContextPacket(content="[note:report] final report should emphasize scope isolation and explainability", token_count=11, relevance_score=0.8, metadata={"source": "notes"}),
            ContextPacket(content="Chunk: rr1\nSection: Findings\nEvidence shows platform-level context management improves consistency across multi-agent apps.", token_count=16, relevance_score=0.89, metadata={"source": "rag", "chunk_id": "rr1"}),
        ]


@lru_cache(maxsize=1)
def get_orchestrator() -> AppOrchestrator:
    return AppOrchestrator()
