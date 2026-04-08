<template>
  <section class="page-stack mcp-page">
    <header class="surface-card mcp-hero">
      <div>
        <h1>MCP 工作台 </h1>
<!--        <p class="muted">-->
<!--          直接粘贴 <span class="mono">mcp.so</span>、Claude Desktop、Cursor 常见的-->
<!--          <span class="mono">mcpServers</span> JSON 配置，动态接入本地或远程 MCP Server。-->
<!--        </p>-->
      </div>
      <div class="hero-actions">
        <span class="chip">stdio + HTTP 共存</span>
        <span class="chip">{{ backendStatusText }}</span>
        <button class="btn ghost small" type="button" @click="refreshAll">刷新</button>
      </div>
    </header>

    <div v-if="errorMessage" class="surface-card inline-banner">
      <strong>操作失败</strong>
      <p class="inline-error">{{ errorMessage }}</p>
    </div>

    <div v-if="successMessage" class="surface-card inline-banner success-banner">
      <strong>操作完成</strong>
      <p class="muted">{{ successMessage }}</p>
    </div>

    <section class="workbench-shell mcp-shell">
      <aside class="surface-card workbench-rail mcp-rail">
        <div class="tool-strip">
          <div>
            <p class="eyebrow">快速导入</p>
            <strong>粘贴 MCP JSON</strong>
          </div>
        </div>

        <div class="rail-scroll compact-stack">
          <label class="field">
            <span>允许使用的应用</span>
            <p class="muted">不选表示全应用可用（后续新增应用也可直接使用）。</p>
            <div class="app-checklist">
              <label v-for="app in apps" :key="app.app_id" class="check-chip">
                <input v-model="selectedAllowedApps" :value="app.app_id" type="checkbox" />
                <span>{{ appLabel(app.app_id, app.name) }}</span>
              </label>
            </div>
          </label>

          <label class="field">
            <span>配置 JSON</span>
            <textarea
              v-model="importText"
              class="json-editor mono"
              spellcheck="false"
              placeholder='{
  "mcpServers": {
    "amap-maps": {
      "command": "npx",
      "args": ["-y", "@amap/amap-maps-mcp-server"],
      "env": {
        "AMAP_MAPS_API_KEY": "your_api_key"
      }
    }
  }
}'
            />
          </label>

          <div class="summary-bar">
            <button class="btn ghost small" type="button" :disabled="prechecking" @click="runPrecheck">
              {{ prechecking ? "预检中..." : "预检配置" }}
            </button>
            <button class="btn primary" type="button" :disabled="importing" @click="importConfig">
              {{ importing ? "导入中..." : "导入配置" }}
            </button>
            <button class="btn ghost small" type="button" @click="loadSampleJson">填入示例</button>
          </div>

          <section v-if="precheckResults.length" class="surface-card compact-panel precheck-panel">
            <div class="tool-strip">
              <strong>配置预检</strong>
              <span class="chip">{{ precheckResults.length }} 个 server</span>
            </div>
            <div class="pane-scroll compact-stack">
              <div v-for="item in precheckResults" :key="item.server_name" class="compact-row">
                <div class="tool-strip">
                  <strong>{{ item.server_name }}</strong>
                  <span class="chip">{{ item.transport }}</span>
                  <span class="chip">{{ item.ready ? "可尝试导入" : "存在阻塞" }}</span>
                </div>
                <p class="muted mono">{{ precheckSummary(item) }}</p>
                <ul v-if="item.warnings.length" class="warning-list">
                  <li v-for="warning in item.warnings" :key="warning">{{ warning }}</li>
                </ul>
              </div>
            </div>
          </section>

          <div class="compact-row">
            <strong>Server 列表</strong>
            <p class="muted">本地 stdio 和远程 HTTP MCP server 可以共存。</p>
          </div>

          <button
            v-for="server in servers"
            :key="server.server_name"
            type="button"
            class="server-row"
            :class="{ active: server.server_name === selectedServerName }"
            @click="selectServer(server.server_name)"
          >
            <div class="server-row__main">
              <strong>{{ server.server_name }}</strong>
              <p class="muted">{{ server.description || server.transport }}</p>
            </div>
            <div class="server-row__meta">
              <span class="chip">{{ server.source === "custom" ? "自定义" : "内置" }}</span>
              <span class="chip">{{ server.enabled ? "开启" : "关闭" }}</span>
            </div>
          </button>

          <p v-if="!servers.length" class="muted">当前还没有已注册的 MCP Server。</p>
        </div>
      </aside>

      <div class="workbench-main mcp-main">
        <section class="surface-card panel mcp-status-panel">
          <div class="tool-strip">
            <div>
              <h3>Server 状态与目录</h3>
            </div>
            <div class="summary-bar">
              <label class="field inline-field">
                <span>调试应用</span>
                <select v-model="selectedAppId">
                  <option v-for="app in apps" :key="app.app_id" :value="app.app_id">
                    {{ appLabel(app.app_id, app.name) }}
                  </option>
                </select>
              </label>
              <button class="btn ghost small" type="button" :disabled="catalogLoading" @click="loadCatalog(true)">
                {{ catalogLoading ? "刷新中..." : "刷新目录" }}
              </button>
            </div>
          </div>

          <div class="content-scroll detail-stack">
            <div v-if="selectedServer" class="detail-grid">
              <div class="compact-row">
                <span class="eyebrow">连接</span>
                <strong>{{ selectedStatus?.connected ? "已连接" : "未连接" }}</strong>
                <p class="muted mono">{{ selectedServer.transport === "stdio" ? commandPreview(selectedServer) : selectedServer.url || "n/a" }}</p>
              </div>
              <div class="compact-row">
                <span class="eyebrow">允许应用</span>
                <strong>{{ selectedServer.allowed_app_ids.length ? selectedServer.allowed_app_ids.map((id) => appLabel(id, id)).join(" / ") : "全应用" }}</strong>
                <p class="muted">作用域为空表示全局可用，无需为新智能体重复导入。</p>
              </div>
              <div class="compact-row">
                <span class="eyebrow">目录统计</span>
                <strong>{{ selectedCatalog?.tools.length ?? selectedStatus?.tools_count ?? 0 }} tools / {{ selectedCatalog?.resources.length ?? selectedStatus?.resources_count ?? 0 }} resources / {{ selectedCatalog?.prompts.length ?? selectedStatus?.prompts_count ?? 0 }} prompts</strong>
                <p class="muted">{{ selectedStatus?.protocol_version || "unknown protocol" }}</p>
              </div>
            </div>

            <div v-if="selectedServer" class="summary-bar">
              <button class="btn ghost small" type="button" :disabled="updating" @click="toggleServer">
                {{ selectedServer.enabled ? "关闭 Server" : "开启 Server" }}
              </button>
              <button
                class="btn ghost small"
                type="button"
                :disabled="!selectedServer.editable || updating"
                @click="deleteSelectedServer"
              >
                删除 Server
              </button>
            </div>

            <details v-if="selectedServer" class="surface-card compact-panel scope-details">
              <summary class="tool-strip">
                <strong>应用作用域</strong>
                <span class="chip">{{ selectedServerAllowedApps.length ? `${selectedServerAllowedApps.length} 个应用` : "全应用" }}</span>
              </summary>
              <div class="app-checklist">
                <label v-for="app in apps" :key="`scope-${app.app_id}`" class="check-chip">
                  <input
                    v-model="selectedServerAllowedApps"
                    :value="app.app_id"
                    type="checkbox"
                    :disabled="!selectedServer.editable || updating"
                  />
                  <span>{{ appLabel(app.app_id, app.name) }}</span>
                </label>
              </div>
              <div class="summary-bar">
                <button class="btn ghost small" type="button" :disabled="!selectedServer.editable || updating" @click="resetAllowedApps">
                  重置
                </button>
                <button class="btn primary small" type="button" :disabled="!selectedServer.editable || updating" @click="saveAllowedApps">
                  保存作用域
                </button>
              </div>
            </details>

            <div v-if="selectedStatus?.last_error && shouldShowLastError(selectedStatus.last_error)" class="inline-banner">
              <strong>最近错误</strong>
              <p class="inline-error">{{ selectedStatus.last_error }}</p>
            </div>

            <div class="catalog-grid">
              <section class="surface-card compact-panel">
                <div class="tool-strip">
                  <strong>Tools</strong>
                  <span class="chip">{{ selectedCatalog?.tools.length ?? 0 }}</span>
                </div>
                <div class="pane-scroll compact-stack">
                  <label class="field" v-if="selectedCatalog?.tools.length">
                    <span>选择工具</span>
                    <select v-model="selectedToolName">
                      <option v-for="tool in selectedCatalog?.tools ?? []" :key="tool.name as string" :value="tool.name as string">
                        {{ tool.name as string }}
                      </option>
                    </select>
                  </label>
                  <div class="summary-bar">
                    <button class="btn ghost small" type="button" :disabled="!Object.keys(selectedToolSchema).length" @click="fillToolArgsTemplate">
                      填充参数模板
                    </button>
                  </div>
                  <p v-if="selectedToolRequired.length" class="muted mono">必填参数: {{ selectedToolRequired.join(", ") }}</p>
                  <label class="field">
                    <span>工具参数 JSON</span>
                    <textarea v-model="toolArgsText" class="json-editor mono compact-editor" spellcheck="false" />
                  </label>
                  <details v-if="Object.keys(selectedToolSchema).length" class="schema-details">
                    <summary>查看参数 Schema</summary>
                    <pre class="result-block">{{ JSON.stringify(selectedToolSchema, null, 2) }}</pre>
                  </details>
                  <button class="btn primary small" type="button" :disabled="!selectedServer || !selectedToolName || toolRunning" @click="runTool">
                    {{ toolRunning ? "调用中..." : "调用工具" }}
                  </button>
                  <pre class="result-block">{{ toolResultText || "尚未调用工具" }}</pre>
                </div>
              </section>

              <section class="surface-card compact-panel">
                <div class="tool-strip">
                  <strong>Resources</strong>
                  <span class="chip">{{ selectedCatalog?.resources.length ?? 0 }}</span>
                </div>
                <div class="pane-scroll compact-stack">
                  <label class="field" v-if="selectedCatalog?.resources.length">
                    <span>选择资源</span>
                    <select v-model="selectedResourceUri">
                      <option v-for="resource in selectedCatalog?.resources ?? []" :key="resource.uri as string" :value="resource.uri as string">
                        {{ resource.name || resource.uri }}
                      </option>
                    </select>
                  </label>
                  <button class="btn primary small" type="button" :disabled="!selectedServer || !selectedResourceUri || resourceRunning" @click="readResource">
                    {{ resourceRunning ? "读取中..." : "读取资源" }}
                  </button>
                  <pre class="result-block">{{ resourceResultText || "尚未读取资源" }}</pre>
                </div>
              </section>

              <section class="surface-card compact-panel">
                <div class="tool-strip">
                  <strong>Prompts</strong>
                  <span class="chip">{{ selectedCatalog?.prompts.length ?? 0 }}</span>
                </div>
                <div class="pane-scroll compact-stack">
                  <label class="field" v-if="selectedCatalog?.prompts.length">
                    <span>选择 Prompt</span>
                    <select v-model="selectedPromptName">
                      <option v-for="prompt in selectedCatalog?.prompts ?? []" :key="prompt.name as string" :value="prompt.name as string">
                        {{ prompt.name as string }}
                      </option>
                    </select>
                  </label>
                  <label class="field">
                    <span>Prompt 参数 JSON</span>
                    <textarea v-model="promptArgsText" class="json-editor mono compact-editor" spellcheck="false" />
                  </label>
                  <button class="btn primary small" type="button" :disabled="!selectedServer || !selectedPromptName || promptRunning" @click="renderPrompt">
                    {{ promptRunning ? "获取中..." : "获取 Prompt" }}
                  </button>
                  <pre class="result-block">{{ promptResultText || "尚未获取 Prompt" }}</pre>
                </div>
              </section>
            </div>
          </div>
        </section>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import {
  callMcpTool,
  deleteMcpServer,
  getMcpCatalog,
  getMcpStatus,
  getMcpPrompt,
  importMcpServers,
  listApps,
  listMcpServers,
  precheckMcpServers,
  readMcpResource,
  updateMcpServer,
  type AppManifest,
  type MCPCatalogEntry,
  type MCPCatalogResponse,
  type MCPPrecheckResult,
  type MCPServerSummary,
  type MCPStatusServer
} from "../services/api";

