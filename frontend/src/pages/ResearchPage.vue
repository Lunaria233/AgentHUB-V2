<template>
  <section class="workbench-shell research-shell" :style="researchShellStyle">
    <aside class="surface-card workbench-rail research-rail" :class="{ collapsed: leftCollapsed }">
      <div class="tool-strip">
        <button class="icon-btn" type="button" @click="leftCollapsed = !leftCollapsed">
          {{ leftCollapsed ? "›" : "‹" }}
        </button>
        <button v-if="!leftCollapsed" class="btn primary small" type="button" @click="createFreshRun">新建</button>
      </div>

      <template v-if="!leftCollapsed">
        <div class="rail-headline">
          <div>
            <p class="eyebrow">研究历史</p>
            <h2>归档记录</h2>
          </div>
          <button class="btn ghost small" type="button" @click="refreshRuns">刷新</button>
        </div>

        <p v-if="pageError" class="inline-error">{{ pageError }}</p>

        <div class="rail-scroll compact-stack">
          <button
            v-for="run in runs"
            :key="run.session_id"
            type="button"
            class="run-row"
            :class="{ active: run.session_id === currentSessionId }"
            @click="openRun(run.session_id)"
          >
            <strong>{{ run.topic || run.session_id }}</strong>
            <p>{{ run.report_preview || "暂无报告摘要" }}</p>
            <span>{{ formatTimestamp(run.updated_at) }}</span>
          </button>
        </div>
      </template>
    </aside>

    <section class="surface-card workbench-main research-main">
      <header class="research-toolbar">
        <div class="toolbar-left">
          <button class="icon-btn" type="button" @click="leftCollapsed = !leftCollapsed">
            {{ leftCollapsed ? "≡" : "←" }}
          </button>
          <div>
            <p class="eyebrow">深度研究</p>
            <h1>{{ currentRun?.topic || "研究工作区" }}</h1>
          </div>
        </div>
        <div class="summary-bar">
          <span class="chip" :class="backendState">{{ backendLabel }}</span>
          <span class="chip" :class="running ? 'running' : (currentRun?.status || 'idle')">
            {{ running ? "运行中" : statusLabel(currentRun?.status || "draft") }}
          </span>
          <button class="btn ghost small" type="button" @click="rightCollapsed = !rightCollapsed">
            {{ rightCollapsed ? "显示侧栏" : "隐藏侧栏" }}
          </button>
        </div>
      </header>

      <section v-if="backendState !== 'ready'" class="inline-banner">
        <strong>后端暂时不可用</strong>
        <p class="muted">请先启动后端。当前地址：{{ API_BASE_URL }}</p>
        <pre class="command-block">cd backend
