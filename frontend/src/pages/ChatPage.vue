<template>
  <section class="workbench-shell chat-shell" :style="chatShellStyle">
    <aside class="surface-card workbench-rail chat-rail" :class="{ collapsed: sidebarCollapsed }">
      <div class="tool-strip">
        <button class="icon-btn" type="button" @click="sidebarCollapsed = !sidebarCollapsed">
          {{ sidebarCollapsed ? "›" : "‹" }}
        </button>
        <button v-if="!sidebarCollapsed" class="btn primary small" type="button" @click="createFreshSession()">
          新建
        </button>
      </div>

      <template v-if="!sidebarCollapsed">
        <div class="rail-headline">
          <div>
            <p class="eyebrow">历史会话</p>
            <h2>最近对话</h2>
          </div>
          <button class="btn ghost small" type="button" @click="refreshSessions">刷新</button>
        </div>

        <p v-if="pageError" class="inline-error">{{ pageError }}</p>

        <div class="rail-scroll compact-stack">
          <button
            v-for="session in sessions"
            :key="session.session_id"
            type="button"
            class="session-row"
            :class="{ active: session.session_id === currentSessionId }"
            @click="openSession(session.session_id)"
          >
            <strong>{{ session.title || session.session_id }}</strong>
            <p>{{ session.preview || "暂无摘要" }}</p>
            <span>{{ formatTimestamp(session.updated_at) }}</span>
          </button>
        </div>
      </template>
    </aside>

    <section class="surface-card workbench-main chat-main">
      <header class="chat-toolbar">
        <div class="toolbar-left">
          <button class="icon-btn" type="button" @click="sidebarCollapsed = !sidebarCollapsed">
            {{ sidebarCollapsed ? "≡" : "←" }}
          </button>
          <div>
            <p class="eyebrow">聊天助手</p>
            <h1>{{ currentSessionTitle }}</h1>
          </div>
        </div>
        <div class="summary-bar">
          <span class="chip">{{ visibleMessages.length }} 条消息</span>
          <span class="chip" :class="backendState">{{ backendLabel }}</span>
          <button class="btn ghost small" type="button" @click="refreshCurrentConversation">刷新</button>
          <button class="btn ghost small" type="button" @click="inspectorOpen = !inspectorOpen">
            {{ inspectorOpen ? "隐藏侧栏" : "显示侧栏" }}
          </button>
        </div>
      </header>

      <section v-if="backendState !== 'ready'" class="inline-banner">
        <strong>后端暂时不可用</strong>
        <p class="muted">请先启动后端。当前地址：{{ API_BASE_URL }}</p>
        <pre class="command-block">cd backend