const apps = ref<AppManifest[]>([]);
const servers = ref<MCPServerSummary[]>([]);
const statusServers = ref<MCPStatusServer[]>([]);
const selectedServerName = ref("");
const selectedAppId = ref("chat");
const selectedAllowedApps = ref<string[]>([]);
const selectedServerAllowedApps = ref<string[]>([]);
const importText = ref("");

const catalog = ref<MCPCatalogResponse | null>(null);
const precheckResults = ref<MCPPrecheckResult[]>([]);
const importing = ref(false);
const updating = ref(false);
const catalogLoading = ref(false);
const prechecking = ref(false);
const toolRunning = ref(false);
const resourceRunning = ref(false);
const promptRunning = ref(false);

const selectedToolName = ref("");
const selectedResourceUri = ref("");
const selectedPromptName = ref("");
const toolArgsText = ref("{}");
const promptArgsText = ref("{}");
const toolResultText = ref("");
const resourceResultText = ref("");
const promptResultText = ref("");
const errorMessage = ref("");
const successMessage = ref("");
const backendEnabled = ref<boolean | null>(null);
const backendStatusText = computed(() => {
  if (backendEnabled.value === true) return "已启用 MCP";
  if (backendEnabled.value === false) return "MCP 未启用";
  return "MCP 状态未知";
});

