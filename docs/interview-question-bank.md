# AgentHub 面试问题库

这份问题库按“由浅到深”组织，目的是让你提前准备，避免被面试官一路追问时卡住。

---

## 1. 项目定位类问题
- 这个项目是做什么的？
- 为什么要做这个项目？
- 它和普通聊天机器人项目有什么区别？
- 为什么你说它是“多智能体应用平台”而不是“几个 Agent demo”？
- 这个项目当前落地了几个应用？
- 这个项目最核心的价值是什么？

---

## 2. 整体架构类问题
- 整个项目如何分层？
- 平台层和应用层分别负责什么？
- 你为什么要做共享底座？
- 为什么不能每个 Agent 各写一套？
- 现在项目里哪些是平台级能力？
- 哪些是 app 私有配置？
- 新增一个 Agent 应用时要改哪些地方？
- 如果以后再加 5 个 Agent，你的架构还能撑住吗？

---

## 3. 运行时与应用链路类问题
- 一个聊天请求进入系统后，完整链路是什么？
- 一个深度研究请求进入系统后，完整链路是什么？
- chat 和 deep_research 的 runtime 有什么本质差异？
- 为什么一个是聊天型 runtime，一个是 workflow 型 runtime？
- AppOrchestrator 做了什么？
- RuntimeFactoryRegistry 的作用是什么？
- 为什么要用 manifest + profile，而不是直接硬编码？

---

## 4. 模型层问题
- 模型层怎么设计的？
- 为什么要单独封装 `OpenAICompatClient`？
- 兼容层做了哪些事情？
- 如何处理 provider 返回格式异常？
- 现在模型调用为什么还会有 provider 侧噪声？
- 连接复用为什么能优化性能？
- 流式输出是怎么做的？

---

## 5. Context Engineering 问题
- 什么是 context engineering？
- 这个项目里的 context engineering 解决了什么问题？
- 为什么不能让每个 app 自己拼 prompt？
- ContextBuilder 里有哪些步骤？
- 你怎么做 source budget？
- 为什么要去重？
- 为什么要压缩 history？
- 为什么要裁剪 RAG chunk？
- 现在的 context explain / eval 能看到什么？
- 还有哪些更高级的 context engineering 你没做？

---

## 6. Memory 问题
- 你项目里的 Memory 和 History 有什么区别？
- 为什么要做 working / episodic / semantic / perceptual / graph 五类 memory？
- 这些 memory 分别用于什么场景？
- 记忆是怎么写入的？
- 记忆是怎么检索的？
- LLM extraction 和 heuristic extraction 怎么配合？
- conflict resolution 是怎么做的？
- forgetting policy 怎么设计的？
- graph memory 具体有什么作用？
- Neo4j 和本地图关系怎么分工？
- 为什么 chat 里要强制 `user_id`？
- 如何避免不同用户记忆串数据？
- 你怎么验证 memory 的质量？
- memory eval 的指标分别代表什么？
- 这些指标能不能写成“系统性能”？
- 现在的 Memory 是否已经够用了？还差什么？

---

## 7. RAG 问题
- RAG 和 Memory 的区别是什么？
- 为什么 RAG 负责外部知识、Memory 负责内部状态？
- 你的 RAG 支持哪些知识输入方式？
- 文件上传后发生了什么？
- URL 导入后发生了什么？
- generated text 为什么也能进入 RAG？
- 你为什么要区分 session temporary、user private、app shared、system public？
- 如果不区分这些 scope 会有什么问题？
- 检索时如何保证不串用户知识？
- retrieval pipeline 是怎么做的？
- lexical / vector / hybrid 分别是什么？
- MQE / HyDE 是什么？为什么有用？
- rerank 是什么？你现在的 rerank 做到什么程度？
- citations 是怎么生成的？
- answer with sources 是怎么做的？
- RAG 和 ContextBuilder 怎么配合？
- RAG 和 deep_research 怎么配合？
- RAG eval 的指标是什么？怎么解释？
- 为什么 precision 可能没 recall 高？
- leakage rate 为什么重要？
- 现在的 RAG 是否够称为“完整 V1”？

---

## 8. MCP 问题
- MCP 是什么？
- MCP 和 ToolRegistry 的区别是什么？
- MCP 为什么不能简单等同于工具系统？
- 你项目支持哪些 MCP transport？
- `stdio` 和 `streamable_http` 有什么区别？
- 本地 server 和远程 server 能不能共存？
- 为什么 JSON 配置本身不是 MCP server？
- `mcp.so` 这种 JSON 是什么？
- `npx` 和 `python -m` 这两种 stdio server 有什么差异？
- 为什么有的 server 不需要预装，有的需要？
- MCPManager 做了什么？
- MCP client 做了什么？
- MCP adapter 做了什么？
- MCP 的 tools/resources/prompts 三件套是什么？
- 为什么有的 server 会返回 `Method not found` 但 tools 还能用？
- MCP 页面里的预检功能为什么有价值？
- 你怎么验证一个 MCP server 真的接通了？
- 资源和 prompts 现在接到哪里了？
- 为什么说 MCP 已经是 V1 完整，而不是最终形态？

---

