<template>
  <section class="workbench-shell se-shell" :style="shellStyle">
    <aside class="surface-card workbench-rail" :class="{ collapsed: leftCollapsed }">
      <div class="tool-strip">
        <button class="icon-btn" type="button" @click="leftCollapsed = !leftCollapsed">
          {{ leftCollapsed ? ">" : "<" }}
        </button>
        <button v-if="!leftCollapsed" class="btn primary small" type="button" @click="createFreshRun">新任务</button>
      </div>
      <template v-if="!leftCollapsed">
        <div class="tool-strip">
          <div>
            <p class="eyebrow">任务历史</p>
            <h2>Software Engineering Runs</h2>
          </div>
          <button class="btn ghost small" type="button" @click="refreshRuns">刷新</button>
        </div>
        <div class="rail-scroll compact-stack">
          <button
            v-for="run in runs"
            :key="run.session_id"
            type="button"
            class="compact-row run-row"
            :class="{ active: run.session_id === currentSessionId }"
            @click="openRun(run.session_id)"
          >
            <strong>{{ run.goal || run.session_id }}</strong>
            <p>{{ run.final_preview || run.status }}</p>
            <span class="muted">{{ formatTimestamp(run.updated_at) }}</span>
          </button>
          <p v-if="!runs.length" class="muted">暂无历史任务</p>
        </div>
      </template>
    </aside>

    <section class="surface-card workbench-main se-main">
      <header class="tool-strip main-head">
        <div>
          <p class="eyebrow">旗舰应用</p>
          <h1>Software Engineering Agent</h1>
        </div>
        <div class="summary-bar">
          <span class="chip mono">{{ currentSessionId || "未创建会话" }}</span>
          <span class="chip">{{ running ? "运行中" : currentRun.status }}</span>
          <button class="btn ghost small" type="button" @click="rightCollapsed = !rightCollapsed">
            {{ rightCollapsed ? "显示侧栏" : "隐藏侧栏" }}
          </button>
        </div>
      </header>

      <form class="se-control" @submit.prevent="submitTask">
        <label class="field">
          <span>任务模式</span>
          <select v-model="mode" :disabled="running">
            <option value="requirement_to_code">Requirement-to-Code</option>
            <option value="feedback_to_fix">Feedback-to-Fix</option>
          </select>
        </label>

        <label class="field se-task">
          <span>任务描述</span>
          <textarea
            v-model="taskInput"
            rows="3"
            placeholder="例如：修复当前 failing test，不允许修改测试文件"
            :disabled="running"
          ></textarea>
        </label>

        <label class="field">
          <span>Verify Command</span>
          <input
            v-model="verifyCommand"
            type="text"
            placeholder="留空时自动选择（需求任务默认 compileall，修复任务默认 unittest）"
            :disabled="running"
          />
        </label>

        <label class="field">
          <span>User ID</span>
          <input v-model="userId" type="text" placeholder="se-user-001" :disabled="running" />
        </label>

        <div class="constraint-grid">
          <label><input v-model="allowModifyTests" type="checkbox" :disabled="running" />允许修改测试</label>
          <label><input v-model="allowInstallDependency" type="checkbox" :disabled="running" />允许安装依赖</label>
          <label><input v-model="allowNetwork" type="checkbox" :disabled="running" />允许联网</label>
          <label>
            最大轮次
            <input v-model.number="maxIterations" type="number" min="1" max="12" :disabled="running" />
          </label>
        </div>

        <div class="summary-bar">
          <button class="btn primary" type="submit" :disabled="running || !taskInput.trim()">开始执行</button>
          <button class="btn ghost" type="button" :disabled="!running" @click="cancelRun">停止</button>
        </div>
      </form>

      <section class="surface-tabs">
        <button class="tab-btn" :class="{ active: activeTab === 'trace' }" type="button" @click="activeTab = 'trace'">中间过程</button>
        <button class="tab-btn" :class="{ active: activeTab === 'patches' }" type="button" @click="activeTab = 'patches'">Patch / Diff</button>
        <button class="tab-btn" :class="{ active: activeTab === 'final-code' }" type="button" @click="activeTab = 'final-code'">最终代码</button>
        <button class="tab-btn" :class="{ active: activeTab === 'logs' }" type="button" @click="activeTab = 'logs'">执行日志</button>
        <button class="tab-btn" :class="{ active: activeTab === 'report' }" type="button" @click="activeTab = 'report'">最终报告</button>
      </section>

      <section class="surface-card workbench-panel tab-panel">
        <div v-if="activeTab === 'trace'" class="content-scroll">
          <ul class="event-list">
            <li v-for="(event, index) in currentRun.events" :key="`event-${index}`">
              <span class="event-type">{{ event.type }}</span>
              <span>{{ describeEvent(event) }}</span>
            </li>
            <li v-if="!currentRun.events.length" class="muted">暂无过程事件</li>
          </ul>
        </div>

        <div v-else-if="activeTab === 'patches'" class="content-scroll">
          <div v-if="!currentRun.patches.length">
            <p class="muted">暂无 patch 记录</p>
          </div>
          <div class="compact-stack">
            <article v-for="(patch, index) in currentRun.patches" :key="`patch-${index}`" class="compact-row patch-row">
              <strong>{{ patch.path }}</strong>
              <p>{{ patch.summary || patch.mode }}</p>
              <pre class="command-block">{{ patch.diff_preview }}</pre>
            </article>
          </div>
        </div>

        <div v-else-if="activeTab === 'final-code'" class="content-scroll">
          <div v-if="!currentRun.final_code_files?.length">
            <p class="muted">暂无最终代码文件（可能本次未写入 patch）</p>
          </div>
          <div class="compact-stack">
            <article v-for="(file, index) in currentRun.final_code_files || []" :key="`final-file-${index}`" class="compact-row patch-row">
              <strong>{{ file.path }}</strong>
              <pre class="command-block">{{ file.content }}</pre>
            </article>
          </div>
        </div>

        <div v-else-if="activeTab === 'logs'" class="content-scroll">
          <div class="compact-stack">
            <article v-for="(record, index) in currentRun.executions" :key="`log-${index}`" class="compact-row">
              <strong>{{ record.command }}</strong>
              <p>exit={{ record.exit_code }} · {{ record.duration_seconds }}s</p>
              <pre class="command-block">{{ truncate(record.stdout || "", 1200) }}</pre>
              <pre class="command-block">{{ truncate(record.stderr || "", 1200) }}</pre>
            </article>
            <p v-if="!currentRun.executions.length" class="muted">暂无执行日志</p>
          </div>
        </div>

        <div v-else class="content-scroll report-scroll">
          <MarkdownContent :source="currentRun.final_report || '任务完成后会在这里显示最终报告'" />
        </div>
      </section>
    </section>

    <aside v-if="!rightCollapsed" class="surface-card workbench-inspector se-inspector">
      <div class="tool-strip">
        <div>
          <p class="eyebrow">Inspector</p>
          <h2>运行信息</h2>
        </div>
        <button class="icon-btn" type="button" @click="rightCollapsed = true">×</button>
      </div>
      <div class="pane-scroll compact-stack">
        <div class="compact-row">
          <strong>状态</strong>
          <p>{{ currentRun.status }}</p>
        </div>
        <div class="compact-row">
          <strong>轮次</strong>
          <p>{{ currentRun.iteration_count }}</p>
        </div>
        <div class="compact-row">
          <strong>约束</strong>
          <pre class="command-block">{{ JSON.stringify(currentRun.constraints || {}, null, 2) }}</pre>
        </div>
      </div>
    </aside>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import MarkdownContent from "../components/MarkdownContent.vue";