python -m app.main</pre>
      </section>

      <main ref="messagesViewport" class="content-scroll chat-stream">
        <article
          v-for="message in visibleMessages"
          :key="message.id"
          class="message-row"
          :class="message.role"
        >
          <div class="message-bubble" :class="message.role">
            <header class="message-meta">
              <span>{{ message.role === "user" ? "你" : "助手" }}</span>
              <span>{{ formatTimestamp(message.timestamp) }}</span>
            </header>
            <p v-if="message.role === 'user'" class="message-plain">{{ message.content }}</p>
            <MarkdownContent v-else-if="message.content" :source="message.content" />
            <p v-else class="muted">正在生成...</p>
          </div>
        </article>

        <div v-if="!visibleMessages.length" class="empty-chat">
          <h2>开始一段新对话</h2>
          <p class="muted">中间区域始终保留给消息流和输入框，知识增强与会话信息收进右侧 Inspector。</p>
        </div>
      </main>

      <form class="chat-composer" @submit.prevent="submitChat">
        <div class="composer-top">
          <label class="mini-field">
            <span>User ID</span>
            <input v-model="userId" type="text" placeholder="必填，用于隔离记忆和知识" />
          </label>
          <div class="summary-bar">
            <span class="chip">{{ currentSessionId }}</span>
            <button class="btn ghost small" type="button" :disabled="!running" @click="cancelStream">停止</button>
          </div>
        </div>

        <textarea
          v-model="messageInput"
          rows="3"
          placeholder="输入消息，按 Enter 发送，Shift + Enter 换行..."
          :disabled="running"
          @keydown.enter.exact.prevent="submitChat"
          @keydown.shift.enter.stop
        ></textarea>

        <div class="composer-actions">
          <p v-if="streamError" class="inline-error">{{ streamError }}</p>
          <div class="summary-bar">
            <span class="muted">输入框固定在底部，不会被历史列表或增强面板挤掉。</span>
            <button
              class="btn primary"
              type="submit"
              :disabled="running || !messageInput.trim() || !userId.trim() || backendState !== 'ready'"
            >
              {{ running ? "发送中..." : "发送" }}
            </button>
          </div>
        </div>
      </form>
    </section>

    <aside v-if="inspectorOpen" class="surface-card workbench-inspector chat-inspector">
      <div class="tool-strip">
        <div>
          <p class="eyebrow">Inspector</p>
          <h2>辅助信息</h2>
        </div>
        <button class="icon-btn" type="button" @click="inspectorOpen = false">×</button>
      </div>

      <div class="pane-scroll inspector-stack">
        <section class="info-stack">
          <div class="info-card">
            <span>当前会话</span>
            <strong>{{ currentSessionId }}</strong>
          </div>
          <div class="info-card">
            <span>用户标识</span>
            <strong>{{ userId || "未填写" }}</strong>
          </div>
          <div class="info-card">
            <span>后端状态</span>
            <strong>{{ backendLabel }}</strong>
          </div>
        </section>

        <details class="drawer-card">
          <summary>知识抽屉</summary>
          <KnowledgeQuickPanel
            :app-id="'chat'"
            :session-id="currentSessionId"
            :user-id="userId"
            title="向当前聊天写入临时知识或长期知识"
            @ingested="refreshSessions"
          />
        </details>
      </div>
    </aside>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import KnowledgeQuickPanel from "../components/KnowledgeQuickPanel.vue";
import MarkdownContent from "../components/MarkdownContent.vue";
import {
  API_BASE_URL,
  checkHealth,
  getSessionHistory,
  listSessions,
  streamChat,
  type RunEvent,
  type SessionMessage,
  type SessionSummary
} from "../services/api";

