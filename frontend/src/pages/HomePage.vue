<template>
  <section class="page-stack home-page">
    <header class="surface-card dashboard-hero">
      <div class="hero-copy">
        <p class="eyebrow">AgentHub Dashboard</p>
        <h1>一个统一底座，承载多个智能体应用</h1>
        <p class="muted">
          首屏优先展示应用入口、最近活动和关键状态。你可以直接进入聊天、研究、RAG、记忆、MCP 或 Skills 工作台。
        </p>
      </div>
      <div class="hero-actions">
        <RouterLink class="btn primary" to="/chat">打开聊天助手</RouterLink>
        <RouterLink class="btn ghost" to="/research">打开深度研究</RouterLink>
        <RouterLink class="btn ghost" to="/software-engineering">打开软件工程智能体</RouterLink>
        <RouterLink class="btn ghost" to="/skills">打开 Skills 工作台</RouterLink>
      </div>
    </header>

    <section class="surface-card status-strip">
      <div class="status-pill-card">
        <span>后端</span>
        <strong>{{ backendLabel }}</strong>
        <small class="muted mono">{{ API_BASE_URL }}</small>
      </div>
      <div class="status-pill-card">
        <span>RAG</span>
        <strong>{{ ragStatus?.vector_backend.enabled ? "Qdrant 在线" : "未启用" }}</strong>
        <small class="muted mono">{{ ragStatus?.vector_backend.collection || "n/a" }}</small>
      </div>
      <div class="status-pill-card">
        <span>记忆图谱</span>
        <strong>{{ memoryStatus?.graph_backend.enabled ? "Neo4j 在线" : "本地图模式" }}</strong>
        <small class="muted mono">{{ memoryStatus?.graph_backend.active_uri || "local graph" }}</small>
      </div>
      <div class="status-pill-card">
        <span>应用数</span>
        <strong>{{ apps.length }}</strong>
        <small class="muted">已注册工作区</small>
      </div>
    </section>

    <section v-if="backendState !== 'ready'" class="surface-card inline-banner">
      <strong>{{ backendState === "loading" ? "正在检查后端..." : "后端暂时不可用" }}</strong>
      <p class="muted">
        {{
          backendState === "loading"
            ? `正在检查 ${API_BASE_URL}`
            : `当前无法连接 ${API_BASE_URL}，请先启动后端。`
        }}
      </p>
      <p v-if="errorMessage" class="inline-error">{{ errorMessage }}</p>
      <pre class="command-block">cd backend