const selectedServer = computed(() => servers.value.find((item) => item.server_name === selectedServerName.value) || null);
const selectedStatus = computed(() => statusServers.value.find((item) => item.server_name === selectedServerName.value) || null);
const selectedCatalog = computed<MCPCatalogEntry | null>(() => {
  if (!catalog.value || !selectedServerName.value) return null;
  return catalog.value.catalog[selectedServerName.value] || null;
});
const selectedToolSchema = computed<Record<string, unknown>>(() => {
  const tools = (selectedCatalog.value?.tools || []) as Array<Record<string, unknown>>;
  const tool = tools.find((item) => String(item.name || "") === selectedToolName.value);
  if (!tool) return {};
  const schema = tool.input_schema ?? tool.inputSchema ?? {};
  return schema && typeof schema === "object" && !Array.isArray(schema) ? (schema as Record<string, unknown>) : {};
});
const selectedToolRequired = computed<string[]>(() => toStringArray(selectedToolSchema.value.required));

onMounted(async () => {
  await refreshAll();
});

watch(selectedServerName, () => {
  const tools = (selectedCatalog.value?.tools || []) as Array<Record<string, unknown>>;
  const resources = (selectedCatalog.value?.resources || []) as Array<Record<string, unknown>>;
  const prompts = (selectedCatalog.value?.prompts || []) as Array<Record<string, unknown>>;
  selectedToolName.value = String(tools[0]?.name || "");
  selectedResourceUri.value = String(resources[0]?.uri || "");
  selectedPromptName.value = String(prompts[0]?.name || "");
});