import {
  getSERun,
  listSERuns,
  streamSoftwareEngineering,
  type RunEvent,
  type SEFinalCodeFile,
  type SERunRecord,
  type SERunSummary,
  type SEDiagnosisRecord,
  type SEExecutionRecord,
  type SEPatchRecord,
  type SETraceRecord
} from "../services/api";

const route = useRoute();
const router = useRouter();

const mode = ref<"requirement_to_code" | "feedback_to_fix">("requirement_to_code");
const runs = ref<SERunSummary[]>([]);
const currentSessionId = ref("");
const currentRun = ref<SERunRecord>(blankRun("", "", "requirement_to_code"));
const taskInput = ref("");
const verifyCommand = ref("");
const userId = ref("se-user-001");
const allowModifyTests = ref(false);
const allowInstallDependency = ref(false);
const allowNetwork = ref(false);
const maxIterations = ref(4);
const running = ref(false);
const leftCollapsed = ref(false);
const rightCollapsed = ref(false);
const activeTab = ref<"trace" | "patches" | "final-code" | "logs" | "report">("trace");

let streamAbortController: AbortController | null = null;

const shellStyle = computed(() => ({
  gridTemplateColumns: `${leftCollapsed.value ? "72px" : "260px"} minmax(0,1fr) ${rightCollapsed.value ? "0px" : "320px"}`
}));