python -m app.main</pre>
      </section>

      <form class="research-control" @submit.prevent="submitResearch">
        <label class="field compact-topic">
          <span>研究主题</span>
          <textarea
            v-model="topicInput"
            rows="2"
            placeholder="例如：2026 年多智能体平台的发展趋势"
            :disabled="running"
          ></textarea>
        </label>

        <label class="field compact-user">
          <span>User ID</span>
          <input v-model="userId" type="text" placeholder="可选，用于隔离记忆和知识" />
        </label>

        <div class="summary-bar">
          <span class="chip mono">{{ currentSessionId }}</span>
          <button class="btn primary" type="submit" :disabled="running || !topicInput.trim() || backendState !== 'ready'">
            {{ running ? "研究中..." : "开始研究" }}
          </button>
          <button class="btn ghost" type="button" :disabled="!running" @click="cancelResearch">停止</button>
        </div>
      </form>

      <section class="surface-tabs research-tabs">
        <button class="tab-btn" :class="{ active: activeTab === 'report' }" type="button" @click="activeTab = 'report'">
          最终报告
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'tasks' }" type="button" @click="activeTab = 'tasks'">
          任务树
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'logs' }" type="button" @click="activeTab = 'logs'">
          执行日志
        </button>
      </section>

      <section class="surface-card workbench-panel content-panel">
        <div v-if="activeTab === 'report'" class="content-scroll tab-scroll">
          <div class="section-head">
            <div>
              <p class="eyebrow">最终报告</p>
              <h2>{{ currentRun?.topic || "等待输入研究主题" }}</h2>
            </div>
            <span class="chip">{{ currentRun?.tasks.length || 0 }} 个任务</span>
          </div>
          <div class="report-rendered">
            <MarkdownContent :source="currentRun?.report || '研究完成后，最终报告会稳定显示在这里。'" />
          </div>
        </div>

        <div v-else-if="activeTab === 'tasks'" class="content-scroll tab-scroll">
          <div class="section-head">
            <div>
              <p class="eyebrow">任务树</p>
              <h2>{{ currentRun?.tasks.length || 0 }} 个任务</h2>
            </div>
          </div>

          <div v-if="!currentRun?.tasks.length" class="empty-state">
            <p class="muted">还没有任务计划。可以直接开始一次研究，或从左侧打开历史记录。</p>
          </div>

          <div class="accordion-list">
            <details v-for="task in currentRun?.tasks || []" :key="task.task_id" class="task-accordion">
              <summary>
                <div>
                  <strong>{{ task.title || `任务 ${task.task_id}` }}</strong>
                  <p>{{ task.query }}</p>
                </div>
                <span class="chip">{{ task.sources.length }} 个来源</span>
              </summary>

              <div class="task-body">
                <section class="task-section">
                  <h3>摘要</h3>
                  <div class="content-card">
                    <MarkdownContent :source="task.summary || '等待任务摘要...'" />
                  </div>
                </section>

                <section class="task-section">
                  <h3>来源</h3>
                  <ul class="source-list">
                    <li v-for="(source, index) in task.sources" :key="`${source.url}-${index}`">
                      <a :href="source.url || '#'" target="_blank" rel="noreferrer">
                        {{ source.title || source.url || `来源 ${index + 1}` }}
                      </a>
                      <p>{{ source.snippet }}</p>
                    </li>
                  </ul>
                </section>
              </div>
            </details>
          </div>
        </div>

        <div v-else class="content-scroll tab-scroll">
          <div class="section-head">
            <div>
              <p class="eyebrow">执行日志</p>
              <h2>完整运行轨迹</h2>
            </div>
            <span class="chip">{{ currentRun?.events.length || 0 }} 条事件</span>
          </div>

          <ul class="event-list">
            <li v-for="(event, index) in currentRun?.events || []" :key="`event-${index}`">
              <span class="event-type">{{ event.type }}</span>
              <span>{{ describeEvent(event) }}</span>
            </li>
          </ul>
        </div>
      </section>
    </section>

    <aside v-if="!rightCollapsed" class="surface-card workbench-inspector research-inspector">
      <div class="tool-strip">
        <div>
          <p class="eyebrow">Inspector</p>
          <h2>运行信息</h2>
        </div>
        <button class="icon-btn" type="button" @click="rightCollapsed = true">×</button>
      </div>

      <div class="pane-scroll inspector-stack">
        <section class="info-stack">
          <div class="info-card">
            <span>当前会话</span>
            <strong>{{ currentSessionId }}</strong>
          </div>
          <div class="info-card">
            <span>User ID</span>
            <strong>{{ userId || "未填写" }}</strong>
          </div>
          <div class="info-card">
            <span>运行状态</span>
            <strong>{{ running ? "运行中" : statusLabel(currentRun?.status || "draft") }}</strong>
          </div>
        </section>

        <details class="drawer-card">
          <summary>知识资料</summary>
          <KnowledgeQuickPanel
            :app-id="'deep_research'"
            :session-id="currentSessionId"
            :user-id="userId"
            title="为当前研究补充资料、约束或网页"
            @ingested="refreshRuns"
          />
        </details>
      </div>
    </aside>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import KnowledgeQuickPanel from "../components/KnowledgeQuickPanel.vue";
import MarkdownContent from "../components/MarkdownContent.vue";
import {
  API_BASE_URL,
  checkHealth,
  getResearchRun,
  listResearchRuns,
  streamResearch,
  type ResearchCitation,
  type ResearchRunRecord,
  type ResearchRunSummary,
  type ResearchTaskRecord,
  type RunEvent
} from "../services/api";

