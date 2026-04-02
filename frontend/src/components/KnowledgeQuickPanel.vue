<template>
  <section class="quick-panel">
    <div class="tool-strip">
      <div>
        <p class="eyebrow">知识输入</p>
        <h2>{{ title }}</h2>
      </div>
      <button class="btn ghost small" type="button" @click="resetForm" :disabled="busy">重置</button>
    </div>

    <div class="field-grid">
      <label class="field">
        <span>写入目标</span>
        <select v-model="knowledgeTarget" :disabled="busy">
          <option value="session_temporary">当前会话</option>
          <option value="user_private">用户长期知识</option>
        </select>
      </label>
      <label class="field">
        <span>标题</span>
        <input v-model="titleInput" type="text" placeholder="知识标题" :disabled="busy" />
      </label>
    </div>

    <p class="context-hint muted">
      <template v-if="knowledgeTarget === 'session_temporary'">
        当前会话知识需要有效的 Session ID。适合临时材料、研究过程产物和一次性上下文。
      </template>
      <template v-else>
        用户长期知识需要 User ID。适合稳定偏好、个人资料和长期约束。
      </template>
    </p>

    <div class="surface-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        type="button"
        class="tab-btn"
        :class="{ active: mode === tab.value }"
        @click="mode = tab.value"
      >
        {{ tab.label }}
      </button>
    </div>

    <label v-if="mode === 'text'" class="field">
      <span>文本知识</span>
      <textarea
        v-model="textInput"
        rows="5"
        placeholder="粘贴岗位要求、研究材料、行程约束、规则说明或任何参考文本。"
        :disabled="busy"
      ></textarea>
    </label>

    <label v-else-if="mode === 'url'" class="field">
      <span>网页地址</span>
      <input v-model="urlInput" type="url" placeholder="https://example.com/article" :disabled="busy" />
    </label>

    <label v-else class="field">
      <span>文档文件</span>
      <input ref="fileInput" type="file" accept=".pdf,.docx,.txt,.md" :disabled="busy" @change="handleFileChange" />
      <small class="muted">{{ selectedFile?.name || "支持 PDF / DOCX / TXT / MD" }}</small>
    </label>

    <div class="panel-actions">
      <div class="message-stack">
        <p v-if="errorMessage" class="inline-error">{{ errorMessage }}</p>
        <p v-if="successMessage" class="success-message">{{ successMessage }}</p>
      </div>
      <button class="btn primary" type="button" :disabled="busy" @click="submitKnowledge">
        {{ busy ? "处理中..." : actionLabel }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import { addRagText, importRagUrl, uploadRagDocument } from "../services/api";

const props = withDefaults(
  defineProps<{
    appId: string;
    sessionId?: string;
    userId?: string;
    title?: string;
    ownerId?: string;
  }>(),
  {
    sessionId: "",
    userId: "",
    title: "向当前工作区添加知识",
    ownerId: "ui"
  }
);

const emit = defineEmits<{
  ingested: [payload: Record<string, unknown>];
}>();

type InputMode = "text" | "url" | "file";

const tabs: Array<{ label: string; value: InputMode }> = [
  { label: "文本", value: "text" },
  { label: "网页", value: "url" },
  { label: "文件", value: "file" }
];

const mode = ref<InputMode>("text");
const knowledgeTarget = ref<"session_temporary" | "user_private">("session_temporary");
const titleInput = ref("");
const textInput = ref("");
const urlInput = ref("");
const selectedFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const busy = ref(false);
const errorMessage = ref("");
const successMessage = ref("");

const actionLabel = computed(() => {
  if (mode.value === "text") return "写入文本知识";
  if (mode.value === "url") return "导入网页";
  return "上传文档";
});

async function submitKnowledge(): Promise<void> {
  errorMessage.value = "";
  successMessage.value = "";

  if (knowledgeTarget.value === "session_temporary" && !props.sessionId.trim()) {
    errorMessage.value = "当前会话知识必须提供 Session ID。请先进入一个会话，或切换到“用户长期知识”。";
    return;
  }

  if (knowledgeTarget.value === "user_private" && !props.userId.trim()) {
    errorMessage.value = "写入用户长期知识时必须填写 User ID。";
    return;
  }

  if (mode.value === "text" && !textInput.value.trim()) {
    errorMessage.value = "请输入要写入的文本内容。";
    return;
  }

  if (mode.value === "url" && !urlInput.value.trim()) {
    errorMessage.value = "请输入网页地址。";
    return;
  }

  if (mode.value === "file" && !selectedFile.value) {
    errorMessage.value = "请先选择文件。";
    return;
  }

  busy.value = true;
  try {
    const payloadTitle = resolveTitle();
    let result: Record<string, unknown>;
    if (mode.value === "text") {
      result = await addRagText({
        app_id: props.appId,
        title: payloadTitle,
        text: textInput.value.trim(),
        user_id: props.userId || undefined,
        session_id: props.sessionId || undefined,
        owner_id: props.ownerId,
        knowledge_target: knowledgeTarget.value
      });
    } else if (mode.value === "url") {
      result = await importRagUrl({
        app_id: props.appId,
        title: payloadTitle,
        url: urlInput.value.trim(),
        user_id: props.userId || undefined,
        session_id: props.sessionId || undefined,
        owner_id: props.ownerId,
        knowledge_target: knowledgeTarget.value
      });
    } else {
      result = await uploadRagDocument({
        app_id: props.appId,
        title: payloadTitle,
        file: selectedFile.value as File,
        user_id: props.userId || undefined,
        session_id: props.sessionId || undefined,
        owner_id: props.ownerId,
        knowledge_target: knowledgeTarget.value
      });
    }
    successMessage.value = `已写入 ${stringValue(result.title) || payloadTitle}`;
    emit("ingested", result);
    clearModeInputs();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    busy.value = false;
  }
}

function handleFileChange(event: Event): void {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] || null;
}

function resolveTitle(): string {
  if (titleInput.value.trim()) return titleInput.value.trim();
  if (mode.value === "url") return urlInput.value.trim();
  if (mode.value === "file" && selectedFile.value) return selectedFile.value.name;
  return `${props.appId} knowledge`;
}

function clearModeInputs(): void {
  textInput.value = "";
  urlInput.value = "";
  selectedFile.value = null;
  if (fileInput.value) {
    fileInput.value.value = "";
  }
}

function resetForm(): void {
  titleInput.value = "";
  textInput.value = "";
  urlInput.value = "";
  selectedFile.value = null;
  errorMessage.value = "";
  successMessage.value = "";
  if (fileInput.value) {
    fileInput.value.value = "";
  }
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}
</script>

<style scoped>
.quick-panel {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
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

.context-hint {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.55;
}

.panel-actions {
  display: grid;
  gap: 10px;
}

.message-stack {
  display: grid;
  gap: 6px;
}

.success-message {
  margin: 0;
  color: var(--success);
}
</style>
