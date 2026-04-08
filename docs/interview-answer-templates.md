# AgentHub 面试标准回答模板

这份文档不是问题库，而是“当面试官继续追问时，你可以怎么答”的模板。

建议使用方法：
- 先按自己的话回答
- 如果卡住了，再用这里的结构化模板兜底

---

## 1. 项目定位类模板

### Q：这个项目到底是什么？
#### 回答模板
这个项目本质上是一个自研的多智能体应用平台，而不是单一 Agent demo。  

我把它拆成了两层：平台层和应用层。平台层统一实现模型层、上下文工程、Memory、RAG、MCP、Skills 和运行时；应用层则在这个共享底座上配置不同的 Agent 应用。当前落地了聊天助手和深度研究助手两个应用。

---

### Q：为什么不直接做一个聊天机器人就行？
#### 回答模板
如果只做一个聊天机器人，短期是快，但后面一旦想扩成多个 Agent，就会发现模型、记忆、知识、工具、协议接入、Prompt 都耦合在一起，几乎没法复用。  

我做这个项目的重点不是“某一个应用多强”，而是把这些公共能力平台化，后续新增应用时只做 app 级配置和 workflow，而不是重写一整套底层能力。

---

## 2. 架构类模板

### Q：你是怎么分层的？
#### 回答模板
我分成：
- 平台共享层
- 应用层
- 工作台层

平台共享层包括模型网关、History、ContextBuilder、Memory、RAG、MCP、Skills、ToolRegistry、Runtime、AppRegistry。  
应用层目前有 `chat` 和 `deep_research`。  
工作台层包括 Memory、RAG、MCP、Skills、Context 等能力工作台，用于调试和验证。

---

### Q：为什么要用 manifest + profile？
#### 回答模板
因为平台需要同时满足“共享底座”和“应用差异化”。  

共享底座负责能力存在，manifest/profile 负责能力怎么被某个 app 使用。这样新增 app 时，不需要改平台总控逻辑，只需要声明：
- 用哪个 runtime
- 开哪些 capability
- 用哪些 profile
- 允许哪些工具和 MCP server

---

## 3. chat 链路模板

### Q：聊天请求的完整链路是什么？
#### 回答模板
聊天请求的链路是：
1. 前端提交 `message + session_id + user_id`
2. API 层校验
3. orchestrator 按 app manifest 组装 runtime
4. runtime 先写 history
5. 构建 `ContextBuildRequest`
6. ContextBuilder 拉 history/memory/rag/notes
7. 做 budget、去重、压缩、结构化
8. 组合 system prompt、skills prompt、tool prompt
9. 调模型
10. 如果有 tool call，就走 ToolExecutor/MCP
11. 返回 assistant answer
12. 异步做 memory 写入和 consolidation

这个链路里最重要的是，聊天不是直接 `user_input -> model`，而是走平台级上下文、技能和工具能力。

---

### Q：为什么你说 chat 有 light/full path？
#### 回答模板
因为普通闲聊不应该每次都跑完整平台链路，否则会很慢。  

所以我做了轻量和重型两条路径：
- 简单聊天默认只查必要的 history 和 memory
- 如果是明显的知识型请求，才启用更重的 RAG 路径

这样既能保留平台能力，又不会让所有请求都被重链路拖慢。

---

## 4. research 链路模板

### Q：深度研究助手和聊天助手最大的区别是什么？
#### 回答模板
聊天助手本质上还是 conversation runtime，而深度研究助手是 workflow runtime。  

research 的链路是：
1. planner 拆任务
2. search 拿资料
3. summarizer 做任务总结
4. task summary 写 notes/memory/rag
5. reporter 汇总最终报告

所以它不是单轮生成，而是多阶段、多事件、多产物的工作流。

---

### Q：research 为什么慢？
#### 回答模板
因为 research 不是一次模型调用，而是多阶段 workflow。  

一个 topic 进来之后，会经历任务规划、多个 task 的检索和总结、最终报告生成，而且每一阶段都可能要用上下文构建、RAG、memory、skills。  

我已经做过几轮优化，比如 task 并发、后处理异步化、阶段 token 上限裁剪，但 research 目前仍然比 chat 重很多，这是它的本质决定的。

---

