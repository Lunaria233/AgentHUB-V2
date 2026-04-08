<template>
  <section class="workbench-shell memory-shell">
    <aside class="surface-card workbench-rail memory-rail">
      <div class="tool-strip">
        <div>
          <p class="eyebrow">Memory Control Tower</p>
          <h2>过滤与状态</h2>
        </div>
        <button class="btn ghost small" type="button" @click="refreshAll" :disabled="loading">
          {{ loading ? "刷新中..." : "刷新" }}
        </button>
      </div>

      <div class="rail-scroll inspector-stack">
        <section v-if="pageError" class="inline-banner">
          <strong>记忆后端检查失败</strong>
          <p class="muted">{{ pageError }}</p>
        </section>

        <section class="status-grid">
          <div class="info-card">
            <span>向量后端</span>
            <strong>{{ status?.vector_backend.enabled ? "Qdrant 在线" : "未启用" }}</strong>
            <small class="muted mono">{{ status?.vector_backend.collection || "n/a" }}</small>
          </div>
          <div class="info-card">
            <span>图后端</span>
            <strong>{{ status?.graph_backend.enabled ? "Neo4j 在线" : "本地图模式" }}</strong>
            <small class="muted mono">{{ status?.graph_backend.active_uri || "local graph only" }}</small>
          </div>
          <div class="info-card">
            <span>Embedding</span>
            <strong>{{ status?.embedding_mode || "unknown" }}</strong>
            <small class="muted">{{ status?.llm_extraction.configured_model || "n/a" }}</small>
          </div>
        </section>

        <section class="surface-card inner-panel">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">过滤条件</p>
              <h3>查看范围</h3>
            </div>
          </div>

          <div class="field-grid">
            <label class="field">
              <span>应用</span>
              <select v-model="filters.appId">
                <option value="chat">chat</option>
                <option value="deep_research">deep_research</option>
                <option value="software_engineering">software_engineering</option>
              </select>
            </label>
            <label class="field">
              <span>User ID</span>
              <input v-model="filters.userId" type="text" placeholder="可选" />
            </label>
            <label class="field">
              <span>Session ID</span>
              <input v-model="filters.sessionId" type="text" placeholder="可选" />
            </label>
            <label class="field">
              <span>记忆类型</span>
              <select v-model="filters.memoryType">
                <option value="">全部</option>
                <option value="working">working</option>
                <option value="episodic">episodic</option>
                <option value="semantic">semantic</option>
                <option value="perceptual">perceptual</option>
              </select>
            </label>
          </div>
        </section>

        <section class="surface-card inner-panel">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">快照</p>
              <h3>当前统计</h3>
            </div>
          </div>

          <div v-if="summary" class="summary-grid">
            <div class="summary-item">
              <span>总数</span>
              <strong>{{ summary.count }}</strong>
            </div>
            <div class="summary-item">
              <span>已归档</span>
              <strong>{{ summary.archived }}</strong>
            </div>
            <div class="summary-item">
              <span>图节点</span>
              <strong>{{ summary.graph.nodes }}</strong>
            </div>
            <div class="summary-item">
              <span>图边</span>
              <strong>{{ summary.graph.edges }}</strong>
            </div>
          </div>

          <div v-if="summary" class="chip-bucket">
            <span v-for="(count, type) in summary.by_type" :key="type" class="chip">{{ type }} / {{ count }}</span>
          </div>
        </section>
      </div>
    </aside>

    <section class="surface-card workbench-main memory-main">
      <header class="memory-toolbar">
        <div>
          <p class="eyebrow">召回解释</p>
          <h1>检索、结果与质量诊断</h1>
        </div>
        <div class="summary-bar">
          <span class="chip">include graph: {{ includeGraph ? "on" : "off" }}</span>
          <button class="btn ghost small" type="button" @click="includeGraph = !includeGraph">切换图召回</button>
        </div>
      </header>

      <section class="memory-search">
        <label class="field">
          <span>问题</span>
          <textarea v-model="searchQuery" rows="3" placeholder="这个智能体应该记住什么？"></textarea>
        </label>
        <div class="summary-bar">
          <button class="btn ghost" type="button" @click="runSearch" :disabled="searching || !searchQuery.trim()">
            {{ searching ? "检索中..." : "运行检索" }}
          </button>
          <button class="btn primary" type="button" @click="runEval" :disabled="runningEval">
            {{ runningEval ? "评测中..." : "运行评测" }}
          </button>
        </div>
        <section v-if="actionMessage" class="inline-banner">
          <strong>{{ actionMessage }}</strong>
        </section>
      </section>

      <section class="surface-tabs memory-tabs">
        <button class="tab-btn" :class="{ active: activeTab === 'results' }" type="button" @click="activeTab = 'results'">
          召回结果
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'records' }" type="button" @click="activeTab = 'records'">
          最新记录
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'eval' }" type="button" @click="activeTab = 'eval'">
          质量指标
        </button>
      </section>

      <section class="surface-card workbench-panel memory-panel">
        <div v-if="activeTab === 'results'" class="content-scroll result-column">
          <article v-for="item in searchResults" :key="`${item.memory_id}-${item.source_kind}-${item.score}`" class="result-card">
            <header>
              <strong>{{ item.memory_type }}</strong>
              <span class="chip mono">score {{ Number(item.score || 0).toFixed(3) }}</span>
            </header>
            <p>{{ item.content }}</p>
            <div class="chip-bucket">
              <span class="chip">{{ item.source_kind }}</span>
              <span v-if="item.canonical_key" class="chip">{{ item.canonical_key }}</span>
              <span class="chip">importance {{ Number(item.importance || 0).toFixed(2) }}</span>
            </div>
          </article>
          <p v-if="!searchResults.length" class="muted">
            运行检索后，这里会展示召回到的记忆。如果你在 chat 模式下没有填写 User ID，结果会按设计返回空。
          </p>
        </div>

        <div v-else-if="activeTab === 'records'" class="content-scroll result-column">
          <article v-for="record in records" :key="record.memory_id" class="record-card">
            <div class="record-main">
              <header>
                <strong>{{ record.memory_type }}</strong>
                <span class="chip">{{ record.source_kind }}</span>
                <span class="chip">{{ record.status }}</span>
              </header>
              <p>{{ record.content }}</p>
            </div>
            <div class="record-meta">
              <span class="muted mono">{{ record.memory_id }}</span>
              <span class="muted">importance {{ Number(record.importance).toFixed(2) }}</span>
              <span class="muted">access {{ record.access_count }}</span>
            </div>
          </article>
          <p v-if="!records.length" class="muted">当前范围内没有记忆记录。</p>
        </div>

        <div v-else class="content-scroll result-column">
          <div v-if="evalSummary" class="eval-grid">
            <div class="summary-item">
              <span>Recall@k</span>
              <strong>{{ evalSummary.average_recall_at_k }}</strong>
            </div>
            <div class="summary-item">
              <span>Precision@k</span>
              <strong>{{ evalSummary.average_precision_at_k }}</strong>
            </div>
            <div class="summary-item">
              <span>污染率</span>
              <strong>{{ evalSummary.average_pollution_rate }}</strong>
            </div>
            <div class="summary-item">
              <span>冲突处理</span>
              <strong>{{ evalSummary.conflict_resolution_quality }}</strong>
            </div>
          </div>

          <article v-for="item in evalSummary?.cases || []" :key="item.case_id" class="result-card">
            <header>
              <strong>{{ item.case_id }}</strong>
              <span class="muted">recall {{ item.recall_at_k }} / precision {{ item.precision_at_k }}</span>
            </header>
            <p class="muted">expected: {{ item.expected.join(", ") }}</p>
            <p class="muted">retrieved: {{ item.retrieved.join(" | ") }}</p>
          </article>
          <p v-if="!evalSummary" class="muted">运行评测后，这里会展示 recall、precision、污染率和冲突处理质量。</p>
        </div>
      </section>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import {
  getMemoryStatus,
  getMemorySummary,
  listMemoryRecords,
  runMemoryEval,
  searchMemories,
  type MemoryEvalSummary,
  type MemoryRecord,
  type MemoryStatus,
  type MemorySummary
} from "../services/api";