interface ChatBubble {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

const route = useRoute();
const router = useRouter();

const sessions = ref<SessionSummary[]>([]);
const currentSessionId = ref("");
const userId = ref("");
const messageInput = ref("");
const visibleMessages = ref<ChatBubble[]>([]);
const pageError = ref("");
const streamError = ref("");
const running = ref(false);
const backendState = ref<"loading" | "ready" | "error">("loading");
const sidebarCollapsed = ref(false);
const inspectorOpen = ref(true);
const messagesViewport = ref<HTMLElement | null>(null);

let streamAbortController: AbortController | null = null;
let assistantPlaceholderId = "";

const currentSessionTitle = computed(() => {
  const summary = sessions.value.find((item) => item.session_id === currentSessionId.value);
  return summary?.title || "新对话";
});

const backendLabel = computed(() => {
  if (backendState.value === "loading") return "检查中";
  if (backendState.value === "ready") return "在线";
  return "离线";
});

const chatShellStyle = computed(() => ({
  gridTemplateColumns: `${sidebarCollapsed.value ? "72px" : "248px"} minmax(0, 1fr) ${inspectorOpen.value ? "300px" : "0px"}`
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
      await openSession(sessionId, false);
    }
  }
);

async function hydratePage(): Promise<void> {
  await refreshSessions();
  const routeSessionId = typeof route.params.sessionId === "string" ? route.params.sessionId : "";
  if (routeSessionId) {
    await openSession(routeSessionId, false);
    return;
  }
  if (sessions.value[0]) {
    await openSession(sessions.value[0].session_id);
    return;
  }
  await createFreshSession();
}

async function refreshSessions(): Promise<void> {
  backendState.value = "loading";
  try {
    await checkHealth();
    sessions.value = await listSessions("chat", 60);
    backendState.value = "ready";
    pageError.value = "";
  } catch (error) {
    backendState.value = "error";
    pageError.value = getErrorMessage(error);
  }
}

async function openSession(sessionId: string, updateRoute = true): Promise<void> {
  currentSessionId.value = sessionId;
  streamError.value = "";
  if (updateRoute && route.params.sessionId !== sessionId) {
    await router.push({ name: "chat", params: { sessionId } });
  }
  try {
    const result = await getSessionHistory(sessionId, "chat");
    visibleMessages.value = result.messages
      .filter((message) => message.role === "user" || message.role === "assistant")
      .map(mapHistoryMessage);
    await scrollToBottom();
  } catch (error) {
    streamError.value = getErrorMessage(error);
  }
}

async function createFreshSession(): Promise<void> {
  cancelStream();
  const sessionId = createSessionId("chat");
  currentSessionId.value = sessionId;
  visibleMessages.value = [];
  messageInput.value = "";
  streamError.value = "";
  await router.push({ name: "chat", params: { sessionId } });
}

async function refreshCurrentConversation(): Promise<void> {
  if (!currentSessionId.value) return;
  await openSession(currentSessionId.value, false);
  await refreshSessions();
}

async function submitChat(): Promise<void> {
  if (!messageInput.value.trim() || running.value || backendState.value !== "ready") {
    return;
  }
  if (!userId.value.trim()) {
    streamError.value = "聊天工作区必须填写 User ID。";
    return;
  }

  streamAbortController?.abort();
  streamAbortController = new AbortController();
  running.value = true;
  streamError.value = "";

  const content = messageInput.value.trim();
  const timestamp = new Date().toISOString();
  visibleMessages.value.push({
    id: `user-${timestamp}`,
    role: "user",
    content,
    timestamp
  });
  assistantPlaceholderId = `assistant-${timestamp}`;
  visibleMessages.value.push({
    id: assistantPlaceholderId,
    role: "assistant",
    content: "",
    timestamp
  });
  messageInput.value = "";
  await scrollToBottom();

  try {
    await streamChat(
      { session_id: currentSessionId.value, message: content, user_id: userId.value.trim() },
      handleChatEvent,
      { signal: streamAbortController.signal }
    );
  } catch (error) {
    if (!isAbortError(error)) {
      streamError.value = getErrorMessage(error);
      replaceAssistantPlaceholder(streamError.value);
    }
  } finally {
    running.value = false;
    await refreshSessions();
  }
}

function handleChatEvent(event: RunEvent): void {
  if (event.type === "message_chunk") {
    appendAssistantChunk(stringValue(event.content));
    return;
  }
  if (event.type === "message_done") {
    replaceAssistantPlaceholder(stringValue(event.content));
  }
  if (event.type === "error") {
    const message = stringValue(event.message) || "未知聊天错误";
    streamError.value = message;
    replaceAssistantPlaceholder(message);
  }
}

function replaceAssistantPlaceholder(content: string): void {
  const target = visibleMessages.value.find((item) => item.id === assistantPlaceholderId);
  if (target) {
    target.content = content;
  }
  void scrollToBottom();
}

function appendAssistantChunk(chunk: string): void {
  const target = visibleMessages.value.find((item) => item.id === assistantPlaceholderId);
  if (!target) {
    return;
  }
  target.content += chunk;
  void scrollToBottom();
}

function cancelStream(): void {
  streamAbortController?.abort();
  running.value = false;
}

function mapHistoryMessage(message: SessionMessage, index: number): ChatBubble {
  return {
    id: `${message.role}-${message.timestamp}-${index}`,
    role: message.role === "user" ? "user" : "assistant",
    content: message.content,
    timestamp: message.timestamp
  };
}

async function scrollToBottom(): Promise<void> {
  await nextTick();
  const viewport = messagesViewport.value;
  if (viewport) {
    viewport.scrollTop = viewport.scrollHeight;
  }
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

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
</script>

<style scoped>
.chat-shell {
  align-items: stretch;
  height: 100%;
}

.chat-rail {
  transition: width 0.2s ease, padding 0.2s ease;
}

.chat-rail.collapsed {
  padding-inline: 10px;
}

.rail-headline h2,
.toolbar-left h1 {
  margin: 6px 0 0;
  font-size: 1rem;
}

.session-row {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.74);
  text-align: left;
}

.session-row.active {
  border-color: rgba(76, 134, 255, 0.34);
  background: rgba(232, 242, 255, 0.92);
}

.session-row strong,
.session-row p,
.session-row span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.session-row p {
  margin: 0;
  color: var(--muted);
  font-size: 0.85rem;
}

.session-row span {
  color: var(--muted);
  font-size: 0.78rem;
}

.chat-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 12px;
  border-bottom: 1px solid rgba(76, 134, 255, 0.12);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.toolbar-left h1 {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-stream {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: grid;
  gap: 12px;
  align-content: start;
  padding: 16px;
}

.message-row {
  display: flex;
}

.message-row.user {
  justify-content: flex-end;
}

.message-bubble {
  width: min(820px, 100%);
  padding: 14px 16px;
  border-radius: 22px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.84);
  box-shadow: var(--shadow-soft);
}

.message-bubble.user {
  background: linear-gradient(135deg, rgba(76, 134, 255, 0.92), rgba(123, 184, 255, 0.92));
  color: white;
}

.message-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.76rem;
  opacity: 0.8;
}