## 5. Memory 模板

### Q：你项目里的 Memory 和 History 有什么区别？
#### 回答模板
History 是原始会话日志，Memory 是提炼后的长期状态。  

History 主要用于最近对话连续性，Memory 主要用于长期偏好、事实、任务结论和关系图谱。  

如果不分开，系统很容易把所有东西都堆成一个模糊池子，后面既难检索，也难治理。

---

### Q：为什么要做 working / episodic / semantic / graph？
#### 回答模板
因为不同类型的信息生命周期不同。  

- working：当前任务短期状态  
- episodic：事件型记忆  
- semantic：稳定事实与偏好  
- graph：实体关系  

如果不分类型，所有信息都按同样方式写入和检索，效果会很差。

---

### Q：你怎么验证 memory 是真的有用？
#### 回答模板
我从两个层面验证。  

第一是功能层面：
- 用不同 `user_id` 写不同偏好
- 再分别提问
- 验证系统能按用户隔离正确召回

第二是评测层面：
- 我做了 memory eval
- 指标包括 recall@k、precision@k、pollution rate、conflict resolution quality

所以它不是“感觉记住了”，而是有功能验证和离线指标支撑。

---

## 6. RAG 模板

### Q：RAG 和 Memory 的区别是什么？
#### 回答模板
RAG 负责外部知识，Memory 负责内部状态。  

RAG 的输入是文档、文本、URL、生成内容，检索的是知识 chunk；  
Memory 的输入是对话、任务、偏好、关系，检索的是长期状态。  

它们最后都能进 ContextBuilder，但来源和职责完全不同。

---

### Q：你的 RAG 具体做到了什么程度？
#### 回答模板
已经做成了完整 V1。  

支持：
- 文本、文件、URL 导入
- parse、chunk、embedding、Qdrant 入库
- lexical / vector / hybrid retrieval
- MQE / HyDE
- rerank
- structured citations
- answer with sources
- scope 隔离
- RAG eval

所以它不是一个“本地 JSON 搜索 demo”，而是完整平台 RAG 主链。

---

### Q：为什么要做结构化 citations？
#### 回答模板
因为如果只给一段答案，不知道它来自哪里，就很难验证。  

所以我要求 RAG 返回：
- doc_id
- title
- chunk_id
- page_or_section
- score
- preview
- visibility

这样不仅前端能展示，也能用于权限控制、调试和 answer with sources。

---

## 7. MCP 模板

### Q：MCP 和 ToolRegistry 的区别是什么？
#### 回答模板
MCP 是外部能力接入协议层，ToolRegistry 是平台内部给 agent 暴露工具的运行时注册层。  

两者关系是：
`MCP server -> MCP client -> MCP adapter -> ToolRegistry -> runtime`

所以 ToolRegistry 可以装内置工具，也可以装 MCP 派生工具，但 MCP 本身还包含 resources 和 prompts，不能被简化成 ToolRegistry。

---

### Q：为什么 MCP 既支持本地又支持外部？
#### 回答模板
因为 MCP server 本身就有两类典型形态：
- 本地 `stdio`
- 远程 `streamable_http`

平台同时支持这两类，可以让接入方式更灵活：
- 本地适合社区 server、开发调试
- 远程适合官方或托管服务

---

### Q：为什么一个 MCP server 会显示 `Method not found`，但工具还能用？
#### 回答模板
因为有些 MCP server 只实现了 tools，没有实现 resources 或 prompts。  

比如 `tools/list` 和 `tools/call` 能正常工作，但 `resources/list` 或 `prompts/list` 返回 `Method not found`。  

这不代表 server 没接上，而是代表它只支持 MCP 三件套中的一部分。平台现在已经把这种情况从“致命错误”降级成“能力不支持”。

---

## 8. Skills 模板

### Q：Skills 和 Prompt Engineering 有什么区别？
#### 回答模板
Prompt Engineering 更像针对某个场景手写提示词；Skills 更像平台里的“行为与资源包”。  

在我的项目里，一个 skill 不只是几句提示，而是：
- `SKILL.md`
- stage config
- references
- scripts
- assets

运行时会按 app 和 stage 动态解析和注入。

---

### Q：为什么要做文件型 `SKILL.md`？
#### 回答模板
因为这样技能不再绑死在代码里。  

