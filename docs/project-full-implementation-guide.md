# AgentHub 从 0 到 1 的完整实现说明书

## 1. 这份文档是做什么的
这份文档的目标不是简单介绍“有哪些模块”，而是完整讲清楚：
- 项目要解决什么问题
- 为什么要实现这些能力
- 每个能力具体做了什么
- 这些能力在系统里如何配合
- 数据是怎么流动的
- 用户如何感知到这些能力
- 如何测试每一部分

如果你后面要面试、写项目介绍、准备技术答辩，这份文档就是总材料。

---

## 2. 项目从 0 开始时要解决的核心问题

### 2.1 单 Agent demo 的局限
一开始如果只做一个 Agent demo，通常会出现这些问题：
- Prompt、知识、工具、记忆、运行时都写在一起
- 不同应用无法复用
- 一旦想增加第二个 Agent，代码边界会变乱
- 很难做统一调试与评测
- 很难做权限隔离

### 2.2 我们真正想做的是什么
我们要做的不是“一个会回答问题的助手”，而是：

**一个多智能体应用平台**

这个平台要同时满足两件事：
1. 平台层有共享底座
2. 不同 Agent 应用又能有自己的配置和行为差异

### 2.3 为什么平台化
因为多个 Agent 之间有很多共性：
- 都要调模型
- 都要管理会话
- 都可能需要知识检索
- 都可能需要长期记忆
- 都可能需要接工具
- 都可能需要做上下文编排

所以把这些都放到平台层，才能真正复用。

---

## 3. 项目整体架构

### 3.1 平台层
平台层当前主要包含：
- Model Gateway
- History
- Context Builder
- Memory
- RAG
- MCP
- Skills
- Tool Registry / Tool Executor
- Runtime / Orchestrator
- App Registry
- Trace / Eval

### 3.2 应用层
当前落地的应用有两个：
- `chat`
- `deep_research`

### 3.3 前端工作台层
当前前端页面包括：
- 首页 Dashboard
- 聊天助手
- 深度研究
- RAG 工作台
- 记忆中心
- MCP 工作台
- Skills 工作台
- Context 工作台

---

## 4. 平台基础设施是如何从 0 开始做起来的

### 4.1 统一配置体系
#### 作用
统一管理模型、搜索、embedding、Qdrant、Neo4j、MCP、RAG、Memory 等配置。

#### 为什么要做
如果没有统一配置，后面每条能力线都会在不同模块里散落配置，项目很快失控。

#### 怎么做
- `.env` 管理密钥和环境差异
- `platform.toml` 管理结构化配置
- `config.py` 负责加载和合并

#### 用户如何感知
- 换模型、换向量库、加 MCP server 不需要大改代码

#### 如何测试
- 修改 env 后重启服务
- 检查 `/api/*/status` 是否反映新配置

---

### 4.2 模型调用层
#### 模型层是什么
模型层负责统一封装 OpenAI-compatible API，包括：
- 普通调用
- 流式调用
- 错误包装
- provider 返回异常兼容

#### 为什么有用
平台后面所有应用和能力都通过这一层调模型，而不是每个地方自己直接写 HTTP 请求。

#### 如何实现
- `BaseModelClient`
- `OpenAICompatClient`
- 统一 `ModelRequest / ModelResponse / ModelChunk`

#### 数据流
runtime -> model client -> provider -> response -> runtime

#### 用户如何感知
- chat 和 research 都能用同一套模型配置
- 流式输出体验一致

#### 如何测试
- `/api/chat`
- `/api/research`
- 单独 smoke test `model_client.generate()` / `stream_generate()`

---

### 4.3 History
#### History 是什么
History 是原始会话日志，不是长期记忆。

#### 为什么要单独做
History 和 Memory 解决的问题不同：
- History 记录原始对话
- Memory 记录提炼后的长期状态

#### 如何实现
- SQLiteHistoryStore
- HistoryService

#### 数据流
user message -> history  
assistant answer -> history

#### 用户如何感知
- 聊天历史能回看
- 深度研究的历史 run 能回看

#### 如何测试
- `/api/sessions/*`
- 前端聊天页和研究页历史侧栏

---

