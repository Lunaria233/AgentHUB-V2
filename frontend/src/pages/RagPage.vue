<template>
  <section class="workbench-shell rag-shell">
    <aside class="surface-card workbench-rail rag-rail">
      <div class="tool-strip">
        <div>
          <p class="eyebrow">RAG Workbench</p>
          <h2>知识导入与索引</h2>
        </div>
        <button class="btn ghost small" type="button" @click="refreshAll" :disabled="loading">
          {{ loading ? "刷新中..." : "刷新" }}
        </button>
      </div>

      <div class="rail-scroll inspector-stack">
        <section class="status-grid">
          <div class="info-card">
            <span>向量后端</span>
            <strong>{{ status?.vector_backend.enabled ? "Qdrant 在线" : "未启用" }}</strong>
            <small class="muted mono">{{ status?.vector_backend.collection || "n/a" }}</small>
          </div>
          <div class="info-card">
            <span>Embedding</span>
            <strong>{{ status?.embedding.provider || "unknown" }}</strong>
            <small class="muted">{{ status?.embedding.configured_model || "n/a" }}</small>
          </div>
        </section>

        <section v-if="pageError" class="inline-banner">
          <strong>RAG 后端检查失败</strong>
          <p class="muted">{{ pageError }}</p>
        </section>

        <section class="surface-card inner-panel">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">作用域</p>
              <h3>检索范围</h3>
            </div>
            <button class="btn ghost small" type="button" @click="rebuildIndex" :disabled="rebuilding">
              {{ rebuilding ? "重建中..." : "重建索引" }}
            </button>
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
              <span>检索模式</span>
              <select v-model="searchOptions.retrievalMode">
                <option value="hybrid">hybrid</option>
                <option value="lexical">lexical</option>
                <option value="vector">vector</option>
              </select>
            </label>
          </div>

          <div class="toggle-grid">
            <label class="toggle"><input v-model="searchOptions.includeSessionTemporary" type="checkbox" />当前会话</label>
            <label class="toggle"><input v-model="searchOptions.includeUserPrivate" type="checkbox" />用户长期</label>
            <label class="toggle"><input v-model="searchOptions.includeAppShared" type="checkbox" />应用共享</label>
            <label class="toggle"><input v-model="searchOptions.includePublic" type="checkbox" />公共知识</label>
          </div>
        </section>

        <section class="surface-card inner-panel">
          <KnowledgeQuickPanel
            :app-id="filters.appId"
            :session-id="filters.sessionId"
            :user-id="filters.userId"
            title="导入文本、网页或文件"
            @ingested="handleKnowledgeIngested"
          />
        </section>

        <section class="surface-card inner-panel">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">知识库</p>
              <h3>Scopes 与文档</h3>
            </div>
          </div>
          <div class="chip-bucket">
            <span v-for="scope in scopes" :key="scope.kb_id" class="chip">
              {{ scope.visibility }} / {{ scope.kb_id }} / {{ scope.document_count }}
            </span>
            <p v-if="!scopes.length" class="muted">当前范围下没有可见 scope。</p>
          </div>

          <div class="content-scroll document-list">
            <article v-for="document in documents" :key="document.document_id" class="document-row">
              <div class="document-copy">
                <strong>{{ document.title }}</strong>
                <p class="muted">{{ document.visibility }} / {{ document.source_type }} / {{ document.chunk_count }} 个 chunk</p>
                <p class="muted mono">{{ document.source_uri || document.file_name || document.kb_id }}</p>
              </div>
              <button class="btn ghost small" type="button" @click="deleteDocument(document.document_id)">删除</button>
            </article>
            <p v-if="!documents.length" class="muted">当前范围内没有文档。</p>
          </div>
        </section>
      </div>
    </aside>

    <section class="surface-card workbench-main rag-main">
      <header class="rag-toolbar">
        <div>
          <p class="eyebrow">检索与回答</p>
          <h1>带结构化来源的 RAG 调试台</h1>
        </div>
        <div class="summary-bar">
          <span class="chip">{{ enabledFeatureCount }} / 5 已启用</span>
          <span class="chip">URL / rerank / MQE / HyDE / sources</span>
        </div>
      </header>

      <section class="search-control">
        <label class="field">
          <span>问题</span>
          <textarea v-model="query" rows="3" placeholder="输入问题，检查召回、rerank、MQE、HyDE 和结构化引用。"></textarea>
        </label>

        <div class="toggle-grid">
          <label class="toggle"><input v-model="searchOptions.queryRewriteEnabled" type="checkbox" />查询改写</label>
          <label class="toggle"><input v-model="searchOptions.hydeEnabled" type="checkbox" />HyDE</label>
          <label class="toggle"><input v-model="searchOptions.rerankEnabled" type="checkbox" />rerank</label>
        </div>

        <div class="field-grid">
          <label class="field">
            <span>改写模式</span>
            <select v-model="searchOptions.queryRewriteMode">
              <option value="hybrid">hybrid</option>
              <option value="heuristic">heuristic</option>
              <option value="llm">llm</option>
            </select>
          </label>
          <label class="field">
            <span>MQE 变体数</span>
            <input v-model.number="searchOptions.mqeVariants" type="number" min="1" max="8" />
          </label>
          <label class="field">
            <span>HyDE 模式</span>
            <select v-model="searchOptions.hydeMode">
              <option value="model">model</option>
              <option value="fallback">fallback</option>
            </select>
          </label>
          <label class="field">
            <span>Rerank Top-N</span>
            <input v-model.number="searchOptions.rerankTopN" type="number" min="1" max="20" />
          </label>
        </div>

        <div class="summary-bar">
          <button class="btn ghost" type="button" :disabled="searching || !query.trim()" @click="runSearch">
            {{ searching ? "检索中..." : "运行检索" }}
          </button>
          <button class="btn primary" type="button" :disabled="answering || !query.trim()" @click="runAnswer">
            {{ answering ? "回答中..." : "带来源回答" }}
          </button>
        </div>

        <section v-if="actionMessage" class="inline-banner">
          <strong>{{ actionMessage }}</strong>
        </section>
      </section>

      <section class="surface-tabs rag-tabs">
        <button class="tab-btn" :class="{ active: activeTab === 'results' }" type="button" @click="activeTab = 'results'">
          召回结果
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'answer' }" type="button" @click="activeTab = 'answer'">
          回答与来源
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'eval' }" type="button" @click="activeTab = 'eval'">
          评测
        </button>
      </section>

      <section class="surface-card workbench-panel rag-panel">
        <div v-if="activeTab === 'results'" class="content-scroll result-column">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">Top-K 召回</p>
              <h2>检索结果</h2>
            </div>
            <span class="chip">{{ searchResult?.mode || searchOptions.retrievalMode }}</span>
          </div>

          <article v-for="item in searchResult?.items || []" :key="item.chunk_id" class="result-card">
            <header>
              <strong>{{ item.title }}</strong>
              <span class="chip">{{ item.visibility }}</span>
            </header>
            <p>{{ item.preview }}</p>
            <div class="chip-bucket">
              <span class="chip">总分 {{ item.score.toFixed(3) }}</span>
              <span class="chip">词法 {{ item.lexical_score.toFixed(3) }}</span>
              <span class="chip">向量 {{ item.vector_score.toFixed(3) }}</span>
              <span class="chip">rerank {{ item.rerank_score.toFixed(3) }}</span>
              <span class="chip">{{ item.page_or_section || "section n/a" }}</span>
            </div>
          </article>
          <p v-if="!(searchResult?.items?.length)" class="muted">
            先运行检索。若结果仍为空，通常表示当前 app/user/session 作用域下没有可访问知识，或过滤条件太严格。
          </p>
        </div>

        <div v-else-if="activeTab === 'answer'" class="content-scroll result-column">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">回答</p>
              <h2>带结构化来源输出</h2>
            </div>
          </div>

          <div class="answer-card">
            <MarkdownContent :source="answerResult?.answer || '运行「带来源回答」后，这里会显示最终答案。'" />
          </div>

          <article v-for="(source, index) in visibleSources" :key="`${source.doc_id}-${source.chunk_id}-${index}`" class="source-card">
            <header>
              <strong>[S{{ index + 1 }}] {{ source.title }}</strong>
              <span class="chip">{{ source.visibility }}</span>
            </header>
            <p>{{ source.preview }}</p>
            <div class="chip-bucket">
              <span class="chip">score {{ Number(source.score).toFixed(3) }}</span>
              <span class="chip">{{ source.page_or_section || "section n/a" }}</span>
              <span class="chip">{{ source.source_type }}</span>
            </div>
          </article>

          <details class="debug-panel">
            <summary>查看调试信息</summary>
            <pre class="command-block">{{ debugPayload }}</pre>
          </details>
        </div>

        <div v-else class="content-scroll result-column">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">评测</p>
              <h2>RAG 质量指标</h2>
            </div>
            <button class="btn primary small" type="button" @click="runEval" :disabled="runningEval">
              {{ runningEval ? "运行中..." : "运行评测" }}
            </button>
          </div>

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
              <span>MRR</span>
              <strong>{{ evalSummary.average_mrr }}</strong>
            </div>
            <div class="summary-item">
              <span>泄漏率</span>
              <strong>{{ evalSummary.average_leakage_rate }}</strong>
            </div>
            <div class="summary-item">
              <span>来源覆盖</span>
              <strong>{{ evalSummary.average_source_coverage }}</strong>
            </div>
          </div>

          <article v-for="item in evalSummary?.cases || []" :key="item.case_id" class="result-card">
            <header>
              <strong>{{ item.case_id }}</strong>
              <span class="chip">{{ item.mode }}</span>
            </header>
            <p class="muted">{{ item.description }}</p>
            <p class="muted">expected: {{ item.expected.join(", ") }}</p>
            <p class="muted">retrieved: {{ item.retrieved.join(" | ") }}</p>
            <div class="chip-bucket">
              <span class="chip">recall {{ item.recall_at_k }}</span>
              <span class="chip">precision {{ item.precision_at_k }}</span>
              <span class="chip">mrr {{ item.mrr }}</span>
              <span class="chip">leakage {{ item.leakage_rate }}</span>
            </div>
          </article>
        </div>
      </section>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import KnowledgeQuickPanel from "../components/KnowledgeQuickPanel.vue";