const route = useRoute();
const router = useRouter();

const runs = ref<ResearchRunSummary[]>([]);
const currentRun = ref<ResearchRunRecord | null>(null);
const currentSessionId = ref("");
const userId = ref("");
const topicInput = ref("");
const activeTab = ref<"report" | "tasks" | "logs">("report");
const pageError = ref("");
const streamError = ref("");
const running = ref(false);
const backendState = ref<"loading" | "ready" | "error">("loading");
const leftCollapsed = ref(false);
const rightCollapsed = ref(false);

let streamAbortController: AbortController | null = null;

const backendLabel = computed(() => {
  if (backendState.value === "loading") return "检查中";
  if (backendState.value === "ready") return "在线";
  return "离线";
});

const researchShellStyle = computed(() => ({
  gridTemplateColumns: `${leftCollapsed.value ? "72px" : "248px"} minmax(0, 1fr) ${rightCollapsed.value ? "0px" : "300px"}`
}));

onMounted(async () => {
  await hydratePage();
});

onBeforeUnmount(() => {
  streamAbortController?.abort();
});

watch(
  () => route.params.sessionId,
  async (value) => {
    const sessionId = typeof value === "string" ? value : "";
    if (sessionId && sessionId !== currentSessionId.value) {
      await openRun(sessionId, false);
    }
  }
);

async function hydratePage(): Promise<void> {
  await refreshRuns();
  const routeSessionId = typeof route.params.sessionId === "string" ? route.params.sessionId : "";
  if (routeSessionId) {
    await openRun(routeSessionId, false);
    return;
  }
  if (runs.value[0]) {
    await openRun(runs.value[0].session_id);
    return;
  }
  await createFreshRun();
}

async function refreshRuns(): Promise<void> {
  backendState.value = "loading";
  try {
    await checkHealth();
    runs.value = await listResearchRuns(40);
    backendState.value = "ready";
    pageError.value = "";
  } catch (error) {
    backendState.value = "error";
    pageError.value = getErrorMessage(error);
  }
}

async function openRun(sessionId: string, updateRoute = true): Promise<void> {
  currentSessionId.value = sessionId;
  if (updateRoute && route.params.sessionId !== sessionId) {
    await router.push({ name: "research", params: { sessionId } });
  }
  try {
    currentRun.value = await getResearchRun(sessionId);
    topicInput.value = currentRun.value.topic;
    streamError.value = "";
  } catch (error) {
    currentRun.value = blankRun(sessionId, topicInput.value.trim());
    streamError.value = getErrorMessage(error);
  }
}

async function createFreshRun(): Promise<void> {
  cancelResearch();
  const sessionId = createSessionId("research");
  currentSessionId.value = sessionId;
  currentRun.value = blankRun(sessionId, "");
  topicInput.value = "";
  streamError.value = "";
  await router.push({ name: "research", params: { sessionId } });
}

async function submitResearch(): Promise<void> {
  if (!topicInput.value.trim() || running.value || backendState.value !== "ready") {
    return;
  }

  streamAbortController?.abort();
  streamAbortController = new AbortController();
  running.value = true;
  streamError.value = "";
  currentRun.value = blankRun(currentSessionId.value, topicInput.value.trim(), userId.value || null, "running");

  try {
    await streamResearch(
      { session_id: currentSessionId.value, topic: topicInput.value.trim(), user_id: userId.value || undefined },
      handleResearchEvent,
      { signal: streamAbortController.signal }
    );
  } catch (error) {
    if (!isAbortError(error)) {
      streamError.value = getErrorMessage(error);
      if (currentRun.value) currentRun.value.status = "failed";
    }
  } finally {
    running.value = false;
    await refreshRuns();
    await openRun(currentSessionId.value, false);
  }
}