文件型技能有几个好处：
- 好维护
- 好扩展
- 更接近真实技能包
- 可以带 references/scripts/assets
- 更适合后面做技能管理和版本化

---

## 9. Context Engineering 模板

### Q：为什么要有 ContextBuilder？
#### 回答模板
因为 history、memory、RAG、notes、skills 这些东西最后都要进模型，但不能让每个 app 自己随便拼。  

ContextBuilder 是平台里的统一入口，负责：
- gather
- source budget
- 去重
- 压缩
- 结构化
- prompt 输出

它的价值在于把上下文从“经验拼接”变成“可治理的系统能力”。

---

### Q：现在的 context engineering 做到什么程度？
#### 回答模板
当前已经是“骨架完整 + 可解释 + 可评测”，但还不是最终上限版。  

已经做了：
- gather/select/compress/structure
- source budgets
- dedupe
- history 压缩
- RAG chunk 裁剪
- explain
- eval

还没继续往上做的是更高级的压缩策略、动态 budget、质量评估闭环和更复杂的 source-aware rerank。

---

## 10. 性能模板

### Q：项目最大的性能问题是什么？
#### 回答模板
最大的问题是平台能力越完整，链路越容易变重。  

尤其是聊天，如果每次都默认跑 history、memory、RAG、后处理，延迟会很差。  

所以后面我做了 light/full path、provider 短路、异步后处理、模型连接复用和 RAG 缓存，先把最影响体验的部分优化掉。

---

### Q：为什么 research 还是慢？
#### 回答模板
因为 research 本质上是多阶段 workflow，不是单次生成。  

它要做任务规划、检索、总结、最终报告，而且每个阶段都可能调用模型。  

现在我已经把一部分后处理放后台了，但真正的瓶颈还包括模型/provider 自身响应速度，所以如果继续优化，我会优先做更激进的 research fast mode 和阶段缓存。

---

## 11. 评测模板

### Q：你这些 eval 真的可靠吗？
#### 回答模板
我会把它定义成“内部质量回归基线”，而不是线上 benchmark。  

它可靠的地方在于：
- 有明确指标定义
- 有隔离运行
- 能稳定发现退化

但我不会把它夸成“系统线上性能”。  

在简历里我会写成：
- “设计并实现 Memory / RAG / Skills / Context 的离线评测工具和指标体系”
而不是：
- “系统性能达到多少多少”

---

## 12. 为什么不直接用现成框架

### Q：为什么不直接用 LangChain、Dify、AutoGen？
#### 回答模板
不是说这些框架不能用，而是我这个项目的目的本来就是做平台级工程能力展示。  

如果直接套现成框架，当然能更快出功能，但我想体现的是：
- 我能否自己定义抽象边界
- 我能否自己把运行时和能力主线接起来
- 我能否自己做能力治理、评测和工作台

所以这个项目本身就是“为了做自研平台而自研”。

---

## 13. 还没做完的部分怎么答

### Q：这个项目还有哪些没做完？
#### 回答模板
如果按 V1 来看，Memory、RAG、MCP、Skills 都已经是完整形态了。  

还没继续往上做的，主要是增强项：
- 更高级的 context engineering
- 更强的 research 性能优化
- 技能管理的更高级能力
- 更强的 MCP resources/prompts 深度集成

我会把它定义成“V1 完整，后续还有增强空间”，而不是“半成品”。

---

## 14. 如果被质疑“是不是做得太大了”

### Q：这个项目会不会太大，不像一个人做的？
#### 回答模板
这个项目确实覆盖面比较广，所以我一直是按主线分阶段推进的。  

我没有一上来就做所有上限，而是先把平台骨架定好，再逐条补：
- 先 Memory
- 再 RAG
- 再 MCP
- 再 Skills
- 再做 Context explain / eval 和性能优化

所以它不是一次性堆出来的，而是一个逐步收口的平台工程。

---

## 15. 最后一句收口模板

如果你觉得一段回答太长，可以用这句收：

**这个项目最核心的不是某个单点功能，而是我把多 Agent 平台里最关键的四条能力主线做成了统一底座，并且让它们具备可运行、可解释、可评测和可优化的工程闭环。**