import MarkdownContent from "../components/MarkdownContent.vue";
import {
  answerWithRag,
  deleteRagDocument,
  getRagStatus,
  listRagDocuments,
  listRagScopes,
  rebuildRagIndex,
  runRagEval,
  searchRag,
  type RAGAnswerResponse,
  type RAGCitation,
  type RAGDocumentRecord,
  type RAGEvalSummary,
  type RAGScopeSummary,
  type RAGSearchResponse,
  type RAGStatus
} from "../services/api";

const loading = ref(false);
const searching = ref(false);
const answering = ref(false);
const rebuilding = ref(false);
const runningEval = ref(false);
const pageError = ref("");
const actionMessage = ref("");

const status = ref<RAGStatus | null>(null);
const scopes = ref<RAGScopeSummary[]>([]);
const documents = ref<RAGDocumentRecord[]>([]);
const searchResult = ref<RAGSearchResponse | null>(null);
const answerResult = ref<RAGAnswerResponse | null>(null);
const evalSummary = ref<RAGEvalSummary | null>(null);
const activeTab = ref<"results" | "answer" | "eval">("results");

const filters = reactive({
  appId: "chat",
  userId: "",
  sessionId: ""
});

const searchOptions = reactive({
  retrievalMode: "hybrid",
  includeSessionTemporary: true,
  includeUserPrivate: true,
  includeAppShared: true,
  includePublic: true,
  queryRewriteEnabled: true,
  queryRewriteMode: "hybrid",
  mqeVariants: 4,
  hydeEnabled: true,
  hydeMode: "model",
  rerankEnabled: true,
  rerankStrategy: "feature",
  rerankTopN: 12
});