const filters = reactive({
  appId: "chat",
  userId: "",
  sessionId: "",
  memoryType: ""
});

const loading = ref(false);
const searching = ref(false);
const runningEval = ref(false);
const includeGraph = ref(true);
const searchQuery = ref("这个聊天助手应该记住什么风格和用户事实？");
const pageError = ref("");
const actionMessage = ref("");

const status = ref<MemoryStatus | null>(null);
const summary = ref<MemorySummary | null>(null);
const records = ref<MemoryRecord[]>([]);
const searchResults = ref<MemoryRecord[]>([]);
const evalSummary = ref<MemoryEvalSummary | null>(null);
const activeTab = ref<"results" | "records" | "eval">("results");

onMounted(async () => {
  await refreshAll();
});

async function refreshAll(): Promise<void> {
  loading.value = true;
  pageError.value = "";
  actionMessage.value = "";
  try {
    const [statusResult, summaryResult, recordResult] = await Promise.all([
      getMemoryStatus(),
      getMemorySummary(filters.appId, filters.userId || undefined),
      listMemoryRecords({
        appId: filters.appId,
        sessionId: filters.sessionId || undefined,
        userId: filters.userId || undefined,
        memoryType: filters.memoryType || undefined,
        limit: 40
      })
    ]);
    status.value = statusResult;
    summary.value = summaryResult;
    records.value = recordResult;
  } catch (error) {
    pageError.value = getErrorMessage(error);
  } finally {
    loading.value = false;
  }
}

