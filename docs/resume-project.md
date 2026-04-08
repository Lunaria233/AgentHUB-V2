# AgentHub 项目简历写法

## 一句话版本
自研多智能体应用平台 `AgentHub`，统一实现模型网关、上下文工程、Memory、RAG、MCP、Skills 与多应用运行时，落地聊天助手与深度研究助手两个内置 Agent 应用。

## 项目名称建议
- `AgentHub：自研多智能体应用平台`
- `AgentHub：面向多 Agent 应用的统一平台底座`

## 简历中的项目定位
这个项目不建议写成“做了一个聊天机器人”或“做了几个 Agent Demo”，而应写成：

- 一个自研的多智能体应用平台
- 平台层负责统一能力底座
- 应用层承载不同 Agent 应用
- 当前已落地 `聊天助手` 和 `深度研究助手`

## 简历版项目简介
设计并实现 `AgentHub` 多智能体应用平台，围绕统一模型层、上下文工程、长期记忆、检索增强、MCP 协议接入、Skills 运行时和事件流工作流，构建可复用的 Agent 基础设施，并落地聊天助手与深度研究助手两个内置应用。

## 推荐写法一：标准项目描述
### AgentHub｜自研多智能体应用平台
- 设计并实现统一 Agent 平台底座，抽象模型网关、会话历史、工具执行、上下文构建、Memory、RAG、MCP、Skills 与应用注册机制，支持多 Agent 应用共享基础设施。
- 实现平台级 Context Builder，统一编排 history、memory、notes、RAG、search evidence 等上下文来源，支持按应用与阶段配置 profile、budget、去重、压缩和来源优先级。
- 实现完整 V1 Memory 系统，支持 working / episodic / semantic / 文档型 perceptual memory、graph memory、冲突处理、遗忘策略、Qdrant 检索、Neo4j 图后端及离线评测。
- 实现完整 V1 RAG 系统，打通 `knowledge input -> parse -> chunk -> embed -> Qdrant -> retrieve -> structured sources` 主链，支持文本、文件、URL 导入、混合检索、MQE / HyDE、结构化引用与评测。
- 实现完整 V1 MCP 集成，支持 `stdio` 与 `streamable_http` 两类 MCP server，打通 `server -> client -> adapter -> ToolRegistry -> runtime` 链路，并提供 MCP 工作台支持导入、启停、删除和调用测试。
- 实现 Skills 运行时与文件型技能系统，支持 `SKILL.md`、references / scripts / assets、app/stage 级 skill 绑定与解析、技能评测与工作台检查。
- 落地聊天助手与深度研究助手两个内置应用，支持多轮会话、知识注入、任务分解、流式输出、研究过程回放、研究归档和结果可视化。

## 推荐写法二：偏工程亮点
### AgentHub｜多智能体平台
- 自研平台级 Agent Runtime，统一聊天型与工作流型两类执行路径，支持 streaming event、tool call、trace 与 app manifest 装配。
- 构建 Memory / RAG / MCP / Skills 四类平台核心能力，并通过 app profile 实现“共享底座 + 应用差异化配置”。
- 建立 Memory 与 RAG 的离线评测闭环：Memory 评测覆盖 recall@k、precision@k、pollution rate、conflict resolution quality；RAG 评测覆盖 recall@k、precision@k、MRR、leakage rate、source coverage。
- 实现 MCP 工作台、RAG 工作台、Memory 中心、Skills 工作台、Context 工作台等平台化检查界面，支持能力观测、验证与调试。

## 推荐写法三：偏后端平台
### AgentHub｜LLM Agent Platform
- 设计多 Agent 平台分层架构，拆分 app layer / runtime layer / capability layer / infra layer，避免不同 Agent 之间的工具、知识、记忆和上下文污染。
- 基于 FastAPI + Vue 搭建平台与工作台界面，统一管理聊天、研究、记忆、知识、MCP、技能和上下文调试能力。
- 在性能层面对聊天路径做轻量 profile、连接复用、缓存与异步后处理优化，将简单聊天响应延迟从重链路模式显著压缩到轻量路径。

## 可选技术栈写法
- Backend: Python, FastAPI, SQLite, httpx
- Frontend: Vue 3, TypeScript, Vite
- AI/Agent: OpenAI-compatible LLM API, Context Engineering, RAG, Memory, MCP, Skills Runtime
- Infra/Storage: Qdrant, Neo4j, local file store

## 面试时建议强调的四个亮点
- 不是单 Agent demo，而是“平台 + 多应用”的设计
- `Memory / RAG / MCP / Skills` 都不是概念，而是完整接进运行时
- 做了能力工作台和评测，不只是功能能跑
- 做了上下文治理和性能优化，不只是堆能力

## 不建议夸大的点
- 不要写成“生产级 Agent OS”
- 不要写成“企业级多租户平台”
- 不要写成“全自动 Agent 协作网络”
- Skills 现在是完整 V1，但不是技能市场
- MCP 现在是 V1 完整，但不是覆盖所有 transport

## 简历中的可量化表述建议
- 完成 `2` 个内置 Agent 应用：聊天助手、深度研究助手
- 打通 `4` 条平台核心能力主线：Memory、RAG、MCP、Skills
- 构建 `5` 个能力工作台：Memory / RAG / MCP / Skills / Context
- 建立 `2` 套离线评测：Memory eval、RAG eval

## 最精简版三条 bullet
- 自研多智能体应用平台 `AgentHub`，统一实现模型层、上下文工程、Memory、RAG、MCP、Skills 与多应用运行时，支撑聊天助手与深度研究助手两个内置应用。
- 搭建完整 V1 Memory / RAG 能力链，分别支持多类型记忆、图关系、冲突处理、评测，以及知识导入、混合检索、结构化引用、评测闭环。
- 实现 MCP 与 Skills 平台化接入，支持 `stdio / streamable_http` MCP server、文件型 `SKILL.md` 技能包、app/stage 级装配和多工作台调试。
