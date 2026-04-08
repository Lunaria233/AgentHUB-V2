<template>
  <div class="app-shell">
    <header class="topbar surface-card">
      <RouterLink class="brand" to="/">
        <span class="brand-mark">AH</span>
        <div>
          <strong>AgentHub</strong>
          <span>多智能体应用平台</span>
        </div>
      </RouterLink>

      <nav class="topnav">
        <RouterLink to="/" class="nav-link">首页</RouterLink>
        <RouterLink to="/chat" class="nav-link">聊天助手</RouterLink>
        <RouterLink to="/research" class="nav-link">深度研究</RouterLink>
        <RouterLink to="/software-engineering" class="nav-link">软件工程智能体</RouterLink>
        <RouterLink to="/rag" class="nav-link">RAG 工作台</RouterLink>
        <RouterLink to="/memory" class="nav-link">记忆中心</RouterLink>
        <RouterLink to="/mcp" class="nav-link">MCP 工作台</RouterLink>
        <RouterLink to="/skills" class="nav-link">Skills 工作台</RouterLink>
        <RouterLink to="/context" class="nav-link">Context 工作台</RouterLink>
      </nav>
    </header>

    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
</script>