python -m app.main</pre>
    </section>

    <div class="dashboard-grid">
      <article class="surface-card panel">
        <div class="tool-strip">
          <div>
            <p class="eyebrow">应用入口</p>
            <h2>工作区</h2>
          </div>
          <button class="btn ghost small" type="button" @click="loadDashboard">刷新</button>
        </div>
        <div class="app-list content-scroll">
          <RouterLink
            v-for="app in apps"
            :key="app.app_id"
            :to="appRoute(app.app_id)"
            class="app-row"
          >
            <div class="app-copy">
              <strong>{{ localAppName(app.app_id, app.name) }}</strong>
              <p class="muted">{{ localAppDescription(app.app_id, app.description) }}</p>
            </div>
            <span class="chip">{{ routeLabel(app.app_id) }}</span>
          </RouterLink>
          <RouterLink to="/rag" class="app-row">
            <div class="app-copy">
              <strong>RAG 工作台</strong>
              <p class="muted">导入知识、检索测试、引用验证与评测。</p>
            </div>
            <span class="chip">知识</span>
          </RouterLink>
          <RouterLink to="/memory" class="app-row">
            <div class="app-copy">
              <strong>记忆中心</strong>
              <p class="muted">检查召回、图关系、冲突处理与质量指标。</p>
            </div>
            <span class="chip">记忆</span>
          </RouterLink>
          <RouterLink to="/mcp" class="app-row">
            <div class="app-copy">
              <strong>MCP 工作台</strong>
              <p class="muted">导入服务配置、查看目录、测试 tools/resources/prompts。</p>
            </div>
            <span class="chip">MCP</span>
          </RouterLink>
          <RouterLink to="/skills" class="app-row">
            <div class="app-copy">
              <strong>Skills 工作台</strong>
              <p class="muted">检查技能目录、App 绑定和当前阶段的生效结果。</p>
            </div>
            <span class="chip">Skills</span>
          </RouterLink>
        </div>
      </article>

      <article class="surface-card panel">
        <div class="tool-strip">
          <div>
            <p class="eyebrow">最近会话</p>
            <h2>聊天助手</h2>
          </div>
          <RouterLink class="btn ghost small" to="/chat">进入</RouterLink>
        </div>
        <div class="compact-list content-scroll">
          <RouterLink
            v-for="session in chatSessions"
            :key="session.session_id"
            :to="`/chat/${session.session_id}`"
            class="recent-row"
          >
            <div class="recent-copy">
              <strong>{{ session.title || session.session_id }}</strong>
              <p class="muted">{{ session.preview || "暂无摘要" }}</p>
            </div>
            <span>{{ formatTimestamp(session.updated_at) }}</span>
          </RouterLink>
          <p v-if="!chatSessions.length" class="muted">暂无最近会话。</p>
        </div>
      </article>

      <article class="surface-card panel">
        <div class="tool-strip">
          <div>
            <p class="eyebrow">最近研究</p>
            <h2>深度研究</h2>
          </div>
          <RouterLink class="btn ghost small" to="/research">进入</RouterLink>
        </div>
        <div class="compact-list content-scroll">
          <RouterLink
            v-for="run in researchRuns"
            :key="run.session_id"
            :to="`/research/${run.session_id}`"
            class="recent-row"
          >
            <div class="recent-copy">
              <strong>{{ run.topic || run.session_id }}</strong>
              <p class="muted">{{ run.report_preview || "暂无报告摘要" }}</p>
            </div>
            <span>{{ formatTimestamp(run.updated_at) }}</span>
          </RouterLink>
          <p v-if="!researchRuns.length" class="muted">暂无最近研究。</p>
        </div>
      </article>

      <article class="surface-card panel">
        <div class="tool-strip">
          <div>
            <p class="eyebrow">最近工程任务</p>
            <h2>Software Engineering</h2>
          </div>
          <RouterLink class="btn ghost small" to="/software-engineering">进入</RouterLink>
        </div>
        <div class="compact-list content-scroll">
          <RouterLink
            v-for="run in seRuns"
            :key="run.session_id"
            :to="`/software-engineering/${run.session_id}`"
            class="recent-row"
          >
            <div class="recent-copy">
              <strong>{{ run.goal || run.session_id }}</strong>
              <p class="muted">{{ run.final_preview || run.status }}</p>
            </div>
            <span>{{ formatTimestamp(run.updated_at) }}</span>
          </RouterLink>
          <p v-if="!seRuns.length" class="muted">暂无最近工程任务。</p>
        </div>
      </article>

      <article class="surface-card panel">
        <div class="tool-strip">
          <div>
            <p class="eyebrow">系统摘要</p>
            <h2>关键状态</h2>
          </div>
        </div>
        <div class="summary-grid content-scroll">
          <div class="summary-item">
            <span>RAG 文档数</span>
            <strong>{{ ragStatus?.documents.document_count ?? 0 }}</strong>
          </div>
          <div class="summary-item">
            <span>RAG Chunk 数</span>
            <strong>{{ ragStatus?.documents.chunk_count ?? 0 }}</strong>
          </div>
          <div class="summary-item">
            <span>Embedding 模式</span>
            <strong>{{ memoryStatus?.embedding_mode || "unknown" }}</strong>
          </div>
          <div class="summary-item">
            <span>记忆图谱</span>
            <strong>{{ memoryGraphLabel }}</strong>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import {
  API_BASE_URL,
  checkHealth,
  getMemoryStatus,
  getRagStatus,
  listApps,
  listSERuns,
  listResearchRuns,
  listSessions,
  type AppManifest,
  type MemoryStatus,
  type RAGStatus,
  type SERunSummary,
  type ResearchRunSummary,
  type SessionSummary
} from "../services/api";

