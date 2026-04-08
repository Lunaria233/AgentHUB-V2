<template>
  <section class="workbench-shell skills-shell">
    <aside class="surface-card workbench-rail skills-rail">
      <div class="tool-strip sticky-rail-head">
        <div>
          <p class="eyebrow">Skills 工作台</p>
          <h2>应用与阶段</h2>
        </div>
        <div class="summary-bar">
          <button class="btn ghost small" type="button" :disabled="loading" @click="refreshAll">
            {{ loading ? "刷新中..." : "刷新" }}
          </button>
          <button class="btn ghost small" type="button" :disabled="loading" @click="reloadCatalog">
            重新扫描
          </button>
        </div>
      </div>

      <div class="rail-scroll compact-stack">
        <section v-if="errorMessage" class="inline-banner">
          <strong>加载失败</strong>
          <p class="muted">{{ errorMessage }}</p>
        </section>

        <section class="surface-card inner-panel">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">当前上下文</p>
              <h3>选择应用与阶段</h3>
            </div>
            <span class="chip">{{ skillEnabledApps.length }} 个应用</span>
          </div>
          <div class="field-grid">
            <label class="field">
              <span>应用</span>
              <select v-model="selectedAppId">
                <option v-for="app in skillEnabledApps" :key="app.app_id" :value="app.app_id">
                  {{ appLabel(app.app_id, app.name) }}
                </option>
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
              <span>User ID（可选）</span>
              <input v-model="userId" type="text" placeholder="用于查看按用户解析的技能效果" />
            </label>
          </div>
        </section>

        <section class="surface-card inner-panel">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">Skill 绑定</p>
              <h3>{{ bindingInfo?.app_name || "未选择应用" }}</h3>
            </div>
            <span class="chip">{{ bindingInfo?.bindings.length ?? 0 }} 条绑定</span>
          </div>
          <div class="pane-scroll compact-stack">
            <article
              v-for="binding in bindingInfo?.bindings || []"
              :key="`${binding.skill_id}-${binding.stage}-${binding.priority}`"
              class="compact-row"
            >
              <div class="tool-strip">
                <strong>{{ binding.skill_id }}</strong>
                <span class="chip">{{ binding.stage }}</span>
              </div>
              <p class="muted">priority {{ binding.priority }} · {{ binding.enabled ? "启用" : "禁用" }}</p>
            </article>
            <p v-if="!(bindingInfo?.bindings.length)" class="muted">当前应用没有绑定任何技能。</p>
          </div>
        </section>

        <section class="surface-card inner-panel">
          <div class="tool-strip">
            <div>
              <p class="eyebrow">评测</p>
              <h3>Skills Eval</h3>
            </div>
            <button class="btn primary small" type="button" :disabled="evalLoading" @click="runEvalNow">
              {{ evalLoading ? "评测中..." : "运行评测" }}
            </button>
          </div>
          <div v-if="evalSummary" class="metric-grid">
            <article class="metric-card">
              <span>平均 Precision</span>
              <strong>{{ formatMetric(evalSummary.average_precision) }}</strong>
            </article>
            <article class="metric-card">
              <span>平均 Recall</span>
              <strong>{{ formatMetric(evalSummary.average_recall) }}</strong>
            </article>
            <article class="metric-card">
              <span>引用覆盖率</span>
              <strong>{{ formatMetric(evalSummary.average_reference_loading_coverage) }}</strong>
            </article>
            <article class="metric-card">
              <span>资源清单覆盖率</span>
              <strong>{{ formatMetric(evalSummary.average_resource_inventory_coverage) }}</strong>
            </article>
          </div>
          <p v-else class="muted">运行评测后可查看 skill 解析质量指标。</p>
        </section>
      </div>
    </aside>

    <section class="surface-card workbench-main skills-main">
      <header class="skills-toolbar">
        <div>
          <p class="eyebrow">Resolved Skills</p>
          <h1>当前阶段生效的技能与资源</h1>
        </div>
        <div class="summary-bar">
          <span class="chip">{{ selectedAppId || "未选应用" }}</span>
          <span class="chip">{{ selectedStage || "未选阶段" }}</span>
          <button class="btn primary small" type="button" :disabled="loading" @click="loadResolved">
            解析当前阶段
          </button>
        </div>
      </header>

      <section class="surface-tabs skills-tabs">
        <button class="tab-btn" :class="{ active: activeTab === 'resolved' }" type="button" @click="activeTab = 'resolved'">
          生效技能
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'catalog' }" type="button" @click="activeTab = 'catalog'">
          技能目录
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'eval' }" type="button" @click="activeTab = 'eval'">
          评测结果
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'explain' }" type="button" @click="activeTab = 'explain'">
          使用说明
        </button>
      </section>

      <section class="surface-card workbench-panel skills-panel">
        <div v-if="activeTab === 'resolved'" class="content-scroll result-column">
          <article v-for="skill in resolvedSkills" :key="`${skill.skill_id}-${skill.stage}`" class="result-card">
            <header class="tool-strip">
              <div>
                <strong>{{ skill.name }}</strong>
                <p class="muted mono">{{ skill.skill_id }} · {{ skill.stage }}</p>
              </div>
              <span class="chip">{{ skill.tool_names.length }} tools</span>
            </header>

            <div v-if="catalogMap[skill.skill_id]" class="muted skill-description">
              {{ catalogMap[skill.skill_id].description }}
            </div>

            <section v-if="skill.prompt_fragments.length" class="section-block">
              <h4>Prompt 片段</h4>
              <ul class="markdown-list">
                <li v-for="fragment in skill.prompt_fragments" :key="fragment">{{ fragment }}</li>
              </ul>
            </section>

            <section v-if="skill.tool_names.length" class="section-block">
              <h4>偏好工具</h4>
              <div class="chip-bucket">
                <span v-for="tool in skill.tool_names" :key="tool" class="chip">{{ tool }}</span>
              </div>
            </section>

            <section v-if="skill.references.length" class="section-block">
              <h4>References</h4>
              <div class="reference-stack">
                <article
                  v-for="reference in skill.references"
                  :key="`${skill.skill_id}-${reference.relative_path}`"
                  class="reference-card"
                >
                  <div class="tool-strip">
                    <strong>{{ reference.title }}</strong>
                    <span class="chip">{{ reference.resource_type }}</span>
                  </div>
                  <p class="muted mono">{{ reference.relative_path }}</p>
                  <p class="reference-preview">{{ reference.content || "未加载内容" }}</p>
                </article>
              </div>
            </section>

            <section v-if="skill.scripts.length || skill.assets.length" class="resource-grid">
              <article v-if="skill.scripts.length" class="surface-card inner-panel">
                <div class="tool-strip">
                  <strong>Scripts</strong>
                  <span class="chip">{{ skill.scripts.length }}</span>
                </div>
                <ul class="path-list">
                  <li v-for="resource in skill.scripts" :key="resource.relative_path">
                    <span>{{ resource.title }}</span>
                    <code>{{ resource.relative_path }}</code>
                  </li>
                </ul>
              </article>
              <article v-if="skill.assets.length" class="surface-card inner-panel">
                <div class="tool-strip">
                  <strong>Assets</strong>
                  <span class="chip">{{ skill.assets.length }}</span>
                </div>
                <ul class="path-list">
                  <li v-for="resource in skill.assets" :key="resource.relative_path">
                    <span>{{ resource.title }}</span>
                    <code>{{ resource.relative_path }}</code>
                  </li>
                </ul>
              </article>
            </section>
          </article>
          <p v-if="!resolvedSkills.length" class="muted">
            当前 app/stage 下没有解析出技能。请先选择应用和阶段，再点击“解析当前阶段”。
          </p>
        </div>

        <div v-else-if="activeTab === 'catalog'" class="content-scroll result-column">
          <article v-for="skill in catalog" :key="skill.skill_id" class="record-card">
            <div class="record-main">
              <header class="tool-strip">
                <div>
                  <strong>{{ skill.name }}</strong>
                  <p class="muted mono">{{ skill.skill_id }}</p>
                </div>
                <div class="chip-bucket">
                  <span class="chip">{{ skill.hydrated ? "已加载" : "按需加载" }}</span>
                  <span class="chip">{{ skill.stage_configs.length || 1 }} 个阶段</span>
                </div>
              </header>
              <p>{{ skill.description }}</p>
              <div class="chip-bucket">
                <span v-for="tag in skill.tags" :key="tag" class="chip">{{ tag }}</span>
                <span v-for="stage in skill.stage_configs" :key="`${skill.skill_id}-${stage}`" class="chip">{{ stage }}</span>
                <span v-for="tool in skill.tool_names" :key="`${skill.skill_id}-${tool}`" class="chip">{{ tool }}</span>
              </div>
              <div class="resource-summary">
                <span>references {{ skill.resource_counts.references }}</span>
                <span>scripts {{ skill.resource_counts.scripts }}</span>
                <span>assets {{ skill.resource_counts.assets }}</span>
              </div>
              <p class="muted mono">{{ skill.source_dir }}</p>
            </div>
          </article>
        </div>

        <div v-else-if="activeTab === 'eval'" class="content-scroll result-column">
          <article v-if="evalSummary" class="result-card">
            <header class="tool-strip">
              <div>
                <strong>评测摘要</strong>
                <p class="muted">skills catalog {{ evalSummary.catalog_skill_count }} 个技能</p>
              </div>
            </header>
            <div class="metric-grid">
              <article class="metric-card">
                <span>平均 Precision</span>
                <strong>{{ formatMetric(evalSummary.average_precision) }}</strong>
              </article>
              <article class="metric-card">
                <span>平均 Recall</span>
                <strong>{{ formatMetric(evalSummary.average_recall) }}</strong>
              </article>
              <article class="metric-card">
                <span>引用覆盖率</span>
                <strong>{{ formatMetric(evalSummary.average_reference_loading_coverage) }}</strong>
              </article>
              <article class="metric-card">
                <span>资源清单覆盖率</span>
                <strong>{{ formatMetric(evalSummary.average_resource_inventory_coverage) }}</strong>
              </article>
            </div>
          </article>
          <article v-for="caseResult in evalSummary?.cases || []" :key="caseResult.case_id" class="result-card">
            <header class="tool-strip">
              <div>
                <strong>{{ caseResult.case_id }}</strong>
                <p class="muted">expected {{ caseResult.expected_skill_ids.join(", ") }}</p>
              </div>
              <span class="chip">resolved {{ caseResult.resolved_skill_ids.length }}</span>
            </header>
            <div class="metric-grid">
              <article class="metric-card">
                <span>Precision</span>
                <strong>{{ formatMetric(caseResult.precision) }}</strong>
              </article>
              <article class="metric-card">
                <span>Recall</span>
                <strong>{{ formatMetric(caseResult.recall) }}</strong>
              </article>
              <article class="metric-card">
                <span>引用覆盖率</span>
                <strong>{{ formatMetric(caseResult.reference_loading_coverage) }}</strong>
              </article>
              <article class="metric-card">
                <span>资源覆盖率</span>
                <strong>{{ formatMetric(caseResult.resource_inventory_coverage) }}</strong>
              </article>
            </div>
            <div class="chip-bucket">
              <span v-for="resolved in caseResult.resolved_skill_ids" :key="resolved" class="chip">{{ resolved }}</span>
            </div>
          </article>
          <p v-if="!evalSummary" class="muted">点击左侧“运行评测”查看 skills 解析与资源加载指标。</p>
        </div>

        <div v-else class="content-scroll explain-column">
          <article class="result-card">
            <header>
              <strong>Skills 在 AgentHub 里是什么</strong>
            </header>
            <p>
              Skills 是一组可复用的工作方式说明，不直接等同于 MCP 或工具。它决定某个应用在某个阶段应如何组织输出、
              如何使用工具、如何引用证据，以及需要附带哪些参考资料、脚本和资产。
            </p>
          </article>
          <article class="result-card">
            <header>
              <strong>当前文件型 Skill System</strong>
            </header>
            <ul class="markdown-list">
              <li>每个技能都来自一个独立的 <code>SKILL.md</code> 目录。</li>
              <li>平台先扫描元数据，需要时再按需加载 references / scripts / assets。</li>
              <li>运行时会按 app 和 stage 解析真正生效的 skills。</li>
            </ul>
          </article>
          <article class="result-card">
            <header>
              <strong>如何验证</strong>
            </header>
            <ul class="markdown-list">
              <li>切到 <code>chat.reply</code>，应看到 <code>general_qa</code>、<code>tool_use_hygiene</code>、<code>source_grounding</code>。</li>
              <li>切到 <code>research.plan</code>，应看到 <code>research_planning</code>。</li>
              <li>切到 <code>research.report</code>，应看到 <code>source_grounding</code> 和 <code>research_synthesis</code>。</li>
              <li>运行评测，可看到 precision / recall / resource coverage。</li>
            </ul>
          </article>
        </div>
      </section>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import {
  getSkillBindings,
  listApps,
  listSkillCatalog,
  reloadSkills,
  resolveSkills,
  runSkillEval,
  type AppManifest,
  type SkillBindingsResponse,
  type SkillCatalogItem,
  type SkillEvalSummary,
  type SkillResolvedItem
} from "../services/api";