watch(selectedServer, (server) => {
  selectedServerAllowedApps.value = server ? [...server.allowed_app_ids] : [];
});

watch(selectedAppId, async () => {
  await loadCatalog(false);
});

watch(selectedCatalog, (entry) => {
  const tools = (entry?.tools || []) as Array<Record<string, unknown>>;
  const resources = (entry?.resources || []) as Array<Record<string, unknown>>;
  const prompts = (entry?.prompts || []) as Array<Record<string, unknown>>;
  selectedToolName.value = String(tools[0]?.name || "");
  selectedResourceUri.value = String(resources[0]?.uri || "");
  selectedPromptName.value = String(prompts[0]?.name || "");
  if (!toolArgsText.value.trim() || toolArgsText.value.trim() === "{}") {
    fillToolArgsTemplate();
  }
});

watch(selectedToolName, () => {
  fillToolArgsTemplate();
});

async function refreshAll(): Promise<void> {
  errorMessage.value = "";
  successMessage.value = "";
  backendEnabled.value = null;
  try {
    const [appsResult, serversResult, statusResult] = await Promise.all([
      listApps(),
      listMcpServers(),
      getMcpStatus()
    ]);
    apps.value = appsResult;
    servers.value = serversResult;
    statusServers.value = statusResult.servers;
    backendEnabled.value = statusResult.enabled;
    if (!selectedServerName.value || !servers.value.find((item) => item.server_name === selectedServerName.value)) {
      selectedServerName.value = servers.value[0]?.server_name || "";
    }
    if (!apps.value.find((item) => item.app_id === selectedAppId.value)) {
      selectedAppId.value = apps.value[0]?.app_id || "chat";
    }
    await loadCatalog(false);
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  }
}

