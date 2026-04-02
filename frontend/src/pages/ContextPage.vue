<template>
  <section class="workbench-shell context-shell">
    <aside class="surface-card workbench-rail context-rail">
      <div class="tool-strip">
        <div>
          <p class="eyebrow">Context 工作台</p>
          <h2>Explain 与 Eval</h2>
        </div>
        <button class="btn ghost small" type="button" :disabled="loading" @click="runExplainNow">
          {{ loading ? "解析中..." : "解析上下文" }}
        </button>
      </div>

      <div class="rail-scroll compact-stack">
        <section v-if="errorMessage" class="inline-banner">
          <strong>执行失败</strong>
          <p class="muted">{{ errorMessage }}</p>
        </section>

        <section class="surface-card inner-panel">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">当前请求</p>
              <h3>选择应用与阶段</h3>
            </div>
            <button class="btn ghost small" type="button" :disabled="evalLoading" @click="runEvalNow">
              {{ evalLoading ? "评测中..." : "运行评测" }}
            </button>
          </div>
          <div class="field-grid">
            <label class="field">
              <span>应用</span>
              <select v-model="selectedAppId">
                <option value="chat">聊天助手</option>
                <option value="deep_research">深度研究</option>
              </select>
            </label>
            <label class="field">
              <span>阶段</span>
              <select v-model="selectedStage">
                <option v-for="stage in stageOptions" :key="stage" :value="stage">
                  {{ stage }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>Session ID</span>
              <input v-model="sessionId" type="text" />
            </label>
            <label class="field">
              <span>User ID</span>
              <input v-model="userId" type="text" />
            </label>
          </div>
          <label class="field">
            <span>输入</span>
            <textarea v-model="userInput" rows="6" placeholder="输入要解释的请求"></textarea>
          </label>
        </section>

        <section class="surface-card inner-panel">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">摘要</p>
              <h3>关键指标</h3>
            </div>
          </div>
          <div v-if="explainResult" class="metric-grid">
            <article class="metric-card">
              <span>选中 Token</span>
              <strong>{{ explainResult.diagnostics.selected_tokens ?? 0 }}</strong>
            </article>
            <article class="metric-card">
              <span>压缩后 Token</span>
              <strong>{{ explainResult.diagnostics.compressed_tokens ?? 0 }}</strong>
            </article>
            <article class="metric-card">
              <span>Gathered</span>
              <strong>{{ explainResult.diagnostics.gathered_count ?? 0 }}</strong>
            </article>
            <article class="metric-card">
              <span>Compressed</span>
              <strong>{{ explainResult.diagnostics.compressed_count ?? 0 }}</strong>
            </article>
          </div>
          <p v-else class="muted">运行解析后显示当前上下文构建的核心指标。</p>
        </section>
      </div>
    </aside>

    <section class="surface-card workbench-main context-main">
      <header class="skills-toolbar">
        <div>
          <p class="eyebrow">Context Explain</p>
          <h1>来源、预算、裁剪与压缩结果</h1>
        </div>
        <div class="summary-bar">
          <span class="chip">{{ selectedAppId }}</span>
          <span class="chip">{{ selectedStage }}</span>
          <span class="chip" v-if="explainResult">{{ packetCount }} packets</span>
        </div>
      </header>

      <section class="surface-tabs skills-tabs">
        <button class="tab-btn" :class="{ active: activeTab === 'overview' }" type="button" @click="activeTab = 'overview'">
          概览
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'packets' }" type="button" @click="activeTab = 'packets'">
          Packets
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'prompt' }" type="button" @click="activeTab = 'prompt'">
          Prompt 预览
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'eval' }" type="button" @click="activeTab = 'eval'">
          Eval
        </button>
      </section>

      <section class="surface-card workbench-panel context-panel">
        <div v-if="activeTab === 'overview'" class="content-scroll result-column">
          <article v-if="explainResult" class="result-card">
            <header class="tool-strip">
              <div>
                <strong>{{ explainResult.profile }}</strong>
                <p class="muted">light_mode: {{ String(explainResult.request_metadata.light_mode ?? false) }}</p>
              </div>
            </header>
            <div class="metric-grid">
              <article class="metric-card">
                <span>Source Diversity</span>
                <strong>{{ Object.keys(sourceSummary).length }}</strong>
              </article>
              <article class="metric-card">
                <span>去重率</span>
                <strong>{{ formatRatio(dedupeRate) }}</strong>
              </article>
              <article class="metric-card">
                <span>压缩增益</span>
                <strong>{{ formatRatio(compressionGain) }}</strong>
              </article>
              <article class="metric-card">
                <span>Budget 利用率</span>
                <strong>{{ formatRatio(utilization) }}</strong>
              </article>
            </div>
          </article>

          <article v-if="explainResult" class="result-card">
            <header><strong>Source Budgets</strong></header>
            <div class="chip-bucket">
              <span v-for="(value, key) in sourceBudgets" :key="key" class="chip">{{ key }} {{ formatRatio(Number(value)) }}</span>
            </div>
          </article>

          <article v-if="explainResult" class="result-card">
            <header><strong>Source Summary</strong></header>
            <div class="result-column">
              <div v-for="(value, key) in sourceSummary" :key="key" class="compact-row">
                <div class="tool-strip">
                  <strong>{{ key }}</strong>
                  <span class="chip">{{ value.tokens }} tokens</span>
                </div>
                <p class="muted">gathered {{ value.gathered }} / selected {{ value.selected }} / compressed {{ value.compressed }}</p>
              </div>
            </div>
          </article>

          <article v-if="explainResult" class="result-card">
            <header><strong>Sections</strong></header>
            <div class="chip-bucket">
              <span v-for="section in explainResult.sections" :key="section.title" class="chip">{{ section.title }}</span>
            </div>
          </article>
        </div>

        <div v-else-if="activeTab === 'packets'" class="content-scroll result-column">
          <article v-for="(packet, index) in explainResult?.packets || []" :key="`${packet.source}-${index}`" class="result-card">
            <header class="tool-strip">
              <div>
                <strong>{{ packet.source }}</strong>
                <p class="muted">score {{ packet.relevance_score.toFixed(3) }}</p>
              </div>
              <div class="chip-bucket">
                <span class="chip">{{ packet.token_count }} tokens</span>
                <span v-if="packet.metadata.compressed" class="chip">compressed</span>
              </div>
            </header>
            <pre class="command-block">{{ packet.content_preview }}</pre>
          </article>
          <p v-if="!explainResult?.packets.length" class="muted">先运行一次解析，上下文 packets 会显示在这里。</p>
        </div>

        <div v-else-if="activeTab === 'prompt'" class="content-scroll result-column">
          <article class="result-card">
            <header><strong>Prompt 预览</strong></header>
            <pre class="command-block">{{ explainResult?.prompt_preview || "先运行一次解析查看 prompt 预览。" }}</pre>
          </article>
        </div>

        <div v-else class="content-scroll result-column">
          <article v-if="evalSummary" class="result-card">
            <header><strong>Context Eval Summary</strong></header>
            <div class="metric-grid">
              <article class="metric-card">
                <span>平均利用率</span>
                <strong>{{ formatRatio(evalSummary.average_utilization) }}</strong>
              </article>
              <article class="metric-card">
                <span>平均去重率</span>
                <strong>{{ formatRatio(evalSummary.average_dedupe_rate) }}</strong>
              </article>
              <article class="metric-card">
                <span>平均压缩增益</span>
                <strong>{{ formatRatio(evalSummary.average_compression_gain) }}</strong>
              </article>
              <article class="metric-card">
                <span>平均 Source Diversity</span>
                <strong>{{ evalSummary.average_source_diversity.toFixed(2) }}</strong>
              </article>
            </div>
          </article>
          <article v-for="item in evalSummary?.cases || []" :key="item.case_id" class="result-card">
            <header class="tool-strip">
              <div>
                <strong>{{ item.case_id }}</strong>
                <p class="muted">{{ item.app_id }} / {{ item.stage }}</p>
              </div>
              <span class="chip">{{ item.light_mode ? "light" : "full" }}</span>
            </header>
            <div class="metric-grid">
              <article class="metric-card"><span>利用率</span><strong>{{ formatRatio(item.utilization) }}</strong></article>
              <article class="metric-card"><span>去重率</span><strong>{{ formatRatio(item.dedupe_rate) }}</strong></article>
              <article class="metric-card"><span>压缩增益</span><strong>{{ formatRatio(item.compression_gain) }}</strong></article>
              <article class="metric-card"><span>Source Diversity</span><strong>{{ item.source_diversity.toFixed(0) }}</strong></article>
            </div>
          </article>
          <p v-if="!evalSummary" class="muted">点击左侧“运行评测”查看 context engineering 的基线指标。</p>
        </div>
      </section>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { explainContext, runContextEval, type ContextEvalSummary, type ContextExplainResult } from "../services/api";