const apps = ref<AppManifest[]>([]);
const catalog = ref<SkillCatalogItem[]>([]);
const bindingInfo = ref<SkillBindingsResponse | null>(null);
const resolvedSkills = ref<SkillResolvedItem[]>([]);
const evalSummary = ref<SkillEvalSummary | null>(null);
const selectedAppId = ref("chat");
const selectedStage = ref("chat.reply");
const userId = ref("");
const activeTab = ref<"resolved" | "catalog" | "eval" | "explain">("resolved");
const loading = ref(false);
const evalLoading = ref(false);
const errorMessage = ref("");

const catalogMap = computed<Record<string, SkillCatalogItem>>(() =>
  Object.fromEntries(catalog.value.map((item) => [item.skill_id, item]))
);

const skillEnabledApps = computed(() => apps.value);

const stageOptions = computed(() => {
  const options = bindingInfo.value?.context_profiles || [];
  return options.length ? options : ["default"];
});

onMounted(async () => {
  await refreshAll();
});

watch(selectedAppId, async () => {
  await loadBindings();
  await loadResolved();
});

watch(selectedStage, async () => {
  await loadResolved();
});

async function refreshAll(): Promise<void> {
  loading.value = true;
  try {
    const [appsResult, catalogResult] = await Promise.all([listApps(), listSkillCatalog()]);
    apps.value = appsResult;
    catalog.value = catalogResult;
    if (!skillEnabledApps.value.find((item) => item.app_id === selectedAppId.value)) {
      selectedAppId.value = skillEnabledApps.value[0]?.app_id || "chat";
    }
    await loadBindings();
    await loadResolved();
    errorMessage.value = "";
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    loading.value = false;
  }
}