onMounted(async () => {
  await refreshRuns();
  const routeSession = typeof route.params.sessionId === "string" ? route.params.sessionId : "";
  if (routeSession) {
    await openRun(routeSession);
  } else {
    await createFreshRun();
  }
});

onBeforeUnmount(() => {
  streamAbortController?.abort();
});

async function refreshRuns(): Promise<void> {
  runs.value = await listSERuns(40);
}

async function openRun(sessionId: string): Promise<void> {
  currentSessionId.value = sessionId;
  await router.replace({ name: "software-engineering", params: { sessionId } });
  currentRun.value = normalizeRun(await getSERun(sessionId));
}

async function createFreshRun(): Promise<void> {
  streamAbortController?.abort();
  const sessionId = createSessionId("se");
  currentSessionId.value = sessionId;
  currentRun.value = blankRun(sessionId, "", mode.value);
  await router.replace({ name: "software-engineering", params: { sessionId } });
}

async function submitTask(): Promise<void> {
  if (running.value || !taskInput.value.trim()) return;
  if (!currentSessionId.value) await createFreshRun();
  running.value = true;
  streamAbortController?.abort();
  streamAbortController = new AbortController();
  currentRun.value = blankRun(currentSessionId.value, taskInput.value.trim(), mode.value);
  try {
    await streamSoftwareEngineering(
      {
        session_id: currentSessionId.value,
        task: taskInput.value.trim(),
        mode: mode.value,
        user_id: userId.value || undefined,
        verify_command: verifyCommand.value || undefined,
        allow_modify_tests: allowModifyTests.value,
        allow_install_dependency: allowInstallDependency.value,
        max_iterations: maxIterations.value,
        allow_network: allowNetwork.value
      },
      handleStreamEvent,
      { signal: streamAbortController.signal }
    );
  } finally {
    running.value = false;
    await refreshRuns();
    await openRun(currentSessionId.value);
  }
}

function handleStreamEvent(event: RunEvent): void {
  const run = currentRun.value;
  run.events.push(structuredCloneFallback(event));
  if (event.type === "tool_result" && event.tool_name === "patch_write_tool") {
    const result = ensureRecord(event.result);
    const applied = Array.isArray(result.applied) ? result.applied : [];
    for (const item of applied) {
      if (!item || typeof item !== "object") continue;
      run.patches.push({
        path: stringValue((item as Record<string, unknown>).path),
        mode: stringValue((item as Record<string, unknown>).mode),
        summary: stringValue((item as Record<string, unknown>).summary),
        diff_preview: stringValue((item as Record<string, unknown>).diff_preview)
      });
    }
  }
  if (event.type === "tool_result" && event.tool_name === "command_run_tool") {
    const result = ensureRecord(event.result);
    run.executions.push({
      command: stringValue(result.command),
      exit_code: Number(result.exit_code || -1),
      duration_seconds: Number(result.duration_seconds || 0),
      stdout: stringValue(result.stdout),
      stderr: stringValue(result.stderr)
    });
  }
  if (event.type === "message_done") {
    run.status = stringValue(event.status) || run.status;
    run.final_result = stringValue(event.final_result);
    run.final_report = stringValue(event.final_report);
    run.final_code_files = normalizeFinalCodeFiles(event.final_code_files);
    run.iteration_count = Number(event.iteration_count || run.iteration_count);
  }
}

function cancelRun(): void {
  streamAbortController?.abort();
  running.value = false;
}

function describeEvent(event: RunEvent): string {
  if (event.type === "status") return `${stringValue(event.agent)} · ${stringValue(event.state)} · ${stringValue(event.message)}`;
  if (event.type === "tool_call") return `${stringValue(event.tool_name)} ${safeJson(event.arguments)}`;
  if (event.type === "tool_result") return truncate(safeJson(event.result), 220);
  if (event.type === "error") return stringValue(event.message);
  if (event.type === "done") return `完成，状态：${stringValue(event.status)}`;
  return truncate(safeJson(event), 220);
}

function blankRun(
  sessionId: string,
  goal = "",
  runMode: "requirement_to_code" | "feedback_to_fix" = "requirement_to_code"
): SERunRecord {
  const now = new Date().toISOString();
  return {
    session_id: sessionId,
    app_id: "software_engineering",
    mode: runMode,
    goal,
    status: "draft",
    constraints: {},
    plan: {},
    patches: [],
    executions: [],
    diagnoses: [],
    trace: [],
    events: [],
    final_code_files: [],
    iteration_count: 0,
    final_result: "",
    final_report: "",
    created_at: now,
    updated_at: now
  };
}