function handleResearchEvent(event: RunEvent): void {
  if (!currentRun.value) return;
  currentRun.value.events.push(structuredCloneFallback(event));

  if (event.type === "status" && Array.isArray(event.tasks)) {
    currentRun.value.tasks = event.tasks.map((task) => {
      const record = ensureRecord(task);
      return {
        task_id: numberValue(record.task_id),
        title: stringValue(record.title),
        query: stringValue(record.query),
        goal: "",
        summary: "",
        note_id: "",
        sources: []
      };
    });
  }

  if (event.type === "tool_result") {
    const task = ensureTask(numberValue(event.task_id));
    const result = ensureRecord(event.result);
    const results = Array.isArray(result.results) ? result.results : [];
    task.sources = results
      .filter((item) => item && typeof item === "object")
      .map((item) => {
        const record = item as Record<string, unknown>;
        return {
          title: stringValue(record.title),
          url: stringValue(record.url),
          snippet: stringValue(record.snippet)
        } satisfies ResearchCitation;
      });
  }

  if (event.type === "citation") {
    const task = ensureTask(numberValue(event.task_id));
    const citation = {
      title: stringValue(event.title),
      url: stringValue(event.url),
      snippet: stringValue(event.snippet)
    };
    if (!task.sources.find((item) => item.url === citation.url && item.title === citation.title)) {
      task.sources.push(citation);
    }
  }

  if (event.type === "message_done" && typeof event.task_id === "number") {
    const task = ensureTask(event.task_id);
    task.summary = stringValue(event.content);
    task.note_id = stringValue(event.note_id);
  }

  if (event.type === "message_done" && typeof event.report === "string") {
    currentRun.value.report = event.report;
    currentRun.value.status = "completed";
  }

  if (event.type === "error") {
    currentRun.value.status = "failed";
    streamError.value = stringValue(event.message) || "未知研究错误";
  }
}

function ensureTask(taskId: number): ResearchTaskRecord {
  if (!currentRun.value) {
    throw new Error("Research record is not initialized");
  }
  const existing = currentRun.value.tasks.find((item) => item.task_id === taskId);
  if (existing) return existing;
  const created: ResearchTaskRecord = {
    task_id: taskId,
    title: `任务 ${taskId}`,
    query: "",
    goal: "",
    summary: "",
    note_id: "",
    sources: []
  };
  currentRun.value.tasks.push(created);
  return created;
}

function describeEvent(event: RunEvent): string {
  if (event.type === "status") return stringValue(event.message) || "状态更新";
  if (event.type === "tool_call") return `${stringValue(event.tool_name)} ${safeJson(event.arguments)}`;
  if (event.type === "tool_result") return truncate(safeJson(event.result), 180);
  if (event.type === "message_done" && typeof event.task_id === "number") return `任务 ${event.task_id} 摘要已生成`;
  if (event.type === "message_done" && typeof event.report === "string") return "最终报告已生成";
  if (event.type === "citation") return stringValue(event.title) || stringValue(event.url);
  if (event.type === "done") return "流程执行结束";
  return truncate(safeJson(event), 180);
}

function statusLabel(status: string): string {
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "running") return "运行中";
  return "草稿";
}

function cancelResearch(): void {
  streamAbortController?.abort();
  running.value = false;
}

function blankRun(sessionId: string, topic: string, currentUserId: string | null = null, status = "draft"): ResearchRunRecord {
  const now = new Date().toISOString();
  return {
    session_id: sessionId,
    app_id: "deep_research",
    topic,
    user_id: currentUserId,
    status,
    report: "",
    tasks: [],
    events: [],
    created_at: now,
    updated_at: now
  };
}

