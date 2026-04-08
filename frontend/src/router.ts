import { createRouter, createWebHistory } from "vue-router";

import HomePage from "./pages/HomePage.vue";
import ChatPage from "./pages/ChatPage.vue";
import ResearchPage from "./pages/ResearchPage.vue";
import MemoryPage from "./pages/MemoryPage.vue";
import RagPage from "./pages/RagPage.vue";
import MCPPage from "./pages/MCPPage.vue";
import SkillsPage from "./pages/SkillsPage.vue";
import ContextPage from "./pages/ContextPage.vue";
import SoftwareEngineeringPage from "./pages/SoftwareEngineeringPage.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: HomePage },
    { path: "/chat/:sessionId?", name: "chat", component: ChatPage, props: true },
    { path: "/research/:sessionId?", name: "research", component: ResearchPage, props: true },
    { path: "/memory", name: "memory", component: MemoryPage },
    { path: "/rag", name: "rag", component: RagPage },
    { path: "/mcp", name: "mcp", component: MCPPage },
    { path: "/skills", name: "skills", component: SkillsPage },
    { path: "/context", name: "context", component: ContextPage },
    { path: "/software-engineering/:sessionId?", name: "software-engineering", component: SoftwareEngineeringPage, props: true }
  ],
  scrollBehavior() {
    return { top: 0 };
  }
});