const selectedAppId = ref<"chat" | "deep_research">("chat");
const selectedStage = ref("chat.reply");
const sessionId = ref("context-inspect");
const userId = ref("context-user");
const userInput = ref("你好");
const loading = ref(false);
const evalLoading = ref(false);
const errorMessage = ref("");
const activeTab = ref<"overview" | "packets" | "prompt" | "eval">("overview");
const explainResult = ref<ContextExplainResult | null>(null);
const evalSummary = ref<ContextEvalSummary | null>(null);

const stageOptions = computed(() =>
  selectedAppId.value === "chat"
    ? ["chat.reply"]
    : ["research.plan", "research.summarize", "research.report"]
);

const sourceBudgets = computed<Record<string, number>>(() => (explainResult.value?.diagnostics.source_budgets as Record<string, number>) || {});
const sourceSummary = computed<Record<string, { gathered: number; selected: number; compressed: number; tokens: number }>>(
  () => (explainResult.value?.diagnostics.sources as Record<string, { gathered: number; selected: number; compressed: number; tokens: number }>) || {}
);
const packetCount = computed(() => explainResult.value?.packets.length || 0);
const dedupeRate = computed(() => Number((explainResult.value?.diagnostics.selection as Record<string, number> | undefined)?.dropped_by_dedupe || 0) / Math.max(1, Number(explainResult.value?.diagnostics.gathered_count || 0)));
const compressionGain = computed(() => {
  const selectedTokens = Number(explainResult.value?.diagnostics.selected_tokens || 0);
  const compressedTokens = Number(explainResult.value?.diagnostics.compressed_tokens || 0);
  return Math.max(0, 1 - compressedTokens / Math.max(1, selectedTokens));
});
const utilization = computed(() => {
  const selectedTokens = Number(explainResult.value?.diagnostics.selected_tokens || 0);
  const maxTokens = Number(explainResult.value?.diagnostics.max_tokens || 1);
  return selectedTokens / Math.max(1, maxTokens);
});

async function runExplainNow(): Promise<void> {
  loading.value = true;
  try {
    explainResult.value = await explainContext({
      app_id: selectedAppId.value,
      stage: selectedStage.value,
      session_id: sessionId.value.trim() || "context-inspect",
      user_id: userId.value.trim() || undefined,
      user_input: userInput.value.trim()
    });
    activeTab.value = "overview";
    errorMessage.value = "";
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    loading.value = false;
  }
}

async function runEvalNow(): Promise<void> {
  evalLoading.value = true;
  try {
    evalSummary.value = await runContextEval();
    activeTab.value = "eval";
    errorMessage.value = "";
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    evalLoading.value = false;
  }
}

function formatRatio(value: number): string {
  return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "0.0%";
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
</script>

<style scoped>
.context-shell {
  grid-template-columns: minmax(320px, 360px) minmax(0, 1fr);
}

.context-main {
  min-height: 0;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 12px;
}

.context-panel {
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  margin: 0 18px 18px;
}

.context-panel > .content-scroll {
  min-height: 0;
  height: 100%;
  overflow: auto;
}

@media (max-width: 1100px) {
  .context-shell {
    grid-template-columns: 1fr;
  }
}
</style>