## 9. Skills 问题
- Skills 是什么？
- Skills 和 Prompt Engineering 的区别是什么？
- Skills 和 MCP 的区别是什么？
- 为什么你要做 Skill system？
- SkillBundle 里包含什么？
- 为什么用 `SKILL.md`？
- references / scripts / assets 各自有什么用？
- skill 是怎么加载和注册的？
- skill 是怎么注入到 runtime 的？
- 为什么要按 stage 注入 skill？
- `chat.reply` 和 `research.report` 的 skill 为什么不同？
- Skills eval 测了什么？
- 现在 skills 是不是完整的？
- 还有哪些更高级的 skill 能力没做？

---

## 10. 深度研究助手问题
- 为什么要做一个深度研究助手，而不是只做聊天？
- 研究助手的 workflow 是什么？
- planner / summarizer / reporter 各自负责什么？
- 任务规划失败了怎么办？
- 搜索不到结果怎么办？
- 为什么 research 里需要 notes？
- 为什么 research 里 generated summary / report 还要再进入 Memory 和 RAG？
- 为什么研究链还是慢？
- 你做了哪些研究链性能优化？
- 如果要继续优化 research，你会优先做什么？

---

## 11. 前端工作台问题
- 为什么要做这么多工作台页面？
- 这些页面是为了展示，还是为了调试？
- Memory 中心有什么用？
- RAG 工作台有什么用？
- MCP 工作台有什么用？
- Skills 工作台有什么用？
- Context 工作台有什么用？
- 为什么要做 explain / eval 页面？
- 前端布局为什么一开始会有滚动问题？
- 你后来是怎么修的？
- 为什么你说输入框必须始终可达？

---

## 12. 评测问题
- 为什么要给 Memory / RAG / Skills / Context 都做 eval？
- 这些 eval 是线上指标吗？
- 这些 eval 能不能代表产品效果？
- eval 为什么要隔离运行？
- 为什么不能直接在生产库上跑 eval？
- 评测集是怎么构造的？
- 如果面试官说“这个评测不够严谨”，你怎么回应？

---

## 13. 性能问题
- 项目最开始为什么慢？
- chat 慢的主要瓶颈是什么？
- research 慢的主要瓶颈是什么？
- 你做了哪些性能优化？
- 哪些优化是平台级的？
- 哪些优化是 chat 专项的？
- 哪些优化是 research 专项的？
- 哪些瓶颈还是 provider/model 侧？
- 为什么要做连接复用？
- 为什么要把 memory/rag/archive 后处理放后台？
- RAG 缓存为什么有用？
- 为什么 chat 要 light/full path？

---

## 14. 数据边界与安全问题
- 如何防止跨用户 memory 污染？
- 如何防止跨用户知识泄漏？
- 为什么 scope 很重要？
- `app_id / user_id / session_id` 各自代表什么边界？
- 为什么临时知识不能默认进长期知识库？
- citation 为什么也要做权限控制？
- MCP server 的权限边界怎么管？
- 不同 app 为什么不能共享所有 memory/rag/tool？

---

## 15. 工程权衡问题
- 为什么不用 LangChain / Dify / AutoGen？
- 为什么你要自己实现框架？
- 为什么不直接用 hello_agents 包？
- 参考 hello_agents 的地方有哪些？
- 哪些地方你没有照搬 hello_agents？
- 为什么 `Memory / RAG / MCP / Skills` 都不只是做成工具？
- 为什么 `ContextBuilder` 必须平台化？
- 为什么 `History / Memory / RAG` 必须分开？

---

## 16. 代码实现深挖问题
- `AppManifest` 的作用是什么？
- `profiles` 是干什么的？
- `ContextProfile / MemoryProfile / RAGProfile / MCPProfile` 各自控制什么？
- `RuntimeFactoryRegistry` 为什么比 `if app_id == ...` 更好？
- `ToolRegistry` 为什么是运行时注册层而不是协议层？
- `MCPToolAdapter` 做了什么映射？
- `MemoryService` 和 `SQLiteMemoryStore` 如何分工？
- `RAGService` 和 `SQLiteRAGStore / QdrantRAGIndex` 如何分工？
- `SkillRegistry` 和 `PlatformSkillRuntime` 如何分工？

---

## 17. 上线与扩展问题
- 如果要加第三个 Agent，比如旅行助手，怎么接？
- 旅行助手会复用哪些平台能力？
- 哪些地方需要专门定制？
- 如果未来要做多租户，哪些地方要改？
- 如果未来要支持更多模型 provider，哪些地方已经准备好了？
- 如果未来要支持更多 MCP transport，哪些地方还需要扩展？
- 如果未来要继续做更高级 context engineering，你会做什么？

---

## 18. 结果与价值问题
- 这个项目最能体现你哪方面能力？
- 如果只能挑三点讲，你会挑什么？
- 你认为这个项目最强的部分是什么？
- 你认为这个项目当前最大短板是什么？
- 如果再给你两周，你会优先补什么？

---

## 19. 面试时建议的回答方式
- 先讲“为什么”
- 再讲“系统如何拆”
- 再讲“一个请求怎么流”
- 再讲“你做了哪些工程闭环”
- 最后讲“还差什么”

不要上来就按目录背文件名。  
要让面试官先听懂这个项目解决了什么问题，再听你怎么实现。