async function reloadCatalog(): Promise<void> {
  loading.value = true;
  try {
    await reloadSkills();
    await refreshAll();
    errorMessage.value = "";
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    loading.value = false;
  }
}

async function loadBindings(): Promise<void> {
  if (!selectedAppId.value) return;
  try {
    bindingInfo.value = await getSkillBindings(selectedAppId.value);
    if (!bindingInfo.value.context_profiles.includes(selectedStage.value)) {
      selectedStage.value = bindingInfo.value.context_profiles[0] || "default";
    }
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  }
}

async function loadResolved(): Promise<void> {
  if (!selectedAppId.value || !selectedStage.value) return;
  loading.value = true;
  try {
    resolvedSkills.value = await resolveSkills(selectedAppId.value, selectedStage.value, userId.value.trim() || undefined);
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
    evalSummary.value = await runSkillEval();
    activeTab.value = "eval";
    errorMessage.value = "";
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    evalLoading.value = false;
  }
}

function appLabel(appId: string, fallback: string): string {
  if (appId === "chat") return "聊天助手";
  if (appId === "deep_research") return "深度研究";
  if (appId === "software_engineering") return "软件工程智能体";
  return fallback;
}

function formatMetric(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "0.00";
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
</script>

<style scoped>
.skills-shell {
  grid-template-columns: minmax(300px, 340px) minmax(0, 1fr);
}

.skills-main {
  min-height: 0;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 12px;
}

.sticky-rail-head {
  position: sticky;
  top: 0;
  z-index: 2;
  background: linear-gradient(180deg, rgba(245, 249, 255, 0.98), rgba(245, 249, 255, 0.9));
}

.skills-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  padding: 16px 18px 0;
}