const apps = ref<AppManifest[]>([]);
const chatSessions = ref<SessionSummary[]>([]);
const researchRuns = ref<ResearchRunSummary[]>([]);
const seRuns = ref<SERunSummary[]>([]);
const memoryStatus = ref<MemoryStatus | null>(null);
const ragStatus = ref<RAGStatus | null>(null);
const backendState = ref<"loading" | "ready" | "error">("loading");
const errorMessage = ref("");

const backendLabel = computed(() => {
  if (backendState.value === "loading") return "检查中";
  if (backendState.value === "ready") return "在线";
  return "离线";
});

const memoryGraphLabel = computed(() => (memoryStatus.value?.graph_backend.enabled ? "外部图后端" : "本地图模式"));

onMounted(async () => {
  await loadDashboard();
});

async function loadDashboard(): Promise<void> {
  backendState.value = "loading";
  try {
    await checkHealth();
    const [appsResult, sessionsResult, runsResult, seRunsResult, memoryResult, ragResult] = await Promise.all([
      listApps(),
      listSessions("chat", 8),
      listResearchRuns(8),
      listSERuns(8),
      getMemoryStatus(),
      getRagStatus()
    ]);
    apps.value = appsResult;
    chatSessions.value = sessionsResult;
    researchRuns.value = runsResult;
    seRuns.value = seRunsResult;
    memoryStatus.value = memoryResult;
    ragStatus.value = ragResult;
    backendState.value = "ready";
    errorMessage.value = "";
  } catch (error) {
    backendState.value = "error";
    errorMessage.value = getErrorMessage(error);
  }
}

function appRoute(appId: string): string {
  if (appId === "chat") return "/chat";
  if (appId === "deep_research") return "/research";
  if (appId === "software_engineering") return "/software-engineering";
  return "/";
}

function routeLabel(appId: string): string {
  if (appId === "chat") return "对话";
  if (appId === "deep_research") return "研究";
  if (appId === "software_engineering") return "工程";
  return "打开";
}

function localAppName(appId: string, fallback: string): string {
  if (appId === "chat") return "聊天助手";
  if (appId === "deep_research") return "深度研究助手";
  if (appId === "software_engineering") return "软件工程智能体";
  return fallback;
}

function localAppDescription(appId: string, fallback: string): string {
  if (appId === "chat") return "面向高频操作的主对话工作区。";
  if (appId === "deep_research") return "规划任务、跟踪执行并输出最终报告。";
  if (appId === "software_engineering") return "需求到代码、反馈到修复的动态工程闭环。";
  return fallback;
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
</script>

<style scoped>
.home-page {
  grid-template-rows: auto auto minmax(0, 1fr);
}

.dashboard-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: end;
  padding: 18px 20px;
}

.dashboard-hero h1,
.panel h2 {
  margin: 8px 0 0;
  font-size: 1.4rem;
}

.hero-copy {
  max-width: 68ch;
}

.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.status-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  padding: 12px;
}

.status-pill-card {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(76, 134, 255, 0.12);
  background: rgba(255, 255, 255, 0.62);
}

.status-pill-card span,
.summary-item span {
  display: block;
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.panel {
  display: grid;
  gap: 12px;
  padding: 16px;
  min-height: 0;
}

.app-list,
.compact-list,
.summary-grid {
  display: grid;
  gap: 8px;
  min-height: 0;
}

.app-list,
.compact-list {
  overflow: auto;
}

.app-row,
.recent-row,
.summary-item {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.72);
  text-decoration: none;
  color: inherit;
  transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
}

.app-row:hover,
.recent-row:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-soft);
  border-color: rgba(76, 134, 255, 0.28);
}

.app-row {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.app-copy,
.recent-copy {
  min-width: 0;
}

.app-copy strong,
.app-copy p,
.recent-copy strong,
.recent-copy p {
  display: block;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.app-copy p,
.recent-copy p {
  margin: 0;
}

.recent-row {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.recent-row span {
  color: var(--muted);
  font-size: 0.8rem;
}

.summary-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.summary-item strong {
  font-size: 1.02rem;
}

@media (max-width: 1180px) {
  .status-strip,
  .dashboard-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 860px) {
  .dashboard-hero,
  .status-strip,
  .dashboard-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .hero-actions {
    justify-content: flex-start;
  }
}
</style>