async function runSearch(): Promise<void> {
  if (!searchQuery.value.trim()) return;
  pageError.value = "";
  actionMessage.value = "";
  if (filters.appId === "chat" && !filters.userId.trim() && !filters.sessionId.trim()) {
    pageError.value = "聊天助手的记忆检索默认按用户隔离。请至少填写 User ID；如果只是排查当前会话，也可以填写 Session ID。";
    return;
  }
  searching.value = true;
  try {
    searchResults.value = await searchMemories({
      query: searchQuery.value,
      app_id: filters.appId,
      session_id: filters.sessionId || undefined,
      user_id: filters.userId || undefined,
      limit: 12,
      include_graph: includeGraph.value,
      retrieval_mode: "hybrid"
    });
    activeTab.value = "results";
    actionMessage.value = searchResults.value.length
      ? `检索完成，共召回 ${searchResults.value.length} 条记忆。`
      : "检索已执行，但当前过滤范围内没有命中记忆。";
  } catch (error) {
    pageError.value = getErrorMessage(error);
  } finally {
    searching.value = false;
  }
}

async function runEval(): Promise<void> {
  pageError.value = "";
  actionMessage.value = "";
  runningEval.value = true;
  try {
    evalSummary.value = await runMemoryEval(filters.appId);
    activeTab.value = "eval";
    actionMessage.value = "记忆评测已完成，已切换到质量指标页。";
  } catch (error) {
    pageError.value = getErrorMessage(error);
  } finally {
    runningEval.value = false;
  }
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
</script>

<style scoped>
.memory-shell {
  height: 100%;
  grid-template-columns: 360px minmax(0, 1fr);
}

.memory-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.memory-toolbar,
.memory-search {
  display: grid;
  gap: 12px;
  padding: 14px 16px;
}

.memory-toolbar {
  border-bottom: 1px solid rgba(76, 134, 255, 0.12);
}

.memory-toolbar h1,
.tool-strip h3 {
  margin: 6px 0 0;
  font-size: 1rem;
}

.status-grid,
.field-grid,
.summary-grid,
.eval-grid {
  display: grid;
  gap: 10px;
}

.field-grid,
.summary-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
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
.field select,
.field textarea {
  width: 100%;
  padding: 11px 13px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.84);
  color: var(--text);
}

.inner-panel,
.memory-panel {
  flex: 1;
  grid-template-rows: minmax(0, 1fr);
  display: grid;
  gap: 12px;
  padding: 14px;
  min-height: 0;
}

.status-grid {
  grid-template-columns: 1fr;
}

.info-card,
.summary-item,
.result-card,
.record-card {
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.74);
}

.info-card span,
.summary-item span {
  display: block;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.info-card strong,
.summary-item strong {
  display: block;
  margin-top: 8px;
}

.chip-bucket {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.memory-tabs {
  padding: 0 16px;
}

.result-column {
  display: grid;
  gap: 10px;
  padding: 16px;
  overflow: auto;
}

.result-card header,
.record-main header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.result-card p,
.record-main p {
  margin: 10px 0 0;
  white-space: pre-wrap;
}

.record-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  gap: 14px;
}

.record-meta {
  display: grid;
  gap: 6px;
  align-content: start;
  justify-items: end;
}

.eval-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

@media (max-width: 1180px) {
  .memory-shell {
    grid-template-columns: 1fr;
    height: auto;
  }

  .memory-main {
    min-height: 70vh;
  }
}

@media (max-width: 860px) {
  .field-grid,
  .summary-grid,
  .eval-grid,
  .record-card {
    grid-template-columns: 1fr;
  }
}
</style>