function normalizeRun(run: SERunRecord): SERunRecord {
  return {
    ...run,
    constraints: run.constraints || {},
    plan: run.plan || {},
    patches: normalizePatches(run.patches),
    executions: normalizeExecutions(run.executions),
    diagnoses: normalizeDiagnoses(run.diagnoses),
    trace: normalizeTrace(run.trace),
    events: Array.isArray(run.events) ? run.events : [],
    final_code_files: normalizeFinalCodeFiles(run.final_code_files)
  };
}

function normalizePatches(input: unknown): SEPatchRecord[] {
  if (!Array.isArray(input)) return [];
  return input
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const record = item as Record<string, unknown>;
      return {
        path: stringValue(record.path),
        mode: stringValue(record.mode),
        summary: stringValue(record.summary),
        diff_preview: stringValue(record.diff_preview)
      };
    });
}

function normalizeExecutions(input: unknown): SEExecutionRecord[] {
  if (!Array.isArray(input)) return [];
  return input
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const record = item as Record<string, unknown>;
      return {
        command: stringValue(record.command),
        exit_code: Number(record.exit_code || -1),
        duration_seconds: Number(record.duration_seconds || 0),
        stdout: stringValue(record.stdout),
        stderr: stringValue(record.stderr),
        iteration: Number(record.iteration || 0),
        installed_dependencies: Array.isArray(record.installed_dependencies)
          ? record.installed_dependencies.map((value) => stringValue(value))
          : [],
        timestamp: stringValue(record.timestamp)
      };
    });
}

function normalizeDiagnoses(input: unknown): SEDiagnosisRecord[] {
  if (!Array.isArray(input)) return [];
  return input
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const record = item as Record<string, unknown>;
      return {
        next_state: stringValue(record.next_state),
        reason: stringValue(record.reason),
        failure_type: stringValue(record.failure_type),
        proposed_action: stringValue(record.proposed_action)
      };
    });
}

function normalizeTrace(input: unknown): SETraceRecord[] {
  if (!Array.isArray(input)) return [];
  return input
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const record = item as Record<string, unknown>;
      return {
        iteration: Number(record.iteration || 0),
        state: stringValue(record.state),
        agent: stringValue(record.agent),
        summary: stringValue(record.summary)
      };
    });
}

function normalizeFinalCodeFiles(input: unknown): SEFinalCodeFile[] {
  if (!Array.isArray(input)) return [];
  return input
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const record = item as Record<string, unknown>;
      return {
        path: stringValue(record.path),
        content: stringValue(record.content)
      };
    })
    .filter((item) => item.path);
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
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function ensureRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
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
</script>

<style scoped>
.se-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.main-head,
.se-control {
  padding: 12px 14px;
  border-bottom: 1px solid rgba(76, 134, 255, 0.12);
}

.main-head h1 {
  margin: 6px 0 0;
  font-size: 1rem;
}

.se-control {
  display: grid;
  gap: 10px;
  grid-template-columns: 200px minmax(0, 1fr) 260px 220px;
  align-items: end;
}

.se-task {
  grid-column: span 1;
}

.field {
  display: grid;
  gap: 6px;
}

.field span {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.field input,
.field textarea,
.field select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.84);
}

.constraint-grid {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.constraint-grid label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
}

.run-row.active {
  border-color: rgba(76, 134, 255, 0.35);
  background: rgba(232, 242, 255, 0.92);
}

.tab-panel {
  flex: 1;
  min-height: 0;
  padding: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
}

.tab-panel .content-scroll {
  min-height: 0;
  overflow: auto;
  padding: 12px;
  display: grid;
  gap: 10px;
}

.event-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.event-list li {
  border: 1px solid rgba(76, 134, 255, 0.14);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.74);
  padding: 10px 12px;
}

.event-type {
  display: inline-flex;
  margin-right: 8px;
  border-radius: 999px;
  background: rgba(232, 242, 255, 0.92);
  color: var(--accent-strong);
  font-size: 0.78rem;
  padding: 4px 8px;
}

.patch-row .command-block {
  max-height: 180px;
  overflow: auto;
}

.se-inspector {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 12px;
  gap: 10px;
}

.se-inspector .pane-scroll {
  min-height: 0;
  overflow: auto;
}

@media (max-width: 1400px) {
  .se-control {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 980px) {
  .se-shell {
    grid-template-columns: 1fr !important;
    height: auto;
  }
}
</style>