.message-plain {
  margin: 10px 0 0;
  white-space: pre-wrap;
}

.empty-chat {
  min-height: 100%;
  display: grid;
  place-items: center;
  text-align: center;
  padding: 24px;
}

.empty-chat h2 {
  margin: 0 0 8px;
}

.chat-composer {
  flex-shrink: 0;
  z-index: 2;
  display: grid;
  gap: 12px;
  padding: 14px 16px 16px;
  border-top: 1px solid rgba(76, 134, 255, 0.12);
  background: rgba(245, 250, 255, 0.96);
}

.composer-top,
.composer-actions {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.mini-field {
  display: grid;
  gap: 6px;
  min-width: min(100%, 260px);
}

.mini-field span {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.mini-field input,
.chat-composer textarea {
  width: 100%;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.86);
  color: var(--text);
}

.mini-field input {
  padding: 10px 12px;
}

.chat-composer textarea {
  min-height: 88px;
  padding: 12px 14px;
  resize: vertical;
}

.chat-inspector {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
  padding: 12px;
  gap: 10px;
}

.chat-inspector .tool-strip {
  position: sticky;
  top: 0;
  z-index: 3;
  padding-bottom: 6px;
  background: linear-gradient(180deg, rgba(248, 252, 255, 0.98), rgba(248, 252, 255, 0.9));
}

.inspector-stack {
  flex: 0 0 auto;
  display: grid;
  gap: 10px;
  min-height: 0;
  overflow: visible;
}

.info-stack {
  display: grid;
  gap: 10px;
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

@media (max-width: 1180px) {
  .chat-shell {
    grid-template-columns: 72px minmax(0, 1fr) 0 !important;
  }
}

@media (max-width: 900px) {
  .chat-shell {
    grid-template-columns: 1fr !important;
    height: auto;
  }

  .chat-rail,
  .chat-inspector {
    max-height: 240px;
  }

  .chat-main {
    min-height: 70vh;
  }
}
</style>
