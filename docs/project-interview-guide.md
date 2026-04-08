# AgentHub 项目说明与面试深挖材料

## 1. 项目简要介绍
`AgentHub` 是一个自研的多智能体应用平台，不是单一聊天机器人，也不是几个零散 Agent demo 的拼接。它的核心目标是提供统一的 Agent 能力底座，并在其上承载不同类型的智能体应用。

当前平台已经落地两个内置应用：
- `聊天助手`
- `深度研究助手`

平台层已实现的核心能力包括：
- 统一模型网关
- 会话历史与状态持久化
- 上下文工程
- Memory
- RAG
- MCP
- Skills
- 工作流与事件流运行时
- 前端能力工作台

---

## 2. 项目详细介绍

### 2.1 项目定位
这个项目的目标不是做“更聪明的 Prompt”，而是做“更完整的 Agent 平台工程”。

平台层负责：
- 统一抽象能力
- 统一配置
- 统一装配
- 统一权限边界
- 统一观测与调试

应用层负责：
- 定义 app manifest
- 选择启用哪些平台能力
- 配置各自的上下文、记忆、知识、工具、MCP、Skills 策略

### 2.2 当前系统分层
#### 平台共享层
- Model Gateway
- Context Builder
- History Service
- Memory Service
- RAG Service
- MCP Gateway / Manager
- Tool Registry / Executor
- Skill Registry / Runtime
- App Registry / Runtime Factory

#### 应用层
- `chat`
- `deep_research`

#### 工作台层
- 首页 Dashboard
- 聊天页
- 研究页
- RAG 工作台
- 记忆中心
- MCP 工作台
- Skills 工作台
- Context 工作台

---

## 3. 本项目所有功能的全流程、全链路、数据流转

下面按能力和应用拆开讲，每一条都按“输入 -> 中间处理 -> 输出 -> 异常/边界/优化”来写。

### 3.1 聊天助手全链路
#### 入口
前端聊天页输入：
- `message`
- `session_id`
- `user_id`

前端调用：
- `POST /api/chat`
- 或流式接口 `/api/chat/stream`

#### 后端主链
1. API 层校验参数
2. `AppOrchestrator` 根据 `app_id=chat` 找到 manifest
3. 构建运行时：
   - model client
   - history service
   - memory service
   - context builder
   - tool registry
   - MCP tool adapter
   - skill runtime
4. `chat_runtime` 开始执行
5. 写入 user message 到 history
6. 构建 `ContextBuildRequest`
7. 判断是否进入轻量路径
   - 简单问候/普通对话 -> light mode
   - 文档/知识问题 -> full mode
8. `ContextBuilder` 调度 provider：
   - history
   - memory
   - rag（按需）
   - notes（按需）
9. 进行：
   - gather
   - source budget 分配
   - 去重
   - history 压缩
   - RAG chunk 裁剪
10. 形成 prompt
11. 组合 system prompt
   - app prompt
   - tool prompt
   - active skills prompt fragments
12. 调用模型
13. 如果模型输出工具调用标记：
   - parse tool call
   - ToolExecutor 执行
   - 若工具来自 MCP，则走 MCP adapter -> MCP server
   - 工具结果回注消息列表
   - 再次调用模型
14. 得到最终回答
15. 写 assistant answer 到 history
16. 异步做：
   - memory 写入
   - consolidation
17. 返回前端

#### 输出
- `answer`
- 流式消息时是 `message_chunk -> message_done`

#### 用户感知
- 正常对话
- 会记住不同 `user_id` 的偏好
- 打开知识能力时会用 RAG
- 打开 MCP 能力时可调用外部能力

#### 异常与边界
- `user_id` 缺失：chat 当前按设计要求必须带
- provider 返回 malformed payload：包装成更明确的模型错误
- 没有可访问知识：RAG provider 直接短路
- 没有 memory：memory provider 直接短路
- tool 调用失败：返回 tool_result 错误，不直接炸全链

#### 优化点
- light/full context path
- streaming
- memory 后处理异步化
- model HTTP 连接复用
- RAG 检索短路

---

### 3.2 深度研究助手全链路
#### 入口
前端研究页输入：
- `topic`
- `session_id`
- `user_id`

API：
- `/api/research`
- `/api/research/stream`

#### 后端主链
1. API 层接收 topic
2. orchestrator 构建 `deep_research` runtime
3. 写入 history
4. 写入 research working memory
5. `research.plan`
   - build context
   - apply planning skills
   - 调用 planner
   - 生成任务列表
6. 并发执行任务
   - 每个 task 先发 `search` 工具调用
   - search 可走内置 provider 或 MCP 派生工具
   - 产出 raw sources