.skills-toolbar h1,
.skills-rail h2 {
  margin: 8px 0 0;
}

.skills-tabs {
  padding: 0 18px;
}

.skills-panel {
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  margin: 0 18px 18px;
}

.skills-panel > .content-scroll {
  min-height: 0;
  height: 100%;
  overflow: auto;
}

.inner-panel {
  display: grid;
  gap: 12px;
  padding: 12px;
}

.field-grid {
  display: grid;
  gap: 10px;
}

.field {
  display: grid;
  gap: 6px;
}

.field span {
  font-size: 0.82rem;
  color: var(--muted);
}

.field input,
.field select {
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.82);
}

.result-column,
.explain-column {
  display: grid;
  gap: 12px;
  align-content: start;
}

.result-card,
.record-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.72);
}

.record-main {
  display: grid;
  gap: 10px;
}

.section-block {
  display: grid;
  gap: 8px;
}

.section-block h4 {
  margin: 0;
  font-size: 0.95rem;
}

.resource-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.chip-bucket {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.resource-summary {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: 0.85rem;
}

.skill-description {
  margin-top: 6px;
}

.reference-stack {
  display: grid;
  gap: 8px;
}

.reference-card {
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.72);
}

.reference-preview {
  margin-top: 8px;
  line-height: 1.6;
  color: var(--ink);
  white-space: pre-wrap;
}

.path-list {
  display: grid;
  gap: 8px;
  padding-left: 18px;
}

.path-list li {
  display: grid;
  gap: 4px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}

.metric-card {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.82);
}

.metric-card span {
  color: var(--muted);
  font-size: 0.82rem;
}

.metric-card strong {
  font-size: 1.15rem;
}

.markdown-list {
  margin: 0;
  padding-left: 20px;
  line-height: 1.7;
}

@media (max-width: 1100px) {
  .skills-shell {
    grid-template-columns: 1fr;
  }
}
</style>