const query = ref("当前知识域里有哪些内容可以直接回答？");

const enabledFeatureCount = computed(() => {
  const features = status.value?.features;
  if (!features) return 0;
  return [features.url_import, features.rerank, features.mqe, features.hyde, features.structured_sources].filter(Boolean).length;
});

const visibleSources = computed<RAGCitation[]>(() => answerResult.value?.sources || searchResult.value?.sources || []);
const debugPayload = computed(() => JSON.stringify(answerResult.value?.debug || searchResult.value?.debug || {}, null, 2));

onMounted(async () => {
  await refreshAll();
});

async function refreshAll(): Promise<void> {
  loading.value = true;
  pageError.value = "";
  actionMessage.value = "";
  try {
    const [statusResult, scopeResult, documentResult] = await Promise.all([
      getRagStatus(),
      listRagScopes({
        appId: filters.appId,
        userId: filters.userId || undefined,
        sessionId: filters.sessionId || undefined
      }),
      listRagDocuments({
        appId: filters.appId,
        userId: filters.userId || undefined,
        sessionId: filters.sessionId || undefined
      })
    ]);
    status.value = statusResult;
    scopes.value = scopeResult;
    documents.value = documentResult;
  } catch (error) {
    pageError.value = getErrorMessage(error);
  } finally {
    loading.value = false;
  }
}

async function runSearch(): Promise<void> {
  if (!query.value.trim()) return;
  searching.value = true;
  pageError.value = "";
  actionMessage.value = "";
  try {
    searchResult.value = await searchRag(buildQueryPayload());
    answerResult.value = null;
    activeTab.value = "results";
    actionMessage.value = searchResult.value.items.length
      ? `检索完成，共返回 ${searchResult.value.items.length} 个 chunk，模式为 ${searchResult.value.mode}。`
      : "检索已执行，但当前可访问作用域下没有命中结果。";
  } catch (error) {
    pageError.value = getErrorMessage(error);
  } finally {
    searching.value = false;
  }
}

async function runAnswer(): Promise<void> {
  if (!query.value.trim()) return;
  answering.value = true;
  pageError.value = "";
  actionMessage.value = "";
  try {
    answerResult.value = await answerWithRag(buildQueryPayload());
    activeTab.value = "answer";
    actionMessage.value = answerResult.value.sources.length
      ? `回答完成，共引用 ${answerResult.value.sources.length} 条来源。`
      : "回答已执行，但没有检索到可引用来源；当前答案可能使用了 fallback。";
  } catch (error) {
    pageError.value = getErrorMessage(error);
  } finally {
    answering.value = false;
  }
}