## 5. Context Engineering 全量说明

### 5.1 Context 是什么
Context engineering 指的不是“多写点 Prompt”，而是：

**在每次模型调用前，决定哪些信息应该进上下文、按什么结构进、带多少、以什么顺序进。**

### 5.2 为什么需要它
如果没有平台级 ContextBuilder：
- 每个 app 都会自己拼 prompt
- history / memory / rag / notes 无法统一治理
- token 很容易失控
- 之后很难调优和评估

### 5.3 当前支持什么
- gather
- source budget
- dedupe
- history 压缩
- rag chunk 裁剪
- structure
- prompt 输出
- explain
- eval

### 5.4 如何实现
#### 输入
- history provider
- memory provider
- rag provider
- notes provider
- inline packets

#### 流程
1. runtime 创建 `ContextBuildRequest`
2. providers 依次 collect packets
3. builder 做来源预算
4. 做 packet 去重
5. 进行选择
6. 对 history、rag 做压缩/裁剪
7. 组装 sections
8. 输出 prompt

### 5.5 具体能解决什么问题
- 让 chat 走 light/full path
- 让 research 不同阶段吃不同上下文
- 避免 RAG 和 history 一起把上下文塞爆
- 让上下文来源更可解释

### 5.6 用户如何感知
- 简单聊天更快
- 文档型请求会自动启用更重的 knowledge path
- research 的 plan / summarize / report 看到的上下文不一样

### 5.7 如何测试
- `/context`
- `/api/context/explain`
- `/api/context/eval`

---

## 6. Memory 全量说明

### 6.1 Memory 是什么
Memory 不是聊天历史缓存，而是长期可检索状态层。

### 6.2 为什么需要 Memory
因为 Agent 不应该每一轮都失忆。  
聊天要记住用户偏好，研究要记住任务结论，后续任务要基于之前状态继续。

### 6.3 当前支持的 Memory 类型
- `working`
- `episodic`
- `semantic`
- `perceptual`（文档型）
- `graph`

### 6.4 这些类型分别有什么用
#### working
短期高价值状态，例如当前研究任务中的搜索观察。

#### episodic
事件型记忆，例如一轮交互、一次任务结果。

#### semantic
长期稳定事实，例如用户偏好、研究结论。

#### perceptual
对文档/文件内容的感知型记忆，例如文档快照摘要。

#### graph
实体和关系，例如用户 -> 偏好 -> 某个目标，任务 -> 主题 -> 文档。

### 6.5 如何实现
#### 写入
1. chat / research / 文档输入触发
2. 走 heuristic / LLM extraction
3. 形成 candidate
4. conflict resolution
5. 写 SQLite
6. 写 embedding 到 Qdrant
7. 写图关系到本地图 / Neo4j

#### 检索
1. context provider 调 MemoryService
2. lexical / vector / graph recall
3. 结合 importance、type、recency、access_count 排序
4. 返回 packets 给 ContextBuilder

### 6.6 还做了哪些高级能力
- conflict resolution
- forgetting policy
- graph memory
- evaluation

### 6.7 为什么这些高级能力有用
#### conflict resolution
防止新旧偏好、事实互相污染。

#### forgetting policy
防止 working memory 无限堆积。

#### graph memory
让系统不只记住“事实点”，还记住“关系”。

#### evaluation
让记忆能力不只是能跑，而是能做质量回归。

### 6.8 用户如何感知
- 不同 `user_id` 的爱好可以被分别记住
- 同一用户下再次提问时会召回正确偏好
- 研究助手会带着之前任务的结论继续推理

### 6.9 如何测试
- 聊天页用不同 `user_id` 写不同偏好再提问
- `/memory` 页面运行检索
- `/api/memory/eval`
- 看 `recall / precision / pollution / conflict quality`

---

## 7. RAG 全量说明

### 7.1 RAG 是什么
RAG 是外部知识检索增强，不是长期记忆。

### 7.2 为什么要和 Memory 分开
- Memory 存的是系统/用户内部状态
- RAG 存的是外部知识文档

如果混在一起，平台很快就会出现知识污染和权限混乱。

### 7.3 当前支持哪些导入方式
- 文本直接输入
- 文件上传
- URL 导入
- app 预置知识
- agent 生成内容沉淀为知识