async function loadCatalog(refresh: boolean): Promise<void> {
  if (!selectedAppId.value) return;
  catalogLoading.value = true;
  try {
    catalog.value = await getMcpCatalog(selectedAppId.value, refresh);
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    catalogLoading.value = false;
  }
}

function selectServer(serverName: string): void {
  selectedServerName.value = serverName;
}

async function importConfig(): Promise<void> {
  if (!importText.value.trim()) {
    errorMessage.value = "请先粘贴 MCP 配置 JSON。";
    return;
  }
  importing.value = true;
  errorMessage.value = "";
  try {
    const result = await importMcpServers({
      config_text: importText.value,
      allowed_app_ids: selectedAllowedApps.value,
      enabled: true
    });
    const scopeLabel = selectedAllowedApps.value.length ? selectedAllowedApps.value.map((id) => appLabel(id, id)).join(" / ") : "全应用";
    successMessage.value = `已导入 ${result.imported.map((item) => item.server_name).join("、")}（作用域：${scopeLabel}）。`;
    importText.value = "";
    await refreshAll();
    if (result.imported[0]) {
      selectedServerName.value = result.imported[0].server_name;
    }
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    importing.value = false;
  }
}

function loadSampleJson(): void {
  importText.value = JSON.stringify(
    {
      mcpServers: {
        "amap-maps": {
          command: "npx",
          args: ["-y", "@amap/amap-maps-mcp-server"],
          env: {
            AMAP_MAPS_API_KEY: "your_api_key"
          }
        }
      }
    },
    null,
    2
  );
}

async function runPrecheck(): Promise<void> {
  if (!importText.value.trim()) {
    errorMessage.value = "请先粘贴 MCP 配置 JSON。";
    return;
  }
  prechecking.value = true;
  errorMessage.value = "";
  try {
    const result = await precheckMcpServers({ config_text: importText.value });
    precheckResults.value = result.results;
    successMessage.value = `预检完成：${result.results.map((item) => item.server_name).join("、")}`;
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    prechecking.value = false;
  }
}

async function toggleServer(): Promise<void> {
  if (!selectedServer.value) return;
  updating.value = true;
  errorMessage.value = "";
  try {
    const updated = await updateMcpServer(selectedServer.value.server_name, {
      enabled: !selectedServer.value.enabled
    });
    successMessage.value = `${updated.server_name} 已${updated.enabled ? "开启" : "关闭"}。`;
    await refreshAll();
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    updating.value = false;
  }
}