7. `research.summarize`
   - 将 search result 作为 inline packets
   - build summarize context
   - apply summarize skills
   - 调用 summarizer
8. 每个任务完成后：
   - 写 note
   - 异步写 memory
   - 异步写 generated summary 到 RAG session knowledge
9. `research.report`
   - 将 task summary 聚合成 task_summary packets
   - build report context
   - apply synthesis skills
   - 调用 reporter
10. 异步写：
   - report memory
   - report generated knowledge
   - research archive
   - memory consolidation
11. 返回 final report 与完整 task 数据

#### 输出
- task 列表
- event log
- final report

#### 用户感知
- 不是一次性回答，而是“规划 -> 检索 -> 总结 -> 报告”
- 可查看历史研究
- 可查看 task log / citation / final report

#### 异常与边界
- search provider 无结果：task summary fallback
- 某个 task 异常：不阻塞整个研究 run
- planner/summarizer/reporter 模型失败：都有 fallback
- 后处理失败：后台告警，不阻塞主结果

#### 优化点
- task 并发
- 研究后处理异步化
- summary/report max_tokens 收紧
- generated knowledge 直接沉淀进 session knowledge

---

### 3.3 Memory 全链路
#### 类型
- working
- episodic
- semantic
- perceptual（文档型）
- graph

#### 写入链路
1. chat/research/文档输入触发写入
2. heuristic / LLM extraction
3. 形成 candidate
4. 冲突检测：
   - canonical key
   - checksum
   - confidence
5. 写 SQLite
6. 写 Qdrant embedding
7. 写 Neo4j / 本地图关系

#### 检索链路
1. ContextBuilder 触发 Memory provider
2. 根据 `app_id / user_id / session_id` 和 profile 查范围
3. 组合 lexical / vector / graph recall
4. 按 importance / type weight / recency / access count 排序
5. 返回 packets

#### 异常与边界
- 缺 user_id：chat 不允许扩大到全 app
- graph backend 异常：降级到非图 memory
- embedding backend 异常：降级 lexical

#### 已做优化
- conflict resolution
- forgetting policy
- eval 隔离运行

---

### 3.4 RAG 全链路
#### 输入源
- 文本直接输入
- 文件上传
- URL 导入
- app 预置知识
- agent/generated knowledge

#### Ingestion
1. 解析来源
2. parse
3. structured chunk
4. metadata 填充
5. embedding
6. SQLite store
7. Qdrant vector upsert

#### Retrieval
1. 构建 `RetrievalQuery`
2. scope 规划：
   - session temporary
   - user private
   - app shared
   - system public
3. lexical search
4. vector search
5. hybrid merge
6. MQE / HyDE
7. rerank
8. structured citations
9. 注入 ContextBuilder
10. answer with sources

#### 异常与边界
- 无可访问文档：短路返回空结果
- query scope 无权限：不返回内容，也不泄漏 citation
- vector backend 不可用：降级 lexical

#### 优化
- search cache
- no_accessible_documents 短路
- query rewrite / HyDE / rerank 可按 profile 关闭

---

### 3.5 MCP 全链路
#### 支持的类型
- `stdio`
- `streamable_http`

#### 主链
1. MCP 工作台或配置文件注册 server
2. `MCPConnectionManager` 维护 server config
3. connect / catalog
4. 拉取：
   - tools
   - resources
   - prompts
5. tools 通过 adapter 暴露到 `ToolRegistry`
6. agent runtime 可直接调用这些工具
7. 资源和 prompts 当前可通过 MCP API 调试，后续可继续深接到 context/skills

#### 异常与边界
- server 不支持 resources/prompts：不当成致命错误
- stdio server 命令缺失：预检和状态里提示
- remote URL 不可达：状态里提示

#### 已做优化
- 自定义 server 持久化
- 启停、删除、目录刷新
- 配置预检

---

### 3.6 Skills 全链路
#### 输入
- `skills/<skill_id>/SKILL.md`
- `references/`
- `scripts/`
- `assets/`

#### 主链
1. 启动时扫描技能目录
2. 解析 metadata / stage config / body
3. 注册 `SkillBundle`
4. app manifest 定义 `SkillBinding`
5. runtime 按 `app_id + stage` resolve 生效 skill
6. skill 注入：
   - prompt fragments
   - tool preference
   - references / scripts / assets hydration

#### 异常与边界
- skill 文件缺失或格式错误：跳过并告警
- app 未绑定：不注入

#### 已做优化
- 按需水合
- skills eval
- skills 工作台

---

### 3.7 Context Engineering 全链路
#### 输入源
- history
- memory
- rag
- notes
- inline packets

