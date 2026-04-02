export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8080";

export interface AppManifest {
  app_id: string;
  name: string;
  description: string;
  runtime_kind: string;
  capabilities: Record<string, boolean>;
  tags: string[];
}

export interface SessionMessage {
  role: string;
  content: string;
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface SessionSummary {
  session_id: string;
  app_id: string;
  title: string;
  preview: string;
  message_count: number;
  updated_at: string;
}

export interface RunEvent {
  type: string;
  [key: string]: unknown;
}

export interface ResearchTaskRecord {
  task_id: number;
  title: string;
  query: string;
  goal: string;
  summary: string;
  note_id?: string | null;
  sources: ResearchCitation[];
}

export interface ResearchCitation {
  title?: string;
  url?: string;
  snippet?: string;
}

export interface ResearchRunSummary {
  session_id: string;
  app_id: string;
  topic: string;
  status: string;
  report_preview: string;
  task_count: number;
  created_at: string;
  updated_at: string;
}

export interface ResearchRunRecord {
  session_id: string;
  app_id: string;
  topic: string;
  user_id?: string | null;
  status: string;
  report: string;
  tasks: ResearchTaskRecord[];
  events: RunEvent[];
  created_at: string;
  updated_at: string;
}

export interface MemoryStatus {
  memory_backend: string;
  extraction_mode: string;
  embedding_mode: string;
  vector_backend: {
    enabled: boolean;
    collection: string;
    base_url: string;
  };
  graph_backend: {
    enabled: boolean;
    active_uri: string;
  };
  llm_extraction: {
    configured_model: string;
    configured: boolean;
  };
}

export interface MemorySummary {
  count: number;
  archived: number;
  by_type: Record<string, number>;
  by_status: Record<string, number>;
  graph: {
    nodes: number;
    edges: number;
  };
}

export interface MemoryRecord {
  memory_id: string;
  app_id: string;
  session_id: string;
  user_id?: string | null;
  memory_type: string;
  importance: number;
  tags: string[];
  metadata: Record<string, unknown>;
  source_kind: string;
  source_confidence: number;
  canonical_key: string;
  checksum: string;
  status: string;
  superseded_by: string;
  embedding: number[];
  content: string;
  access_count: number;
  last_accessed_at?: string | null;
  expires_at?: string | null;
  archived: boolean;
  created_at: string;
  score?: number;
}

export interface MemoryEvalCase {
  case_id: string;
  recall_at_k: number;
  precision_at_k: number;
  pollution_rate: number;
  retrieved: string[];
  expected: string[];
}

export interface MemoryEvalSummary {
  average_recall_at_k: number;
  average_precision_at_k: number;
  average_pollution_rate: number;
  conflict_resolution_quality: number;
  cases: MemoryEvalCase[];
}

export interface RAGStatus {
  backend: string;
  retriever: {
    default_mode: string;
    rerank_strategy: string;
  };
  embedding: {
    provider: string;
    configured_model: string;
  };
  vector_backend: {
    enabled: boolean;
    collection: string;
    base_url: string;
    exists?: boolean;
    vector_size?: number;
    points_count?: number;
    status?: string;
  };
  documents: {
    document_count: number;
    chunk_count: number;
    by_visibility: Record<string, number>;
    by_source_type: Record<string, number>;
  };
  model: {
    configured_model: string;
    available: boolean;
  };
  features: {
    url_import: boolean;
    rerank: boolean;
    mqe: boolean;
    hyde: boolean;
    structured_sources: boolean;
  };
}

export interface RAGScopeSummary {
  kb_id: string;
  visibility: string;
  app_id: string;
  user_id?: string | null;
  session_id?: string | null;
  owner_id: string;
  is_temporary: boolean;
  document_count: number;
}

export interface RAGDocumentRecord {
  document_id: string;
  kb_id: string;
  title: string;
  source_type: string;
  visibility: string;
  tenant_id: string;
  user_id?: string | null;
  app_id: string;
  agent_id?: string | null;
  session_id?: string | null;
  owner_id: string;
  is_temporary: boolean;
  file_name: string;
  mime_type: string;
  source_uri: string;
  metadata: Record<string, unknown>;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface RAGCitation {
  doc_id: string;
  title: string;
  chunk_id: string;
  page_or_section: string;
  score: number;
  preview: string;
  visibility: string;
  source_uri: string;
  source_type: string;
}

export interface RAGSearchItem {
  chunk_id: string;
  document_id: string;
  title: string;
  page_or_section: string;
  score: number;
  lexical_score: number;
  vector_score: number;
  rerank_score: number;
  preview: string;
  visibility: string;
  source_type: string;
  kb_id: string;
  source_uri: string;
}

export interface RAGSearchResponse {
  query: string;
  mode: string;
  sources: RAGCitation[];
  items: RAGSearchItem[];
  debug: Record<string, unknown>;
}

export interface RAGAnswerResponse {
  answer: string;
  sources: RAGCitation[];
  fallback_used: boolean;
  debug: Record<string, unknown>;
}

export interface RAGEvalCase {
  case_id: string;
  description: string;
  mode: string;
  recall_at_k: number;
  precision_at_k: number;
  mrr: number;
  leakage_rate: number;
  source_coverage: number;
  expected: string[];
  retrieved: string[];
  debug: Record<string, unknown>;
}

export interface RAGEvalSummary {
  average_recall_at_k: number;
  average_precision_at_k: number;
  average_mrr: number;
  average_leakage_rate: number;
  average_source_coverage: number;
  cases: RAGEvalCase[];
}

export interface MCPServerSummary {
  server_name: string;
  enabled: boolean;
  source: string;
  transport: string;
  command: string;
  args: string[];
  url: string;
  description: string;
  allowed_app_ids: string[];
  env_keys: string[];
  env_masked: Record<string, string>;
  header_keys: string[];
  headers_masked: Record<string, string>;
  request_timeout_seconds: number;
  startup_timeout_seconds: number;
  editable: boolean;
}

export interface MCPStatusServer {
  server_name: string;
  enabled: boolean;
  source: string;
  allowed_app_ids: string[];
  transport: string;
  command: string;
  args: string[];
  url: string;
  description: string;
  headers: Record<string, string>;
  connected: boolean;
  protocol_version: string;
  server_info: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  last_error: string;
  last_started_at: number;
  session_id: string;
  stderr_tail: string[];
  tools_count: number;
  resources_count: number;
  prompts_count: number;
}

export interface MCPStatusResponse {
  enabled: boolean;
  servers: MCPStatusServer[];
}

export interface MCPCatalogEntry {
  tools: Array<Record<string, unknown>>;
  resources: Array<Record<string, unknown>>;
  prompts: Array<Record<string, unknown>>;
}

export interface MCPCatalogResponse {
  app_id: string;
  enabled: boolean;
  allowed_servers: string[];
  catalog: Record<string, MCPCatalogEntry>;
  exposed_tool_names: Record<string, string[]>;
}

export interface MCPPrecheckResult {
  server_name: string;
  transport: string;
  ready: boolean;
  warnings: string[];
  checks: Record<string, unknown>;
}

export interface SkillCatalogItem {
  skill_id: string;
  name: string;
  description: string;
  tags: string[];
  tool_names: string[];
  stage_configs: string[];
  source_dir: string;
  hydrated: boolean;
  resource_counts: {
    references: number;
    scripts: number;
    assets: number;
  };
}

export interface SkillResource {
  title: string;
  resource_type: string;
  relative_path: string;
  absolute_path: string;
  content: string;
  metadata: Record<string, string>;
}

export interface SkillResolvedItem {
  skill_id: string;
  name: string;
  stage: string;
  prompt_fragments: string[];
  tool_names: string[];
  references: SkillResource[];
  scripts: SkillResource[];
  assets: SkillResource[];
  instructions_markdown: string;
  metadata: Record<string, string>;
}

export interface SkillBindingsResponse {
  app_id: string;
  app_name: string;
  runtime_factory: string;
  context_profiles: string[];
  bindings: Array<{
    skill_id: string;
    stage: string;
    enabled: boolean;
    priority: number;
    metadata: Record<string, string>;
  }>;
}

export interface SkillEvalCase {
  case_id: string;
  expected_skill_ids: string[];
  resolved_skill_ids: string[];
  precision: number;
  recall: number;
  reference_loading_coverage: number;
  resource_inventory_coverage: number;
}

export interface SkillEvalSummary {
  catalog_skill_count: number;
  average_precision: number;
  average_recall: number;
  average_reference_loading_coverage: number;
  average_resource_inventory_coverage: number;
  cases: SkillEvalCase[];
}

export interface ContextExplainPacket {
  source: string;
  token_count: number;
  relevance_score: number;
  metadata: Record<string, unknown>;
  content_preview: string;
}

export interface ContextExplainResult {
  app_id: string;
  stage: string;
  profile: string;
  request_metadata: Record<string, unknown>;
  system_prompt_preview: string;
  sections: Array<{ title: string; content: string }>;
  packets: ContextExplainPacket[];
  prompt_preview: string;
  diagnostics: Record<string, unknown>;
  skills: SkillResolvedItem[];
}

export interface ContextEvalCase {
  case_id: string;
  app_id: string;
  stage: string;
  light_mode: boolean;
  selected_tokens: number;
  compressed_tokens: number;
  max_tokens: number;
  utilization: number;
  dedupe_rate: number;
  compression_gain: number;
  source_diversity: number;
  sections: string[];
  sources: Record<string, unknown>;
}

export interface ContextEvalSummary {
  average_utilization: number;
  average_dedupe_rate: number;
  average_compression_gain: number;
  average_source_diversity: number;
  cases: ContextEvalCase[];
}

export interface StreamOptions {
  signal?: AbortSignal;
}

export async function checkHealth(): Promise<{ status: string }> {
  return requestJson<{ status: string }>("/healthz");
}

export function listApps(): Promise<AppManifest[]> {
  return requestJson<AppManifest[]>("/api/apps");
}

export function listSessions(appId?: string, limit = 30): Promise<SessionSummary[]> {
  const params = new URLSearchParams();
  if (appId) params.set("app_id", appId);
  params.set("limit", String(limit));
  return requestJson<{ sessions: SessionSummary[] }>(`/api/sessions?${params.toString()}`).then((result) => result.sessions);
}

export function getSessionHistory(
  sessionId: string,
  appId?: string
): Promise<{ session_id: string; app_id?: string; messages: SessionMessage[] }> {
  const params = new URLSearchParams();
  if (appId) params.set("app_id", appId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/api/sessions/${encodeURIComponent(sessionId)}${suffix}`);
}

export function listResearchRuns(limit = 30): Promise<ResearchRunSummary[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return requestJson<{ runs: ResearchRunSummary[] }>(`/api/research/history?${params.toString()}`).then((result) => result.runs);
}

export function getResearchRun(sessionId: string): Promise<ResearchRunRecord> {
  return requestJson<ResearchRunRecord>(`/api/research/history/${encodeURIComponent(sessionId)}`);
}

export function getMemoryStatus(): Promise<MemoryStatus> {
  return requestJson<MemoryStatus>("/api/memory/status");
}

export function getMemorySummary(appId?: string, userId?: string): Promise<MemorySummary> {
  const params = new URLSearchParams();
  if (appId) params.set("app_id", appId);
  if (userId) params.set("user_id", userId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<{ summary: MemorySummary }>(`/api/memory/summary${suffix}`).then((result) => result.summary);
}

export function listMemoryRecords(options: {
  appId?: string;
  sessionId?: string;
  userId?: string;
  memoryType?: string;
  includeArchived?: boolean;
  limit?: number;
} = {}): Promise<MemoryRecord[]> {
  const params = new URLSearchParams();
  if (options.appId) params.set("app_id", options.appId);
  if (options.sessionId) params.set("session_id", options.sessionId);
  if (options.userId) params.set("user_id", options.userId);
  if (options.memoryType) params.set("memory_type", options.memoryType);
  if (options.includeArchived) params.set("include_archived", "true");
  params.set("limit", String(options.limit ?? 50));
  return requestJson<{ records: MemoryRecord[] }>(`/api/memory/records?${params.toString()}`).then((result) => result.records);
}

export function searchMemories(payload: {
  query: string;
  app_id: string;
  session_id?: string;
  user_id?: string;
  limit?: number;
  include_graph?: boolean;
  retrieval_mode?: string;
}): Promise<MemoryRecord[]> {
  return requestJson<{ results: MemoryRecord[] }>("/api/memory/search", {
    method: "POST",
    body: JSON.stringify(payload)
  }).then((result) => result.results);
}

export function runMemoryEval(appId = "chat"): Promise<MemoryEvalSummary> {
  return requestJson<MemoryEvalSummary>(`/api/memory/eval?app_id=${encodeURIComponent(appId)}`, {
    method: "POST"
  });
}

export function getRagStatus(): Promise<RAGStatus> {
  return requestJson<RAGStatus>("/api/rag/status");
}

export function listRagScopes(options: {
  appId?: string;
  userId?: string;
  sessionId?: string;
} = {}): Promise<RAGScopeSummary[]> {
  const params = new URLSearchParams();
  if (options.appId) params.set("app_id", options.appId);
  if (options.userId) params.set("user_id", options.userId);
  if (options.sessionId) params.set("session_id", options.sessionId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<{ scopes: RAGScopeSummary[] }>(`/api/rag/scopes${suffix}`).then((result) => result.scopes);
}

export function listRagDocuments(options: {
  appId: string;
  userId?: string;
  sessionId?: string;
  visibility?: string[];
  sourceTypes?: string[];
  kbIds?: string[];
  limit?: number;
}): Promise<RAGDocumentRecord[]> {
  const params = new URLSearchParams();
  params.set("app_id", options.appId);
  if (options.userId) params.set("user_id", options.userId);
  if (options.sessionId) params.set("session_id", options.sessionId);
  for (const item of options.visibility || []) params.append("visibility", item);
  for (const item of options.sourceTypes || []) params.append("source_types", item);
  for (const item of options.kbIds || []) params.append("kb_ids", item);
  params.set("limit", String(options.limit ?? 100));
  return requestJson<{ documents: RAGDocumentRecord[] }>(`/api/rag/documents?${params.toString()}`).then((result) => result.documents);
}

export function addRagText(payload: {
  app_id: string;
  title: string;
  text: string;
  user_id?: string;
  session_id?: string;
  agent_id?: string;
  tenant_id?: string;
  knowledge_target: string;
  source_type?: string;
  kb_id?: string;
  owner_id?: string;
  metadata?: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>("/api/rag/text", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function importRagUrl(payload: {
  app_id: string;
  url: string;
  title?: string;
  user_id?: string;
  session_id?: string;
  agent_id?: string;
  tenant_id?: string;
  knowledge_target: string;
  source_type?: string;
  kb_id?: string;
  owner_id?: string;
  metadata?: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>("/api/rag/url", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function uploadRagDocument(payload: {
  app_id: string;
  title: string;
  knowledge_target: string;
  file: File;
  user_id?: string;
  session_id?: string;
  agent_id?: string;
  tenant_id?: string;
  kb_id?: string;
  owner_id?: string;
  source_type?: string;
}): Promise<Record<string, unknown>> {
  const form = new FormData();
  form.set("app_id", payload.app_id);
  form.set("title", payload.title);
  form.set("knowledge_target", payload.knowledge_target);
  form.set("source_type", payload.source_type || "user_upload");
  form.set("tenant_id", payload.tenant_id || "default");
  if (payload.user_id) form.set("user_id", payload.user_id);
  if (payload.session_id) form.set("session_id", payload.session_id);
  if (payload.agent_id) form.set("agent_id", payload.agent_id);
  if (payload.kb_id) form.set("kb_id", payload.kb_id);
  if (payload.owner_id) form.set("owner_id", payload.owner_id);
  form.set("file", payload.file);
  return requestForm<Record<string, unknown>>("/api/rag/document", form);
}

export function searchRag(payload: {
  app_id: string;
  query: string;
  user_id?: string;
  session_id?: string;
  agent_id?: string;
  tenant_id?: string;
  limit?: number;
  retrieval_mode?: string;
  scope_names?: string[];
  kb_ids?: string[];
  source_types?: string[];
  include_public?: boolean;
  include_app_shared?: boolean;
  include_user_private?: boolean;
  include_session_temporary?: boolean;
  query_rewrite_enabled?: boolean;
  query_rewrite_mode?: string;
  mqe_variants?: number;
  hyde_enabled?: boolean;
  hyde_mode?: string;
  rerank_enabled?: boolean;
  rerank_strategy?: string;
  rerank_top_n?: number;
}): Promise<RAGSearchResponse> {
  return requestJson<RAGSearchResponse>("/api/rag/search", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function answerWithRag(payload: {
  app_id: string;
  query: string;
  user_id?: string;
  session_id?: string;
  agent_id?: string;
  tenant_id?: string;
  limit?: number;
  retrieval_mode?: string;
  scope_names?: string[];
  kb_ids?: string[];
  source_types?: string[];
  include_public?: boolean;
  include_app_shared?: boolean;
  include_user_private?: boolean;
  include_session_temporary?: boolean;
  query_rewrite_enabled?: boolean;
  query_rewrite_mode?: string;
  mqe_variants?: number;
  hyde_enabled?: boolean;
  hyde_mode?: string;
  rerank_enabled?: boolean;
  rerank_strategy?: string;
  rerank_top_n?: number;
  system_prompt?: string;
}): Promise<RAGAnswerResponse> {
  return requestJson<RAGAnswerResponse>("/api/rag/answer", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function deleteRagDocument(payload: {
  documentId: string;
  app_id: string;
  user_id?: string;
  session_id?: string;
}): Promise<{ deleted: boolean; document_id: string }> {
  return requestJson<{ deleted: boolean; document_id: string }>(`/api/rag/documents/${encodeURIComponent(payload.documentId)}`, {
    method: "DELETE",
    body: JSON.stringify({
      app_id: payload.app_id,
      user_id: payload.user_id,
      session_id: payload.session_id
    })
  });
}

export function rebuildRagIndex(payload: { app_id?: string; kb_id?: string } = {}): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>("/api/rag/rebuild", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function runRagEval(appId = "chat"): Promise<RAGEvalSummary> {
  return requestJson<RAGEvalSummary>(`/api/rag/eval?app_id=${encodeURIComponent(appId)}`, {
    method: "POST"
  });
}

export function getMcpStatus(): Promise<MCPStatusResponse> {
  return requestJson<MCPStatusResponse>("/api/mcp/status");
}

export function listSkillCatalog(): Promise<SkillCatalogItem[]> {
  return requestJson<{ skills: SkillCatalogItem[] }>("/api/skills/catalog").then((result) => result.skills);
}

export function resolveSkills(appId: string, stage: string, userId?: string): Promise<SkillResolvedItem[]> {
  const params = new URLSearchParams({ app_id: appId, stage });
  if (userId) params.set("user_id", userId);
  return requestJson<{ skills: SkillResolvedItem[] }>(`/api/skills/resolve?${params.toString()}`).then((result) => result.skills);
}

export function getSkillBindings(appId: string): Promise<SkillBindingsResponse> {
  return requestJson<SkillBindingsResponse>(`/api/skills/bindings?app_id=${encodeURIComponent(appId)}`);
}

export function reloadSkills(): Promise<{ skills_root: string; skill_count: number }> {
  return requestJson<{ skills_root: string; skill_count: number }>("/api/skills/reload", {
    method: "POST"
  });
}

export function runSkillEval(): Promise<SkillEvalSummary> {
  return requestJson<SkillEvalSummary>("/api/skills/eval");
}

export function explainContext(payload: {
  app_id: string;
  stage: string;
  session_id?: string;
  user_id?: string;
  user_input: string;
}): Promise<ContextExplainResult> {
  return requestJson<ContextExplainResult>("/api/context/explain", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function runContextEval(): Promise<ContextEvalSummary> {
  return requestJson<ContextEvalSummary>("/api/context/eval");
}

export function listMcpServers(): Promise<MCPServerSummary[]> {
  return requestJson<{ enabled: boolean; servers: MCPServerSummary[] }>("/api/mcp/servers").then((result) => result.servers);
}

export function importMcpServers(payload: {
  config_text: string;
  allowed_app_ids: string[];
  enabled?: boolean;
}): Promise<{ imported: MCPServerSummary[] }> {
  return requestJson<{ imported: MCPServerSummary[] }>("/api/mcp/import", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function precheckMcpServers(payload: {
  config_text: string;
}): Promise<{ results: MCPPrecheckResult[] }> {
  return requestJson<{ results: MCPPrecheckResult[] }>("/api/mcp/precheck", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateMcpServer(
  serverName: string,
  payload: {
    enabled?: boolean;
    allowed_app_ids?: string[];
  }
): Promise<MCPServerSummary> {
  return requestJson<MCPServerSummary>(`/api/mcp/servers/${encodeURIComponent(serverName)}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function deleteMcpServer(serverName: string): Promise<{ deleted: boolean; server_name: string }> {
  return requestJson<{ deleted: boolean; server_name: string }>(`/api/mcp/servers/${encodeURIComponent(serverName)}`, {
    method: "DELETE"
  });
}

export function getMcpCatalog(appId: string, refresh = false): Promise<MCPCatalogResponse> {
  const params = new URLSearchParams({ app_id: appId, refresh: String(refresh) });
  return requestJson<MCPCatalogResponse>(`/api/mcp/catalog?${params.toString()}`);
}

export function callMcpTool(payload: {
  app_id: string;
  server_name: string;
  tool_name: string;
  arguments?: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>("/api/mcp/call", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function readMcpResource(payload: {
  app_id: string;
  server_name: string;
  uri: string;
}): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>("/api/mcp/resource/read", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getMcpPrompt(payload: {
  app_id: string;
  server_name: string;
  prompt_name: string;
  arguments?: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>("/api/mcp/prompt/get", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function streamChat(
  payload: { session_id: string; message: string; user_id: string },
  onEvent: (event: RunEvent) => void,
  options: StreamOptions = {}
): Promise<void> {
  await streamRequest("/api/chat/stream", payload, onEvent, options);
}

export async function streamResearch(
  payload: { session_id: string; topic: string; user_id?: string },
  onEvent: (event: RunEvent) => void,
  options: StreamOptions = {}
): Promise<void> {
  await streamRequest("/api/research/stream", payload, onEvent, options);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, withJsonHeaders(init));

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

async function requestForm<T>(path: string, body: FormData, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    method: init?.method || "POST",
    body
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

async function streamRequest(
  path: string,
  payload: Record<string, unknown>,
  onEvent: (event: RunEvent) => void,
  options: StreamOptions
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream"
    },
    body: JSON.stringify(payload),
    signal: options.signal
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Stream request failed with status ${response.status}`);
  }

  const body = response.body;
  if (!body) {
    throw new Error("Streaming response is not available in this browser.");
  }

  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      if (block.startsWith("data:")) {
        const payloadText = block.slice(5).trim();
        if (payloadText) {
          onEvent(JSON.parse(payloadText) as RunEvent);
        }
      }
      boundary = buffer.indexOf("\n\n");
    }

    if (done) {
      break;
    }
  }
}

function withJsonHeaders(init?: RequestInit): RequestInit {
  return {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  };
}