function resetAllowedApps(): void {
  selectedServerAllowedApps.value = selectedServer.value ? [...selectedServer.value.allowed_app_ids] : [];
}

async function saveAllowedApps(): Promise<void> {
  if (!selectedServer.value?.editable) return;
  updating.value = true;
  errorMessage.value = "";
  try {
    const updated = await updateMcpServer(selectedServer.value.server_name, {
      allowed_app_ids: selectedServerAllowedApps.value
    });
    const scopeLabel = updated.allowed_app_ids.length ? updated.allowed_app_ids.map((id) => appLabel(id, id)).join(" / ") : "全应用";
    successMessage.value = `${updated.server_name} 作用域已更新：${scopeLabel}。`;
    await refreshAll();
    selectedServerName.value = updated.server_name;
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    updating.value = false;
  }
}

async function deleteSelectedServer(): Promise<void> {
  if (!selectedServer.value?.editable) return;
  updating.value = true;
  errorMessage.value = "";
  try {
    await deleteMcpServer(selectedServer.value.server_name);
    successMessage.value = `${selectedServer.value.server_name} 已删除。`;
    selectedServerName.value = "";
    await refreshAll();
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    updating.value = false;
  }
}

async function runTool(): Promise<void> {
  if (!selectedServer.value || !selectedToolName.value) return;
  toolRunning.value = true;
  errorMessage.value = "";
  try {
    const parsed = parseJsonObject(toolArgsText.value);
    const normalizedArgs = coerceArgumentsBySchema(parsed, selectedToolSchema.value);
    const result = await callMcpTool({
      app_id: selectedAppId.value,
      server_name: selectedServer.value.server_name,
      tool_name: selectedToolName.value,
      arguments: normalizedArgs
    });
    toolResultText.value = JSON.stringify(result, null, 2);
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    toolRunning.value = false;
  }
}

function fillToolArgsTemplate(): void {
  const template = buildArgsTemplate(selectedToolSchema.value);
  toolArgsText.value = JSON.stringify(template, null, 2);
}

async function readResource(): Promise<void> {
  if (!selectedServer.value || !selectedResourceUri.value) return;
  resourceRunning.value = true;
  errorMessage.value = "";
  try {
    const result = await readMcpResource({
      app_id: selectedAppId.value,
      server_name: selectedServer.value.server_name,
      uri: selectedResourceUri.value
    });
    resourceResultText.value = JSON.stringify(result, null, 2);
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    resourceRunning.value = false;
  }
}

async function renderPrompt(): Promise<void> {
  if (!selectedServer.value) return;
  const prompts = (selectedCatalog.value?.prompts || []) as Array<Record<string, unknown>>;
  if (!prompts.length) {
    errorMessage.value = "当前 MCP Server 未提供 prompts（这类 server 只能用 tools）。";
    return;
  }
  if (!selectedPromptName.value) {
    errorMessage.value = "请先选择 Prompt。";
    return;
  }
  promptRunning.value = true;
  errorMessage.value = "";
  try {
    const parsed = parseJsonObject(promptArgsText.value);
    const result = await getMcpPrompt({
      app_id: selectedAppId.value,
      server_name: selectedServer.value.server_name,
      prompt_name: selectedPromptName.value,
      arguments: parsed
    });
    promptResultText.value = JSON.stringify(result, null, 2);
  } catch (error) {
    errorMessage.value = getErrorMessage(error);
  } finally {
    promptRunning.value = false;
  }
}

function parseJsonObject(text: string): Record<string, unknown> {
  const trimmed = text.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("请输入 JSON 对象，例如 {}。");
  }
  return parsed as Record<string, unknown>;
}