async function rebuildIndex(): Promise<void> {
  rebuilding.value = true;
  pageError.value = "";
  actionMessage.value = "";
  try {
    await rebuildRagIndex({ app_id: filters.appId });
    actionMessage.value = "索引重建完成。";
    await refreshAll();
  } catch (error) {
    pageError.value = getErrorMessage(error);
  } finally {
    rebuilding.value = false;
  }
}

async function deleteDocument(documentId: string): Promise<void> {
  try {
    await deleteRagDocument({
      documentId,
      app_id: filters.appId,
      user_id: filters.userId || undefined,
      session_id: filters.sessionId || undefined
    });
    actionMessage.value = "文档已删除。";
    await refreshAll();
  } catch (error) {
    pageError.value = getErrorMessage(error);
  }
}

async function runEval(): Promise<void> {
  runningEval.value = true;
  pageError.value = "";
  actionMessage.value = "";
  try {
    evalSummary.value = await runRagEval(filters.appId);
    activeTab.value = "eval";
    actionMessage.value = "RAG 评测已完成，已切换到评测页。";
  } catch (error) {
    pageError.value = getErrorMessage(error);
  } finally {
    runningEval.value = false;
  }
}

async function handleKnowledgeIngested(): Promise<void> {
  actionMessage.value = "知识已入库，列表已刷新。";
  await refreshAll();
}

function buildQueryPayload() {
  return {
    app_id: filters.appId,
    query: query.value.trim(),
    user_id: filters.userId || undefined,
    session_id: filters.sessionId || undefined,
    retrieval_mode: searchOptions.retrievalMode,
    include_session_temporary: searchOptions.includeSessionTemporary,
    include_user_private: searchOptions.includeUserPrivate,
    include_app_shared: searchOptions.includeAppShared,
    include_public: searchOptions.includePublic,
    query_rewrite_enabled: searchOptions.queryRewriteEnabled,
    query_rewrite_mode: searchOptions.queryRewriteMode,
    mqe_variants: searchOptions.mqeVariants,
    hyde_enabled: searchOptions.hydeEnabled,
    hyde_mode: searchOptions.hydeMode,
    rerank_enabled: searchOptions.rerankEnabled,
    rerank_strategy: searchOptions.rerankStrategy,
    rerank_top_n: searchOptions.rerankTopN
  };
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
</script>

<style scoped>
.rag-shell {
  height: 100%;
  grid-template-columns: 360px minmax(0, 1fr);
}

.rag-rail {
  gap: 10px;
}

.rag-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.rag-toolbar,
.search-control {
  display: grid;
  gap: 12px;
  padding: 14px 16px;
}

.rag-toolbar {
  border-bottom: 1px solid rgba(76, 134, 255, 0.12);
}

.rag-toolbar h1,
.tool-strip h3 {
  margin: 6px 0 0;
  font-size: 1rem;
}

.inner-panel,
.rag-panel {
  flex: 1;
  grid-template-rows: minmax(0, 1fr);
  display: grid;
  gap: 12px;
  padding: 14px;
  min-height: 0;
}

.status-grid,
.field-grid,
.eval-grid {
  display: grid;
  gap: 10px;
}

.status-grid {
  grid-template-columns: 1fr;
}

.field-grid {
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

.toggle-grid {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.68);
}

.chip-bucket {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.document-list,
.result-column {
  display: grid;
  gap: 10px;
  min-height: 0;
}

.result-column {
  overflow: auto;
}

.document-row,
.result-card,
.source-card,
.answer-card,
.summary-item,
.info-card {
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.74);
}

.document-row,
.result-card header,
.source-card header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.document-copy {
  min-width: 0;
}

.document-copy p {
  margin: 6px 0 0;
}

.rag-tabs {
  padding: 0 16px;
}

.result-column {
  padding: 16px;
}

.result-card p,
.source-card p {
  margin: 10px 0 0;
}

.debug-panel {
  border: 1px solid var(--border);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.68);
}

.debug-panel summary {
  cursor: pointer;
  padding: 12px 14px;
  font-weight: 600;
}

.eval-grid {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.summary-item span,
.info-card span {
  display: block;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.summary-item strong,
.info-card strong {
  display: block;
  margin-top: 8px;
}

@media (max-width: 1180px) {
  .rag-shell {
    grid-template-columns: 1fr;
    height: auto;
  }

  .rag-main {
    min-height: 70vh;
  }
}

@media (max-width: 860px) {
  .field-grid,
  .eval-grid {
    grid-template-columns: 1fr;
  }
}
</style>