### 7.4 导入后会发生什么
#### 文本导入
文本 -> Document -> parse -> chunk -> embed -> SQLite + Qdrant

#### 文件导入
文件 -> parser -> ParsedDocument -> chunk -> embed -> SQLite + Qdrant

#### URL 导入
URL -> fetch -> parse webpage -> chunk -> embed -> SQLite + Qdrant

#### 生成内容导入
research task summary / report -> generated knowledge -> session temporary knowledge

### 7.5 为什么要支持多种知识域
当前知识域包括：
- session temporary
- user private
- app shared
- system public

这样可以避免：
- 临时知识误入长期知识库
- 跨用户串知识
- app 之间读到不该读的知识

### 7.6 Retrieval 是怎么做的
1. 构建 `RetrievalQuery`
2. 规划 scope
3. lexical search
4. vector search
5. hybrid merge
6. query rewrite / MQE / HyDE
7. rerank
8. 生成 structured citations
9. 注入 ContextBuilder
10. answer with sources

### 7.7 这些增强为什么有用
#### lexical + vector
同时兼顾关键词精确匹配和语义相似度。

#### MQE
一个问题扩成多个查询，提高召回覆盖率。

#### HyDE
先生成假设文档，再用它去检索，提高复杂问题召回质量。

#### rerank
对 top-k 结果做再排序，提高最终上下文质量。

### 7.8 用户如何感知
- 可以上传文件或贴文本
- 可以让 chat 或 research 基于知识回答
- 答案带 structured sources
- RAG 工作台里能直接看召回结果、引用和评测

### 7.9 和其他能力的配合
#### 与 Context
RAG 不是直接拼 prompt，而是转成 packets 给 ContextBuilder。

#### 与 Memory
RAG 不负责偏好和用户长期事实，但 research 生成内容会先入 RAG session knowledge，再和 Memory 配合使用。

#### 与 research
research 的 task summary、final report 可以继续作为后续检索知识。

### 7.10 如何测试
- `/rag`
- `/api/rag/search`
- `/api/rag/answer`
- `/api/rag/eval`
- 上传文本/文件/URL，再检索和回答

---

## 8. MCP 全量说明

### 8.1 MCP 是什么
MCP 是外部能力接入协议层。

### 8.2 为什么需要它
如果每接一个外部工具都自己写适配，后面会非常乱。  
MCP 让外部能力接入标准化。

### 8.3 当前支持哪些 server
- `stdio`
- `streamable_http`

### 8.4 本地和外部 server 可以共存吗
可以。  
平台允许多个 MCP server 同时注册、同时启用。

### 8.5 JSON 配置导入是什么
像 `mcp.so` 那种 JSON，本质上不是 server，而是：
- 如何启动 stdio server
- 或如何连接远程 server

### 8.6 当前做了哪些能力
- server import
- config preflight
- enable / disable / delete
- catalog
- tools / resources / prompts
- tool adapter -> ToolRegistry
- API 调试
- MCP 工作台

### 8.7 用户如何感知
- 在 MCP 工作台里粘一段 JSON 就能新增 server
- 可以查看它有哪些 tools/resources/prompts
- 可以直接调用测试
- 聊天助手可以真正调用 MCP tool

### 8.8 如何测试
- `/mcp`
- `/api/mcp/status`
- `/api/mcp/catalog`
- `/api/mcp/call`

---

## 9. Skills 全量说明

### 9.1 Skills 是什么
Skills 不是外部连接，而是平台里的“领域行为包”。

一个 Skill 至少包含：
- `SKILL.md`
- prompt fragments
- stage config
- references
- scripts
- assets

### 9.2 为什么需要 Skills
因为不同 app、不同阶段不仅需要不同 Prompt，还需要不同领域知识和行为约束。

### 9.3 当前怎么实现
1. 扫描 `skills/`
2. 解析 `SKILL.md`
3. 注册 `SkillBundle`
4. app manifest 里定义 `SkillBinding`
5. runtime 按 `app + stage` resolve
6. skill 注入 prompt fragments 和资源

### 9.4 references / scripts / assets 有什么用
#### references
给 skill 提供结构化知识资源。