#### 主链
1. runtime 创建 `ContextBuildRequest`
2. provider 按 profile 顺序收集 source packets
3. `ContextBuilder`：
   - dedupe
   - source budgets
   - select
   - compress
   - structure
4. 产出 sections
5. 产出 prompt
6. trace `context_build`

#### explain / eval
- explain：单次查看这次上下文到底用了什么
- eval：离线测 utilization / dedupe / compression / source diversity

#### 异常与边界
- provider limit=0 时直接短路
- 没有数据来源时也能返回可解释的空上下文

---

## 4. 异常、边界、异常处理、优化、判断、选择、分支

### 4.1 关键边界
- History != Memory
- Memory != RAG
- MCP != ToolRegistry
- Skills != MCP
- app scope / user scope / session scope 必须隔离

### 4.2 关键判断
- chat 是否走 light context path
- 是否启用 RAG
- 哪些来源需要进入 context
- 哪些 memory 应写 working / semantic
- 某个工具是否允许在当前 app 使用
- 某个 MCP server 是否允许对当前 app 暴露

### 4.3 关键异常处理
- 模型接口返回 malformed payload
- 向量库不可用时降级
- 图后端不可用时降级
- MCP server 不支持部分方法时不致命
- research 某个 task 失败不拖垮全 run
- eval 走隔离库，不污染正式数据

### 4.4 关键优化
- model HTTP keep-alive
- chat light context path
- memory 后处理异步化
- research 后处理异步化
- RAG 检索缓存
- no-accessible-documents 短路
- provider 按 limit 短路

---

## 5. 如果拿这个项目投简历，需要准备哪些材料

建议你至少准备下面这些：

### 5.1 一份项目总介绍
内容包括：
- 项目目标
- 平台定位
- 分层架构
- 两个内置应用
- 四条核心能力主线：Memory / RAG / MCP / Skills

### 5.2 一份模块地图
你要能把下面这些文件/目录一口气说出来：
- `backend/app/platform/models`
- `backend/app/platform/context`
- `backend/app/platform/memory`
- `backend/app/platform/rag`
- `backend/app/platform/protocols/mcp`
- `backend/app/platform/skills`
- `backend/app/platform/runtime`
- `backend/app/apps/chat`
- `backend/app/apps/deep_research`

### 5.3 一份接口清单
至少熟悉：
- `/api/chat`
- `/api/research`
- `/api/memory/*`
- `/api/rag/*`
- `/api/mcp/*`
- `/api/skills/*`
- `/api/context/*`

### 5.4 一份数据流图
你至少要能口述：
- 聊天请求如何流转
- research request 如何流转
- memory 如何写入/检索
- RAG 如何导入/检索/引用
- MCP 如何从 server 变成 tool
- skill 如何注入到 app stage

### 5.5 一份评测与指标说明
要准备：
- Memory eval 指标含义
- RAG eval 指标含义
- Skills eval 指标含义
- Context eval 指标含义
- 哪些能作为内部质量指标，哪些不能夸大成“生产性能”

### 5.6 一份性能与优化说明
要能说明：
- 聊天为什么之前慢
- 做了哪些优化
- 哪些优化是平台级的
- 哪些瓶颈还在 provider/model 侧

### 5.7 一份 demo 操作脚本
建议准备一个 5 到 8 分钟 demo 流程：
1. 首页介绍平台
2. chat 演示 memory
3. RAG 导入文本/文件并回答
4. MCP 工作台导入一个 server 并调用 tool
5. deep_research 演示完整流程
6. skills/context 工作台做解释

### 5.8 一份“常见追问答案”
你要能回答：
- 为什么不直接用 LangChain / Dify / AutoGen
- 为什么 Memory 和 RAG 分开
- MCP 和 ToolRegistry 的关系
- Skills 和 Prompt Engineering 的区别
- 为什么要有 ContextBuilder
- 为什么 chat 要有 light path
- 为什么评测要隔离运行

---

## 6. 建议你额外准备的文件
如果真要抗住高强度面试，建议你后面再补：
- 架构图
- 时序图
- 模块依赖图
- 关键 API 示例
- 关键配置说明
- 典型问题与优化记录

---

## 7. 面试时最推荐的讲法
不要从“我写了哪些文件”开始讲。  
建议按这个顺序：

1. 为什么做这个项目
2. 平台和单 Agent demo 的区别
3. 平台分层
4. 两个内置应用如何验证平台能力
5. 四条核心能力主线分别解决什么问题
6. 做了哪些评测与性能优化
7. 还有哪些边界和后续空间

这样最稳，也最像一个真正做平台工程的人。
