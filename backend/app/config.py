from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import re
from typing import Any


def _load_env_file(path: Path) -> bool:
    if not path.exists():
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
    return True


def _load_env_files(paths: list[Path]) -> list[Path]:
    loaded: list[Path] = []
    for path in paths:
        if _load_env_file(path):
            loaded.append(path.resolve())
    return loaded


def _env(key: str, default: str, *, allow_blank: bool = False) -> str:
    value = os.getenv(key)
    if value is None:
        return default
    if not allow_blank and not value.strip():
        return default
    return value


def _env_bool(key: str, default: bool) -> bool:
    raw = _env(key, str(default))
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    return int(_env(key, str(default)))


def _env_float(key: str, default: float) -> float:
    return float(_env(key, str(default)))


def _env_list(key: str, default: list[str]) -> list[str]:
    raw = _env(key, ",".join(default))
    return [item.strip() for item in raw.split(",") if item.strip()]


_ENV_REF_PATTERN = re.compile(r"\$\{(?P<name>[A-Z0-9_]+)\}")


def _expand_env_refs(value: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        return os.getenv(match.group("name"), "")

    return _ENV_REF_PATTERN.sub(replacer, value)


def _load_toml_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as file:
        return tomllib.load(file)


def _get_nested(config: dict[str, Any], dotted_key: str, default: Any) -> Any:
    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _resolve_path(base_dir: Path, raw_value: str) -> Path:
    path = Path(raw_value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


@dataclass(slots=True)
class AppSettings:
    name: str
    env: str
    host: str
    port: int
    cors_origins: list[str]


@dataclass(slots=True)
class ModelSettings:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    temperature: float


@dataclass(slots=True)
class SearchProviderSettings:
    name: str
    enabled: bool
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@dataclass(slots=True)
class SearchSettings:
    provider: str
    max_results: int
    providers: dict[str, SearchProviderSettings] = field(default_factory=dict)

    def get_provider(self, provider_name: str | None = None) -> SearchProviderSettings | None:
        key = provider_name or self.provider
        return self.providers.get(key)


@dataclass(slots=True)
class EmbeddingSettings:
    provider: str
    model: str
    base_url: str
    api_key: str


@dataclass(slots=True)
class StorageSettings:
    root: Path
    history_db: Path
    memory_db: Path
    trace_db: Path
    rag_store: Path
    notes_path: Path
    research_runs_path: Path


@dataclass(slots=True)
class MemorySettings:
    backend: str
    extraction_mode: str
    embedding_mode: str
    graph_enabled: bool
    perceptual_enabled: bool
    forgetting_enabled: bool
    conflict_strategy: str
    local_embedding_dimensions: int


@dataclass(slots=True)
class RAGSettings:
    backend: str
    chunk_size: int
    chunk_overlap: int
    retrieval_limit: int
    qdrant_collection: str
    query_rewrite_mode: str
    mqe_variants: int
    hyde_max_tokens: int
    rerank_strategy: str
    rerank_top_n: int
    url_timeout_seconds: float


@dataclass(slots=True)
class MCPServerSettings:
    name: str
    enabled: bool = False
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    description: str = ""
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class MCPSettings:
    enabled: bool
    default_transport: str
    servers: dict[str, MCPServerSettings] = field(default_factory=dict)

    def enabled_servers(self) -> list[MCPServerSettings]:
        return [server for server in self.servers.values() if server.enabled]


@dataclass(slots=True)
class VectorStoreSettings:
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str


@dataclass(slots=True)
class GraphStoreSettings:
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str


@dataclass(slots=True)
class IntegrationSettings:
    tavily_api_key: str
    serpapi_api_key: str
    perplexity_api_key: str
    github_personal_access_token: str
    amap_api_key: str
    unsplash_access_key: str
    unsplash_secret_key: str


@dataclass(slots=True)
class RuntimeSettings:
    default_history_limit: int
    default_context_token_budget: int
    default_tool_iterations: int


@dataclass(slots=True)
class ResearchSettings:
    default_task_count: int
    sources_per_task: int
    max_parallel_tasks: int


@dataclass(slots=True)
class AppRuntimeSettings:
    app_id: str
    enabled: bool = True
    default_model: str = ""
    history_limit: int = 0
    tool_iterations: int = 0
    search_max_results: int = 0
    allowed_tools: list[str] = field(default_factory=list)
    allowed_mcp_servers: list[str] = field(default_factory=list)
    knowledge_scopes: list[str] = field(default_factory=list)
    capabilities: dict[str, bool] = field(default_factory=dict)


@dataclass(slots=True)
class Settings:
    app: AppSettings
    model: ModelSettings
    search: SearchSettings
    embedding: EmbeddingSettings
    storage: StorageSettings
    memory: MemorySettings
    rag: RAGSettings
    mcp: MCPSettings
    vector_store: VectorStoreSettings
    graph_store: GraphStoreSettings
    integrations: IntegrationSettings
    runtime: RuntimeSettings
    research: ResearchSettings
    apps: dict[str, AppRuntimeSettings]
    config_file_path: Path
    env_files_loaded: list[Path]

    def get_app_config(self, app_id: str) -> AppRuntimeSettings:
        return self.apps.get(app_id, AppRuntimeSettings(app_id=app_id))

    def is_app_enabled(self, app_id: str) -> bool:
        return self.get_app_config(app_id).enabled

    @property
    def app_name(self) -> str:
        return self.app.name

    @property
    def app_env(self) -> str:
        return self.app.env

    @property
    def app_host(self) -> str:
        return self.app.host

    @property
    def app_port(self) -> int:
        return self.app.port

    @property
    def cors_origins(self) -> list[str]:
        return self.app.cors_origins

    @property
    def llm_provider(self) -> str:
        return self.model.provider

    @property
    def llm_base_url(self) -> str:
        return self.model.base_url

    @property
    def llm_api_key(self) -> str:
        return self.model.api_key

    @property
    def llm_model(self) -> str:
        return self.model.model

    @property
    def llm_timeout_seconds(self) -> float:
        return self.model.timeout_seconds

    @property
    def llm_temperature(self) -> float:
        return self.model.temperature

    @property
    def search_provider(self) -> str:
        return self.search.provider

    @property
    def search_max_results(self) -> int:
        return self.search.max_results

    @property
    def search_searxng_url(self) -> str:
        provider = self.search.get_provider("searxng")
        return provider.base_url if provider else ""

    @property
    def embed_provider(self) -> str:
        return self.embedding.provider

    @property
    def embed_model(self) -> str:
        return self.embedding.model

    @property
    def embed_base_url(self) -> str:
        return self.embedding.base_url

    @property
    def embed_api_key(self) -> str:
        return self.embedding.api_key

    @property
    def storage_root(self) -> Path:
        return self.storage.root

    @property
    def history_db_path(self) -> Path:
        return self.storage.history_db

    @property
    def memory_db_path(self) -> Path:
        return self.storage.memory_db

    @property
    def trace_db_path(self) -> Path:
        return self.storage.trace_db

    @property
    def rag_store_path(self) -> Path:
        return self.storage.rag_store

    @property
    def notes_path(self) -> Path:
        return self.storage.notes_path

    @property
    def research_runs_path(self) -> Path:
        return self.storage.research_runs_path

    @property
    def memory_backend(self) -> str:
        return self.memory.backend

    @property
    def memory_extraction_mode(self) -> str:
        return self.memory.extraction_mode

    @property
    def memory_embedding_mode(self) -> str:
        return self.memory.embedding_mode

    @property
    def memory_graph_enabled(self) -> bool:
        return self.memory.graph_enabled

    @property
    def memory_perceptual_enabled(self) -> bool:
        return self.memory.perceptual_enabled

    @property
    def memory_forgetting_enabled(self) -> bool:
        return self.memory.forgetting_enabled

    @property
    def memory_conflict_strategy(self) -> str:
        return self.memory.conflict_strategy

    @property
    def memory_local_embedding_dimensions(self) -> int:
        return self.memory.local_embedding_dimensions

    @property
    def rag_backend(self) -> str:
        return self.rag.backend

    @property
    def rag_chunk_size(self) -> int:
        return self.rag.chunk_size

    @property
    def rag_chunk_overlap(self) -> int:
        return self.rag.chunk_overlap

    @property
    def rag_retrieval_limit(self) -> int:
        return self.rag.retrieval_limit

    @property
    def rag_qdrant_collection(self) -> str:
        return self.rag.qdrant_collection

    @property
    def rag_query_rewrite_mode(self) -> str:
        return self.rag.query_rewrite_mode

    @property
    def rag_mqe_variants(self) -> int:
        return self.rag.mqe_variants

    @property
    def rag_hyde_max_tokens(self) -> int:
        return self.rag.hyde_max_tokens

    @property
    def rag_rerank_strategy(self) -> str:
        return self.rag.rerank_strategy

    @property
    def rag_rerank_top_n(self) -> int:
        return self.rag.rerank_top_n

    @property
    def rag_url_timeout_seconds(self) -> float:
        return self.rag.url_timeout_seconds

    @property
    def mcp_enabled(self) -> bool:
        return self.mcp.enabled

    @property
    def mcp_default_transport(self) -> str:
        return self.mcp.default_transport

    @property
    def qdrant_url(self) -> str:
        return self.vector_store.qdrant_url

    @property
    def qdrant_api_key(self) -> str:
        return self.vector_store.qdrant_api_key

    @property
    def qdrant_collection(self) -> str:
        return self.vector_store.qdrant_collection

    @property
    def neo4j_uri(self) -> str:
        return self.graph_store.neo4j_uri

    @property
    def neo4j_username(self) -> str:
        return self.graph_store.neo4j_username

    @property
    def neo4j_password(self) -> str:
        return self.graph_store.neo4j_password

    @property
    def tavily_api_key(self) -> str:
        return self.integrations.tavily_api_key

    @property
    def serpapi_api_key(self) -> str:
        return self.integrations.serpapi_api_key

    @property
    def perplexity_api_key(self) -> str:
        return self.integrations.perplexity_api_key

    @property
    def github_personal_access_token(self) -> str:
        return self.integrations.github_personal_access_token

    @property
    def amap_api_key(self) -> str:
        return self.integrations.amap_api_key

    @property
    def unsplash_access_key(self) -> str:
        return self.integrations.unsplash_access_key

    @property
    def unsplash_secret_key(self) -> str:
        return self.integrations.unsplash_secret_key

    @property
    def default_history_limit(self) -> int:
        return self.runtime.default_history_limit

    @property
    def default_context_token_budget(self) -> int:
        return self.runtime.default_context_token_budget

    @property
    def default_tool_iterations(self) -> int:
        return self.runtime.default_tool_iterations

    @property
    def research_default_task_count(self) -> int:
        return self.research.default_task_count

    @property
    def research_sources_per_task(self) -> int:
        return self.research.sources_per_task

    @property
    def research_max_parallel_tasks(self) -> int:
        return self.research.max_parallel_tasks


def _build_search_settings(toml_config: dict[str, Any]) -> SearchSettings:
    provider = _env("SEARCH_PROVIDER", str(_get_nested(toml_config, "search.provider", "duckduckgo")))
    max_results = _env_int("SEARCH_MAX_RESULTS", int(_get_nested(toml_config, "search.max_results", 5)))

    providers: dict[str, SearchProviderSettings] = {
        "duckduckgo": SearchProviderSettings(name="duckduckgo", enabled=True),
        "tavily": SearchProviderSettings(
            name="tavily",
            enabled=bool(_env("TAVILY_API_KEY", str(_get_nested(toml_config, "integrations.tavily_api_key", "")), allow_blank=True)),
            base_url=str(_get_nested(toml_config, "search.providers.tavily.base_url", "https://api.tavily.com")),
            api_key=_env("TAVILY_API_KEY", str(_get_nested(toml_config, "integrations.tavily_api_key", "")), allow_blank=True),
        ),
        "serpapi": SearchProviderSettings(
            name="serpapi",
            enabled=bool(_env("SERPAPI_API_KEY", str(_get_nested(toml_config, "integrations.serpapi_api_key", "")), allow_blank=True)),
            base_url=str(_get_nested(toml_config, "search.providers.serpapi.base_url", "https://serpapi.com")),
            api_key=_env("SERPAPI_API_KEY", str(_get_nested(toml_config, "integrations.serpapi_api_key", "")), allow_blank=True),
        ),
        "perplexity": SearchProviderSettings(
            name="perplexity",
            enabled=bool(
                _env("PERPLEXITY_API_KEY", str(_get_nested(toml_config, "integrations.perplexity_api_key", "")), allow_blank=True)
            ),
            base_url=str(_get_nested(toml_config, "search.providers.perplexity.base_url", "https://api.perplexity.ai")),
            api_key=_env(
                "PERPLEXITY_API_KEY",
                str(_get_nested(toml_config, "integrations.perplexity_api_key", "")),
                allow_blank=True,
            ),
            model=str(_get_nested(toml_config, "search.providers.perplexity.model", "sonar")),
        ),
        "searxng": SearchProviderSettings(
            name="searxng",
            enabled=bool(_env("SEARXNG_URL", str(_get_nested(toml_config, "search.providers.searxng.base_url", "")))),
            base_url=_env("SEARXNG_URL", str(_get_nested(toml_config, "search.providers.searxng.base_url", ""))),
        ),
    }
    return SearchSettings(provider=provider, max_results=max_results, providers=providers)


def _build_mcp_settings(toml_config: dict[str, Any]) -> MCPSettings:
    raw_servers = _get_nested(toml_config, "mcp.servers", [])
    servers: dict[str, MCPServerSettings] = {}
    for item in raw_servers:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        servers[name] = MCPServerSettings(
            name=name,
            enabled=bool(item.get("enabled", False)),
            transport=str(item.get("transport", "stdio")),
            command=str(item.get("command", "")),
            args=[str(arg) for arg in item.get("args", [])],
            url=str(item.get("url", "")),
            description=str(item.get("description", "")),
            env={str(key): _expand_env_refs(str(value)) for key, value in dict(item.get("env", {})).items()},
            headers={str(key): _expand_env_refs(str(value)) for key, value in dict(item.get("headers", {})).items()},
        )
    return MCPSettings(
        enabled=_env_bool("MCP_ENABLED", bool(_get_nested(toml_config, "mcp.enabled", False))),
        default_transport=_env("MCP_DEFAULT_TRANSPORT", str(_get_nested(toml_config, "mcp.default_transport", "stdio"))),
        servers=servers,
    )


def _build_app_configs(toml_config: dict[str, Any]) -> dict[str, AppRuntimeSettings]:
    raw_apps = toml_config.get("apps", {})
    app_configs: dict[str, AppRuntimeSettings] = {}
    for app_id, item in raw_apps.items():
        if app_id == "enabled" or not isinstance(item, dict):
            continue
        capabilities = item.get("capabilities", {})
        app_configs[app_id] = AppRuntimeSettings(
            app_id=app_id,
            enabled=bool(item.get("enabled", True)),
            default_model=str(item.get("default_model", "")),
            history_limit=int(item.get("history_limit", 0)),
            tool_iterations=int(item.get("tool_iterations", 0)),
            search_max_results=int(item.get("search_max_results", 0)),
            allowed_tools=[str(value) for value in item.get("allowed_tools", [])],
            allowed_mcp_servers=[str(value) for value in item.get("allowed_mcp_servers", [])],
            knowledge_scopes=[str(value) for value in item.get("knowledge_scopes", [])],
            capabilities={str(key): bool(value) for key, value in dict(capabilities).items()},
        )
    return app_configs


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    app_root = Path(__file__).resolve().parent
    backend_root = app_root.parent
    env_files_loaded = _load_env_files([backend_root / ".env", backend_root / ".env.local"])

    default_config_file = backend_root / "config" / "platform.toml"
    config_file_path = Path(_env("APP_CONFIG_FILE", str(default_config_file))).resolve()
    toml_config = _load_toml_config(config_file_path)

    storage_root = _resolve_path(
        backend_root,
        str(_get_nested(toml_config, "storage.root", _env("STORAGE_ROOT", str(app_root / "storage")))),
    )

    settings = Settings(
        app=AppSettings(
            name=_env("APP_NAME", str(_get_nested(toml_config, "app.name", "Agent Platform V1"))),
            env=_env("APP_ENV", str(_get_nested(toml_config, "app.env", "development"))),
            host=_env("APP_HOST", str(_get_nested(toml_config, "app.host", "0.0.0.0"))),
            port=_env_int("APP_PORT", int(_get_nested(toml_config, "app.port", 8080))),
            cors_origins=_env_list("CORS_ORIGINS", list(_get_nested(toml_config, "app.cors_origins", ["http://localhost:5173"]))),
        ),
        model=ModelSettings(
            provider=_env("LLM_PROVIDER", str(_get_nested(toml_config, "model.provider", "openai_compat"))),
            base_url=_env("LLM_BASE_URL", str(_get_nested(toml_config, "model.base_url", "https://api.openai.com/v1"))),
            api_key=_env("LLM_API_KEY", str(_get_nested(toml_config, "model.api_key", "")), allow_blank=True),
            model=_env("LLM_MODEL", str(_get_nested(toml_config, "model.model", "gpt-4o-mini"))),
            timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", float(_get_nested(toml_config, "model.timeout_seconds", 60))),
            temperature=_env_float("LLM_TEMPERATURE", float(_get_nested(toml_config, "model.temperature", 0.2))),
        ),
        search=_build_search_settings(toml_config),
        embedding=EmbeddingSettings(
            provider=_env("EMBED_PROVIDER", str(_get_nested(toml_config, "embedding.provider", "none"))),
            model=_env("EMBED_MODEL", str(_get_nested(toml_config, "embedding.model", "")), allow_blank=True),
            base_url=_env("EMBED_BASE_URL", str(_get_nested(toml_config, "embedding.base_url", "")), allow_blank=True),
            api_key=_env("EMBED_API_KEY", str(_get_nested(toml_config, "embedding.api_key", "")), allow_blank=True),
        ),
        storage=StorageSettings(
            root=storage_root,
            history_db=_resolve_path(
                backend_root,
                _env("HISTORY_DB_PATH", str(_get_nested(toml_config, "storage.history_db", str(storage_root / "sqlite" / "history.db")))),
            ),
            memory_db=_resolve_path(
                backend_root,
                _env("MEMORY_DB_PATH", str(_get_nested(toml_config, "storage.memory_db", str(storage_root / "sqlite" / "memory.db")))),
            ),
            trace_db=_resolve_path(
                backend_root,
                _env("TRACE_DB_PATH", str(_get_nested(toml_config, "storage.trace_db", str(storage_root / "sqlite" / "traces.db")))),
            ),
            rag_store=_resolve_path(
                backend_root,
                _env("RAG_STORE_PATH", str(_get_nested(toml_config, "storage.rag_store", str(storage_root / "knowledge")))),
            ),
            notes_path=_resolve_path(
                backend_root,
                _env("NOTES_PATH", str(_get_nested(toml_config, "storage.notes_path", str(storage_root / "notes")))),
            ),
            research_runs_path=_resolve_path(
                backend_root,
                _env(
                    "RESEARCH_RUNS_PATH",
                    str(_get_nested(toml_config, "storage.research_runs_path", str(storage_root / "research_runs"))),
                ),
            ),
        ),
        memory=MemorySettings(
            backend=_env("MEMORY_BACKEND", str(_get_nested(toml_config, "memory.backend", "sqlite"))),
            extraction_mode=_env("MEMORY_EXTRACTION_MODE", str(_get_nested(toml_config, "memory.extraction_mode", "hybrid"))),
            embedding_mode=_env("MEMORY_EMBEDDING_MODE", str(_get_nested(toml_config, "memory.embedding_mode", "auto"))),
            graph_enabled=_env_bool("MEMORY_GRAPH_ENABLED", bool(_get_nested(toml_config, "memory.graph_enabled", True))),
            perceptual_enabled=_env_bool(
                "MEMORY_PERCEPTUAL_ENABLED",
                bool(_get_nested(toml_config, "memory.perceptual_enabled", True)),
            ),
            forgetting_enabled=_env_bool(
                "MEMORY_FORGETTING_ENABLED",
                bool(_get_nested(toml_config, "memory.forgetting_enabled", True)),
            ),
            conflict_strategy=_env("MEMORY_CONFLICT_STRATEGY", str(_get_nested(toml_config, "memory.conflict_strategy", "confidence"))),
            local_embedding_dimensions=_env_int(
                "MEMORY_LOCAL_EMBEDDING_DIMENSIONS",
                int(_get_nested(toml_config, "memory.local_embedding_dimensions", 128)),
            ),
        ),
        rag=RAGSettings(
            backend=_env("RAG_BACKEND", str(_get_nested(toml_config, "rag.backend", "local"))),
            chunk_size=_env_int("RAG_CHUNK_SIZE", int(_get_nested(toml_config, "rag.chunk_size", 500))),
            chunk_overlap=_env_int("RAG_CHUNK_OVERLAP", int(_get_nested(toml_config, "rag.chunk_overlap", 50))),
            retrieval_limit=_env_int("RAG_RETRIEVAL_LIMIT", int(_get_nested(toml_config, "rag.retrieval_limit", 5))),
            qdrant_collection=_env(
                "RAG_QDRANT_COLLECTION",
                str(_get_nested(toml_config, "rag.qdrant_collection", "agent_platform_v1_rag")),
            ),
            query_rewrite_mode=_env(
                "RAG_QUERY_REWRITE_MODE",
                str(_get_nested(toml_config, "rag.query_rewrite_mode", "hybrid")),
            ),
            mqe_variants=_env_int("RAG_MQE_VARIANTS", int(_get_nested(toml_config, "rag.mqe_variants", 4))),
            hyde_max_tokens=_env_int("RAG_HYDE_MAX_TOKENS", int(_get_nested(toml_config, "rag.hyde_max_tokens", 220))),
            rerank_strategy=_env(
                "RAG_RERANK_STRATEGY",
                str(_get_nested(toml_config, "rag.rerank_strategy", "feature")),
            ),
            rerank_top_n=_env_int("RAG_RERANK_TOP_N", int(_get_nested(toml_config, "rag.rerank_top_n", 12))),
            url_timeout_seconds=_env_float(
                "RAG_URL_TIMEOUT_SECONDS",
                float(_get_nested(toml_config, "rag.url_timeout_seconds", 20)),
            ),
        ),
        mcp=_build_mcp_settings(toml_config),
        vector_store=VectorStoreSettings(
            qdrant_url=_env("QDRANT_URL", str(_get_nested(toml_config, "vector_store.qdrant_url", "")), allow_blank=True),
            qdrant_api_key=_env("QDRANT_API_KEY", str(_get_nested(toml_config, "vector_store.qdrant_api_key", "")), allow_blank=True),
            qdrant_collection=_env("QDRANT_COLLECTION", str(_get_nested(toml_config, "vector_store.qdrant_collection", "agent_platform_v1"))),
        ),
        graph_store=GraphStoreSettings(
            neo4j_uri=_env("NEO4J_URI", str(_get_nested(toml_config, "graph_store.neo4j_uri", "")), allow_blank=True),
            neo4j_username=_env("NEO4J_USERNAME", str(_get_nested(toml_config, "graph_store.neo4j_username", "")), allow_blank=True),
            neo4j_password=_env("NEO4J_PASSWORD", str(_get_nested(toml_config, "graph_store.neo4j_password", "")), allow_blank=True),
        ),
        integrations=IntegrationSettings(
            tavily_api_key=_env("TAVILY_API_KEY", str(_get_nested(toml_config, "integrations.tavily_api_key", "")), allow_blank=True),
            serpapi_api_key=_env("SERPAPI_API_KEY", str(_get_nested(toml_config, "integrations.serpapi_api_key", "")), allow_blank=True),
            perplexity_api_key=_env(
                "PERPLEXITY_API_KEY",
                str(_get_nested(toml_config, "integrations.perplexity_api_key", "")),
                allow_blank=True,
            ),
            github_personal_access_token=_env(
                "GITHUB_PERSONAL_ACCESS_TOKEN",
                str(_get_nested(toml_config, "integrations.github_personal_access_token", "")),
                allow_blank=True,
            ),
            amap_api_key=_env("AMAP_API_KEY", str(_get_nested(toml_config, "integrations.amap_api_key", "")), allow_blank=True),
            unsplash_access_key=_env(
                "UNSPLASH_ACCESS_KEY",
                str(_get_nested(toml_config, "integrations.unsplash_access_key", "")),
                allow_blank=True,
            ),
            unsplash_secret_key=_env(
                "UNSPLASH_SECRET_KEY",
                str(_get_nested(toml_config, "integrations.unsplash_secret_key", "")),
                allow_blank=True,
            ),
        ),
        runtime=RuntimeSettings(
            default_history_limit=_env_int(
                "DEFAULT_HISTORY_LIMIT",
                int(_get_nested(toml_config, "runtime.default_history_limit", 20)),
            ),
            default_context_token_budget=_env_int(
                "DEFAULT_CONTEXT_TOKEN_BUDGET",
                int(_get_nested(toml_config, "runtime.default_context_token_budget", 6000)),
            ),
            default_tool_iterations=_env_int(
                "DEFAULT_TOOL_ITERATIONS",
                int(_get_nested(toml_config, "runtime.default_tool_iterations", 2)),
            ),
        ),
        research=ResearchSettings(
            default_task_count=_env_int(
                "RESEARCH_DEFAULT_TASK_COUNT",
                int(_get_nested(toml_config, "research.default_task_count", 4)),
            ),
            sources_per_task=_env_int(
                "RESEARCH_SOURCES_PER_TASK",
                int(_get_nested(toml_config, "research.sources_per_task", 5)),
            ),
            max_parallel_tasks=_env_int(
                "RESEARCH_MAX_PARALLEL_TASKS",
                int(_get_nested(toml_config, "research.max_parallel_tasks", 3)),
            ),
        ),
        apps=_build_app_configs(toml_config),
        config_file_path=config_file_path,
        env_files_loaded=env_files_loaded,
    )

    settings.storage.root.mkdir(parents=True, exist_ok=True)
    settings.storage.history_db.parent.mkdir(parents=True, exist_ok=True)
    settings.storage.memory_db.parent.mkdir(parents=True, exist_ok=True)
    settings.storage.trace_db.parent.mkdir(parents=True, exist_ok=True)
    settings.storage.rag_store.mkdir(parents=True, exist_ok=True)
    settings.storage.notes_path.mkdir(parents=True, exist_ok=True)
    settings.storage.research_runs_path.mkdir(parents=True, exist_ok=True)
    return settings