#### scripts
给 skill 提供可执行的本地逻辑。

#### assets
提供模板、示例、静态资源。

### 9.5 用户如何感知
- chat.reply 会自动带 `general_qa / tool_use_hygiene / source_grounding`
- research.plan 会带 `research_planning`
- research.report 会带 `research_synthesis`

### 9.6 如何测试
- `/skills`
- `/api/skills/catalog`
- `/api/skills/resolve`
- `/api/skills/eval`

---

## 10. 前端工作台都做了什么

### 首页
作用：
- 平台入口
- 应用入口
- 最近活动
- 状态摘要

### 聊天页
作用：
- 多轮聊天
- 历史会话
- inspector
- 知识注入

### 深度研究页
作用：
- topic 输入
- task / report / log 展示
- 历史研究回看

### RAG 工作台
作用：
- 知识导入
- 检索测试
- 回答测试
- 评测

### 记忆中心
作用：
- 记忆检索
- 结果查看
- 图关系和评测

### MCP 工作台
作用：
- server 导入
- preflight
- 启停删除
- tool/resource/prompt 调试

### Skills 工作台
作用：
- skill 目录
- stage 生效结果
- eval

### Context 工作台
作用：
- explain
- eval
- 看 source budgets / dedupe / compression / prompt preview

---

## 11. 评测都做了什么

### Memory eval
指标：
- recall@k
- precision@k
- pollution rate
- conflict resolution quality

### RAG eval
指标：
- recall@k
- precision@k
- MRR
- leakage rate
- source coverage

### Skills eval
指标：
- precision
- recall
- reference loading coverage
- resource inventory coverage

### Context eval
指标：
- utilization
- dedupe rate
- compression gain
- source diversity

### 为什么这些评测有用
它们不是“线上性能指标”，但能证明：
- 能力不是只会跑
- 系统可以做质量回归
- 你有工程治理意识

---

## 12. 性能优化都做了什么

### chat 方向
- light/full context path
- history / memory / rag provider 短路
- memory 后处理异步化
- 真流式输出
- model HTTP 连接复用

### RAG 方向
- no_accessible_documents 短路
- search cache

### research 方向
- task 并发
- memory/rag/archive 后处理异步化
- 阶段输出 token 上限收紧
- 任务数量裁剪

### 用户如何感知
- 普通聊天明显更快
- 重复检索更快
- research 虽然仍慢，但不会再被一堆后处理额外拖住

---

## 13. 如何测试整个项目

### 13.1 聊天
1. 打开聊天页
2. 传 `user_id`
3. 发普通消息
4. 发知识型消息
5. 看：
- light/full 路径是否生效
- memory 是否隔离
- RAG 是否按需启用

### 13.2 深度研究
1. 输入 topic
2. 观察 task 生成
3. 观察 citations
4. 查看 report
5. 回看历史研究

### 13.3 Memory
1. 用不同 `user_id` 写不同偏好
2. 重新提问
3. 在记忆中心检索
4. 运行 eval

### 13.4 RAG
1. 导入文本
2. 导入文件
3. 导入 URL
4. 运行 search
5. 运行 answer with sources
6. 运行 eval

### 13.5 MCP
1. 导入一个 server
2. 预检
3. 启动
4. 刷 catalog
5. 调用 tool
6. 在 chat 中让模型触发工具

### 13.6 Skills
1. 打开 skills 工作台
2. 看 catalog
3. 看某个 app/stage 的 resolved skill
4. 运行 eval

### 13.7 Context
1. 打开 context 工作台
2. 对 chat/research 做 explain
3. 看 packets/source budgets
4. 运行 eval

---

## 14. 这份项目在面试中最容易被追问的点
- 为什么 Memory 和 History 分开
- 为什么 RAG 和 Memory 分开
- MCP 和 ToolRegistry 的区别
- Skills 和 Prompt Engineering 的区别
- 为什么要有 ContextBuilder
- 为什么 chat 要 light/full path
- 为什么研究链会慢
- 为什么评测要隔离运行
- 为什么要做工作台

你如果能把这份文档讲通，基本已经能扛住大部分面试官的深入追问。