function createSessionId(prefix: string): string {
  const suffix =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `${prefix}-${suffix}`;
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

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function truncate(value: string, limit: number): string {
  return value.length <= limit ? value : `${value.slice(0, limit)}...`;
}

function structuredCloneFallback<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function ensureRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function numberValue(value: unknown): number {
  return typeof value === "number" ? value : Number(value || 0);
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
</script>

<style scoped>
.research-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.research-toolbar,
.research-control {
  display: grid;
  gap: 12px;
  padding: 14px 16px;
}

.research-toolbar {
  border-bottom: 1px solid rgba(76, 134, 255, 0.12);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.toolbar-left h1,
.rail-headline h2,
.section-head h2 {
  margin: 6px 0 0;
  font-size: 1rem;
}

.toolbar-left h1 {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.run-row {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.74);
  text-align: left;
}

.run-row.active {
  border-color: rgba(76, 134, 255, 0.34);
  background: rgba(232, 242, 255, 0.92);
}

.run-row strong,
.run-row p,
.run-row span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.run-row p {
  margin: 0;
  color: var(--muted);
}

.run-row span {
  font-size: 0.78rem;
  color: var(--muted);
}

.research-control {
  grid-template-columns: minmax(0, 1fr) 220px auto;
  align-items: end;
  border-bottom: 1px solid rgba(76, 134, 255, 0.08);
}

.field {
  display: grid;
  gap: 8px;
}

.field span {
  display: block;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.field input,
.field textarea {
  width: 100%;
  padding: 11px 13px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.84);
  color: var(--text);
}

.compact-topic textarea {
  min-height: 72px;
  resize: vertical;
}

.research-tabs {
  padding: 0 16px;
}

.content-panel {
  flex: 1;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  padding: 0;
  min-height: 0;
}

.tab-scroll {
  min-height: 0;
  overflow: auto;
  display: grid;
  gap: 14px;
  padding: 16px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.report-rendered,
.content-card {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.72);
}

.report-rendered {
  min-height: 240px;
}

.accordion-list {
  display: grid;
  gap: 12px;
}

.task-accordion {
  border: 1px solid rgba(76, 134, 255, 0.16);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.64);
}

.task-accordion summary {
  list-style: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
}

.task-accordion summary::-webkit-details-marker {
  display: none;
}

.task-accordion summary p {
  margin: 6px 0 0;
  color: var(--muted);
}

.task-body {
  display: grid;
  gap: 14px;
  padding: 0 16px 16px;
}

.task-section h3 {
  margin: 0 0 10px;
}

.source-list,
.event-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}

.source-list li,
.event-list li {
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(76, 134, 255, 0.12);
  background: rgba(255, 255, 255, 0.74);
}

.source-list a {
  color: var(--accent-strong);
  font-weight: 600;
  text-decoration: none;
}

.source-list a:hover {
  text-decoration: underline;
}

.source-list p {
  margin: 8px 0 0;
  color: var(--muted);
}

.event-type {
  display: inline-flex;
  margin-right: 10px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(232, 242, 255, 0.92);
  color: var(--accent-strong);
  font-size: 0.78rem;
}

.research-inspector {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
  padding: 12px;
  gap: 10px;
}

.research-inspector .tool-strip {
  position: sticky;
  top: 0;
  z-index: 3;
  padding-bottom: 6px;
  background: linear-gradient(180deg, rgba(248, 252, 255, 0.98), rgba(248, 252, 255, 0.9));
}

.inspector-stack,
.info-stack {
  display: grid;
  gap: 10px;
}

.inspector-stack {
  flex: 0 0 auto;
  min-height: 0;
  overflow: visible;
}

.info-card {
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.74);
}

.info-card span {
  display: block;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.info-card strong {
  display: block;
  margin-top: 8px;
  word-break: break-all;
}

.drawer-card {
  min-height: 0;
  border: 1px solid rgba(76, 134, 255, 0.16);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
  overflow: hidden;
}

.drawer-card summary {
  cursor: pointer;
  padding: 12px 14px;
  font-weight: 600;
}

.drawer-card :deep(.quick-panel) {
  padding: 0 14px 14px;
}

@media (max-width: 1220px) {
  .research-shell {
    grid-template-columns: 72px minmax(0, 1fr) 0 !important;
  }
}

@media (max-width: 980px) {
  .research-shell {
    grid-template-columns: 1fr !important;
    height: auto;
  }

  .research-rail,
  .research-inspector {
    max-height: 240px;
  }

  .research-main {
    min-height: 70vh;
  }

  .research-control {
    grid-template-columns: 1fr;
  }
}
</style>