function buildArgsTemplate(schema: Record<string, unknown>): Record<string, unknown> {
  const properties = toRecord(schema.properties);
  const required = new Set(toStringArray(schema.required));
  const result: Record<string, unknown> = {};
  if (!Object.keys(properties).length) return {};
  for (const [name, specValue] of Object.entries(properties)) {
    const spec = toRecord(specValue);
    if (required.has(name)) {
      result[name] = defaultValueForSpec(spec, name);
    }
  }
  if (!Object.keys(result).length) {
    for (const [name, specValue] of Object.entries(properties)) {
      const spec = toRecord(specValue);
      result[name] = defaultValueForSpec(spec, name);
      if (Object.keys(result).length >= 3) break;
    }
  }
  return result;
}

function coerceArgumentsBySchema(
  args: Record<string, unknown>,
  schema: Record<string, unknown>
): Record<string, unknown> {
  const properties = toRecord(schema.properties);
  const required = new Set(toStringArray(schema.required));
  const normalized: Record<string, unknown> = { ...args };
  for (const [name, specValue] of Object.entries(properties)) {
    if (!(name in normalized)) continue;
    const spec = toRecord(specValue);
    normalized[name] = coerceValueBySpec(normalized[name], spec);
    if (required.has(name) && (normalized[name] === "" || normalized[name] == null)) {
      normalized[name] = defaultValueForSpec(spec, name);
    }
  }
  for (const [name, specValue] of Object.entries(properties)) {
    if (!required.has(name)) continue;
    if (!(name in normalized)) {
      normalized[name] = defaultValueForSpec(toRecord(specValue), name);
    }
  }
  return normalized;
}

function coerceValueBySpec(value: unknown, spec: Record<string, unknown>): unknown {
  const rawType = spec.type;
  const type = Array.isArray(rawType) ? String(rawType[0] || "string") : String(rawType || "string");
  if (type === "boolean") {
    if (typeof value === "boolean") return value;
    if (typeof value === "string") {
      const lowered = value.trim().toLowerCase();
      if (lowered === "true" || lowered === "1") return true;
      if (lowered === "false" || lowered === "0") return false;
    }
    return value;
  }
  if (type === "integer" || type === "number") {
    if (typeof value === "number") return value;
    if (typeof value === "string") {
      const parsed = type === "integer" ? Number.parseInt(value, 10) : Number.parseFloat(value);
      if (!Number.isNaN(parsed)) return parsed;
    }
    return value;
  }
  if (type === "object") {
    if (value && typeof value === "object" && !Array.isArray(value)) return value;
    if (typeof value === "string") {
      try {
        const parsed = JSON.parse(value);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
      } catch {
        return value;
      }
    }
    return value;
  }
  if (type === "array") {
    if (Array.isArray(value)) return value;
    if (typeof value === "string") {
      try {
        const parsed = JSON.parse(value);
        if (Array.isArray(parsed)) return parsed;
      } catch {
        const split = value
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        if (split.length) return split;
      }
    }
    return value;
  }
  return value;
}

function defaultValueForSpec(spec: Record<string, unknown>, fieldName = ""): unknown {
  if ("default" in spec) return spec.default;
  const enumValues = Array.isArray(spec.enum) ? spec.enum : [];
  if (enumValues.length) return enumValues[0];
  const rawType = spec.type;
  const type = Array.isArray(rawType) ? String(rawType[0] || "string") : String(rawType || "string");
  if (type === "boolean") return false;
  if (type === "integer" || type === "number") return 0;
  if (type === "array") return [];
  if (type === "object") return {};
  const name = fieldName.toLowerCase();
  if (name.includes("city") || name.includes("adcode")) return "110000";
  if (name.includes("origin") || name.includes("destination") || name.includes("location") || name.includes("lnglat")) return "116.397428,39.90923";
  if (name.includes("keyword")) return "餐厅";
  if (name.includes("query")) return "北京";
  return "example";
}

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item)).filter(Boolean);
}

function appLabel(appId: string, fallback: string): string {
  if (appId === "chat") return "聊天助手";
  if (appId === "deep_research") return "深度研究";
  if (appId === "software_engineering") return "软件工程";
  return fallback;
}

