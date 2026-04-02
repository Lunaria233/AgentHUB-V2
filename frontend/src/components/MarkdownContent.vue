<template>
  <div class="markdown-body" v-html="rendered"></div>
</template>

<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { computed } from "vue";

const props = defineProps<{
  source: string;
}>();

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: true
});

const rendered = computed(() => md.render(props.source || ""));
</script>

<style scoped>
.markdown-body {
  color: var(--text);
  line-height: 1.72;
  font-size: 0.98rem;
  word-break: break-word;
}

.markdown-body :deep(> *:first-child) {
  margin-top: 0;
}

.markdown-body :deep(> *:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 1.1em 0 0.55em;
  line-height: 1.18;
  letter-spacing: -0.02em;
}

.markdown-body :deep(h1) {
  font-size: 1.7rem;
}

.markdown-body :deep(h2) {
  font-size: 1.35rem;
}

.markdown-body :deep(h3) {
  font-size: 1.08rem;
}

.markdown-body :deep(p),
.markdown-body :deep(ul),
.markdown-body :deep(ol),
.markdown-body :deep(table),
.markdown-body :deep(pre),
.markdown-body :deep(blockquote) {
  margin: 0.8em 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.4em;
}

.markdown-body :deep(li + li) {
  margin-top: 0.38em;
}

.markdown-body :deep(blockquote) {
  padding: 0.8em 1em;
  border-left: 3px solid rgba(76, 134, 255, 0.4);
  background: rgba(237, 245, 255, 0.8);
  border-radius: 0 14px 14px 0;
  color: #34516f;
}

.markdown-body :deep(code) {
  padding: 0.18em 0.45em;
  border-radius: 8px;
  background: rgba(228, 238, 252, 0.9);
  font-family: var(--font-mono);
  font-size: 0.92em;
}

.markdown-body :deep(pre) {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(233, 241, 252, 0.88);
  border: 1px solid rgba(76, 134, 255, 0.14);
  overflow: auto;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  border-spacing: 0;
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid var(--border);
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(76, 134, 255, 0.12);
  text-align: left;
}

.markdown-body :deep(th) {
  background: rgba(233, 241, 252, 0.9);
  font-weight: 600;
}

.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid rgba(76, 134, 255, 0.2);
  margin: 1.2em 0;
}

.markdown-body :deep(a) {
  color: var(--accent-strong);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}
</style>