function commandPreview(server: MCPServerSummary): string {
  return [server.command, ...server.args].filter(Boolean).join(" ").trim() || "n/a";
}

function precheckSummary(item: MCPPrecheckResult): string {
  if (item.transport === "stdio") {
    const command = String(item.checks.command || "");
    const resolved = String(item.checks.resolved_command || "");
    const moduleName = String(item.checks.module_name || "");
    if (moduleName) {
      return `${command} -m ${moduleName} | 已解析: ${resolved || "未找到"} | 模块安装: ${item.checks.module_installed ? "是" : "否"}`;
    }
    return `${command || "未提供命令"} | 已解析: ${resolved || "未找到"}`;
  }
  const url = String(item.checks.url || "");
  const status = item.checks.probe_status_code ?? "n/a";
  return `${url || "未提供 URL"} | 预检状态: ${status}`;
}

function shouldShowLastError(message: string): boolean {
  return !message.includes("Method not found");
}

function getErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return String(error);
  const raw = String(error.message || "").trim();
  if (!raw) return "未知错误";
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      return String((parsed as Record<string, unknown>).detail || raw);
    }
  } catch {
    const detailMatch = raw.match(/"detail"\s*:\s*"([^"]+)"/);
    if (detailMatch) return detailMatch[1];
  }
  return raw;
}
</script>

<style scoped>
.mcp-page {
  grid-template-rows: auto auto auto minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
}

.mcp-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: start;
  padding: 16px 18px;
  height: 10%;
}

.mcp-hero h1 {
  margin: 8px 0 6px;
  font-size: 1.35rem;
}

.hero-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.success-banner {
  border-color: rgba(31, 122, 100, 0.18);
  background: rgba(249, 255, 252, 0.92);
}

.precheck-panel {
  padding: 12px;
}

.mcp-shell {
  grid-template-columns: 360px minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
}

.mcp-rail,
.mcp-main,
.mcp-status-panel,
.detail-stack,
.catalog-grid,
.compact-panel {
  min-height: 0;
}

.mcp-main {
  display: grid;
  min-height: 0;
  overflow: hidden;
}

.mcp-status-panel {
  padding: 10px 12px;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
}

.field {
  display: grid;
  gap: 8px;
}

.field span {
  font-size: 0.85rem;
  color: var(--muted);
}

.inline-field {
  grid-template-columns: auto 180px;
  align-items: center;
}

.json-editor {
  min-height: 220px;
  resize: vertical;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.88);
}

.compact-editor {
  min-height: 84px;
}

.app-checklist {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.check-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.72);
}

.server-row {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.72);
  text-align: left;
}

.server-row.active {
  border-color: rgba(76, 134, 255, 0.32);
  background: rgba(240, 247, 255, 0.96);
}

.server-row__main,
.server-row__meta {
  min-width: 0;
}

.server-row__main p {
  margin: 4px 0 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.server-row__meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.detail-stack {
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  align-content: start;
  gap: 10px;
  min-height: 0;
  overflow: hidden;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.detail-grid .compact-row {
  padding: 8px 10px;
}

.catalog-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}

.compact-panel {
  padding: 10px;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 8px;
  min-height: 0;
  overflow: hidden;
}

.result-block {
  margin: 0;
  min-height: 220px;
  max-height: 420px;
  overflow: auto;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.82);
  white-space: pre-wrap;
}

.scope-details > summary {
  cursor: pointer;
  list-style: none;
}

.scope-details > summary::-webkit-details-marker {
  display: none;
}

.schema-details {
  display: grid;
  gap: 8px;
}

.schema-details summary {
  cursor: pointer;
  color: var(--muted);
}

.warning-list {
  margin: 0;
  padding-left: 18px;
  color: var(--warning);
}

@media (max-width: 1200px) {
  .mcp-shell,
  .detail-grid,
  .catalog-grid {
    grid-template-columns: 1fr;
  }
}
</style>
