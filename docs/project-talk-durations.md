# AgentHub 不同时长讲稿

这份文档给你三套版本：
- `3 分钟`
- `10 分钟`
- `20 分钟`

使用建议：
- 自我介绍后被要求“简单介绍一个项目”，用 `3 分钟`
- 一面 / 二面技术面试官要求“展开讲项目”，用 `10 分钟`
- 深挖环节、主管面、复盘式面试，或面试官明确说“详细讲讲这个项目”，用 `20 分钟`

---

## 1. 3 分钟版本

### 目标
让面试官快速知道：
- 这不是 demo
- 这是平台
- 你做了哪些核心能力
- 工程含量在哪

### 讲稿
我最近做的核心项目叫 `AgentHub`，它是一个自研的多智能体应用平台，不是单一聊天机器人或者几个 Agent demo 的拼接。  

我做这个项目的出发点是，很多 Agent 项目一开始都能很快做出一个 demo，但随着能力变多，就会出现一个问题：模型调用、上下文处理、工具、知识检索、记忆、外部能力接入都和具体应用写死在一起，后面很难复用，也很难扩展成多个智能体应用。  

所以我这个项目先做平台底座，再做具体应用。平台层统一实现了模型层、上下文工程、Memory、RAG、MCP、Skills、工具执行和运行时，然后在这个共享底座上落地了两个应用：一个是聊天助手，一个是深度研究助手。  

这个项目里我重点做了四条主线能力。  

第一条是 `Memory`。我做了 working、episodic、semantic、文档型 perceptual 和记忆图谱，还支持冲突处理、遗忘策略、Qdrant 检索和 Neo4j 图后端，并做了 memory eval。  

第二条是 `RAG`。我打通了从文本、文件、URL 导入，到 parse、chunk、embedding、Qdrant 入库，再到 hybrid retrieval、MQE、HyDE、结构化引用和 answer with sources 的完整链路。  

第三条是 `MCP`。我支持本地 `stdio` 和远程 `streamable_http` 两类 MCP server，并把 MCP tools 适配到平台内部 ToolRegistry，让 agent 能真正调用外部能力。  

第四条是 `Skills`。我做了文件型 `SKILL.md` 技能系统，支持 references、scripts、assets，技能会按 app 和 stage 注入到 runtime。  

除了功能本身，我还给这些能力都做了前端工作台和评测，包括 Memory、RAG、MCP、Skills、Context 的工作台，以及对应的 eval。  

如果总结这个项目的价值，我会说它的核心不在于“做了一个聊天应用”，而在于我把多 Agent 平台里最关键的几条能力链路做成了可运行、可复用、可解释、可评测的工程闭环。

---

## 2. 10 分钟版本

### 目标
让面试官对项目形成完整认知，并开始相信你真的做过平台层工作。

### 讲稿
我最近做的项目叫 `AgentHub`，它是一个自研的多智能体应用平台。  

这个项目的核心目标不是做一个更强的聊天机器人，而是搭一套统一的平台底座，让不同的 Agent 应用都能在这个底座上运行。因为我发现单 Agent demo 最大的问题是能力都耦合在应用内部，后面一旦增加第二个、第三个 Agent，边界就会越来越乱。  

所以系统上我一开始就把它分成了平台层和应用层。  

平台层包括：  
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

应用层目前有两个：  
- `chat`，是通用聊天入口  
- `deep_research`，是研究型 workflow agent  

先说聊天助手。聊天助手不是简单把用户输入丢给模型，而是会先写 history，再构建 `ContextBuildRequest`，然后 ContextBuilder 按 profile 决定要不要拉 history、memory、rag、notes，再做预算、去重、压缩和结构化，最后形成 prompt。系统提示里还会注入 skills，比如通用问答、工具使用规范、证据约束。如果模型输出工具调用，再走 ToolExecutor；如果工具是 MCP 派生工具，就会通过 MCP adapter 去调用外部能力。最后回答返回后，再异步做 memory 写入和 consolidation。  

再说深度研究助手。它是 workflow 型，不是单轮问答。流程是：用户给 topic，planner 先生成多个研究任务；每个任务调用 search 工具拿资料；然后 summarizer 结合搜索结果和上下文生成任务总结；任务总结会写到 notes、memory 和 session knowledge；最后 reporter 汇总这些任务结果生成最终报告。整个过程中前端还能看到 task、citation、report、历史研究记录。  

我重点做了四条平台能力主线。  

`Memory` 这条线，我做的是平台级长期状态层，不是聊天历史缓存。它支持 working、episodic、semantic、文档型 perceptual 和记忆图谱。写入时会做 extraction、candidate 生成、冲突处理、embedding 写入和图后端写入；检索时支持 lexical、vector 和 graph recall，还能结合 importance、type、recency 做排序。Memory 和 History 是严格分开的：History 记录原始消息，Memory 记录提炼后的长期状态。  

`RAG` 这条线，我做了完整的 ingestion 和 retrieval pipeline。知识输入支持文本、文件、URL 以及生成内容沉淀。导入之后会 parse、chunk、做 embedding、写 SQLite 和 Qdrant。检索时按 scope 规划访问边界，再做 lexical / vector / hybrid retrieval、query rewrite、MQE、HyDE、rerank 和结构化 citations。最后通过 ContextBuilder 进入模型，而不是直接粗暴拼接 prompt。  

`MCP` 这条线，我把它作为协议接入层来做。平台支持 `stdio` 和 `streamable_http` 两类 MCP server。MCPManager 负责 server config、连接和 catalog，client 负责真正握手和调用，adapter 负责把 MCP tools 转成平台内部工具。前端还有 MCP 工作台，可以粘配置、预检、启停、删除和直接测试调用。  

`Skills` 这条线，我把 skill 做成了文件型系统，而不是硬编码 Prompt。每个 skill 有 `SKILL.md`、references、scripts、assets，运行时会按 app 和 stage 解析生效的 skill，然后把 prompt fragment 和资源按需注入。  

另一个我觉得比较有工程价值的点是，我给这些能力都做了工作台和评测。  
- Memory 有检索、图关系、评测  
- RAG 有导入、检索、回答、评测  
- MCP 有配置、catalog、调用测试  
- Skills 有 catalog、resolve、eval  
- Context 有 explain、eval  

最后我还做了一轮性能优化。聊天现在支持 light/full context path，简单对话走轻量链路；memory 后处理和 research 的一部分后处理改成后台执行；模型调用层用了连接复用；RAG 做了短 TTL 检索缓存。  

如果面试官问我这个项目最强的地方是什么，我会回答：这个项目最核心的不是某个应用功能多炫，而是我把多 Agent 平台里几条最难的能力链都做成了平台级闭环，而且具备可复用、可解释、可评测和可优化的基础。

---

## 3. 20 分钟版本

### 目标
在主管面、深挖环节、终面或长时间技术交流里，把平台设计、链路细节、权衡和工程能力完整讲透。

### 讲稿
我这个项目叫 `AgentHub`，它是一个自研的多智能体应用平台。  

我做它的原因是，很多 Agent 项目其实只有一个应用场景，一开始功能都写在一起，比如模型调用、知识检索、记忆、工具、协议接入、提示词都堆在一个模块里。这种方式做 demo 很快，但只要你想扩到第二个、第三个 Agent，问题就会出现：能力边界不清，组件之间耦合严重，不同 Agent 之间的数据和权限容易污染，也很难统一调试、评测和优化。  

所以我一开始就没有把目标定义成“做一个聊天助手”，而是定义成“做一个平台 + 两个内置应用”。  

系统上我分成了平台层和应用层。  

平台层负责：
- 统一模型层
- 会话历史
- Context Builder
- Memory
- RAG
- MCP
- Skills
- Tool Registry / Executor
- Runtime / Orchestrator
- App Registry
- Trace / Eval

应用层目前有两个内置应用：  
`chat` 和 `deep_research`。前者负责验证通用聊天、多轮上下文、记忆和知识增强；后者负责验证 workflow 型 Agent，包括任务规划、检索、任务总结、最终报告和归档。  

如果先讲运行时，聊天请求进入系统后的链路是这样的：  
前端提交 `message + session_id + user_id`，API 层校验后交给 orchestrator，orchestrator 根据 app manifest 找到对应 runtime factory，组装 model client、history service、memory service、RAG service、MCP tools、skills runtime 和 context builder。  

运行时先把 user message 写进 history，然后创建 `ContextBuildRequest`。这一步并不是死板地把所有数据源都查一遍，我给 chat 做了 light/full path：简单对话默认只查必要的 history 和 memory，如果看起来像文档/知识型请求，才启用更重的 RAG。接着 ContextBuilder 会按 profile 里的 provider order 来 gather 数据，再做 source budget、去重、压缩和结构化。这个结果再和 system prompt、tool prompt、active skills 一起组成最终模型输入。  

如果模型输出的是工具调用，我会 parse 出 tool call，然后走 ToolExecutor。Tool 可以是内置工具，也可以是 MCP 派生工具。如果是 MCP tool，会经过 MCP adapter 调外部 server。工具结果再以 tool result 的形式回到消息列表里，模型继续生成最终回答。最后 assistant answer 返回前端，同时后台异步写入 memory 和记忆整合。  

deep_research 这条链更复杂，它不是单轮回答，而是 workflow。用户给一个 topic，planner 先生成多个互补任务；然后每个任务发 search 工具调用拿资料；summarizer 结合搜索结果和上下文输出任务总结；这些总结会写 notes、memory 和 session knowledge；最后 reporter 聚合这些任务结果生成 markdown 报告。这个过程既有工具调用，也有上下文构建，也有技能注入，还会产出研究归档和历史记录。  

接下来我分四条能力主线来讲。  

第一条是 `Memory`。  
我做的不是简单的会话缓存，而是平台级长期状态系统。里面有 working、episodic、semantic、文档型 perceptual 和记忆图谱。working 记录短期状态，episodic 记录事件，semantic 记录稳定事实，perceptual 记录文档感知结果，graph 记录实体关系。  

写入时，系统会先做 heuristic 或 LLM extraction，得到候选记忆，再做 conflict resolution，比如用 canonical key、checksum 和 confidence 来判断是合并、覆盖还是标记冲突。然后会把记录写到 SQLite，embedding 写到 Qdrant，关系写到本地图或 Neo4j。  

检索时，ContextBuilder 的 memory provider 会按 `app_id / user_id / session_id` 和 profile 范围发起 recall，组合 lexical、vector 和 graph recall，再结合 importance、memory type、recency、access count 做排序。最后返回 packets 给 ContextBuilder。  

第二条是 `RAG`。  
RAG 这条线我做的是平台级外部知识系统。它支持文本、文件、URL 和 agent 生成内容导入。  

文本导入时，会先构建 `Document`，然后 parse、chunk、补 metadata、embedding，再写 SQLite 和 Qdrant。文件上传也类似，只是会先经过 parser，URL 则会先 fetch 再 parse 网页内容。research 的 task summary 和 final report 也能沉淀为 session temporary knowledge。  

检索时，我会先做 scope 规划，区分 session temporary、user private、app shared、system public。之后做 lexical search、vector search、hybrid merge，再按需要做 query rewrite、MQE、HyDE 和 rerank，最后产出 structured citations，再交给 ContextBuilder 和模型。  

我之所以强调要把 RAG 和 Memory 分开，是因为它们解决的是两类完全不同的问题。Memory 存的是用户和系统内部状态，RAG 存的是外部知识文档。如果混在一起，边界会非常乱。  

第三条是 `MCP`。  
MCP 我不是把它当“另一套工具”，而是把它当协议接入层。平台当前支持 `stdio` 和 `streamable_http` 两类 server。本地 `stdio` 适合跑社区 server 或 demo server，远程 `streamable_http` 适合接官方或托管服务。  

在结构上，MCPManager 负责 server 配置、连接和 catalog；client 负责真正的工具/资源/提示词调用；adapter 负责把 MCP tools 转成平台内部 ToolRegistry 能消费的工具。也就是说，MCP 和 ToolRegistry 是上下游关系，不是同一层。  

前端 MCP 工作台还支持粘 JSON 配置、预检、启停、删除、看 tools/resources/prompts 和直接测试调用。这样不仅能运行，还能方便验证和调试。  

第四条是 `Skills`。  
Skills 这块我没有把它做成几段硬编码 Prompt，而是做成文件型 skill system。每个技能目录下有 `SKILL.md`，还可以带 references、scripts、assets。平台启动时会扫描 skill 目录，解析 metadata 和正文，注册成 `SkillBundle`。app manifest 里可以声明 `SkillBinding`，指定某个 stage 生效哪些技能。运行时再按 `app_id + stage` resolve 生效 skill，并把它们的 prompt fragment、资源等按需注入。  

除了这四条能力线，我觉得项目里另一个很重要的点是 `ContextBuilder`。它其实是平台里的中枢。history、memory、rag、notes、inline packets 都不是直接进模型，而是先转成 context packets，再由 ContextBuilder 统一做来源选择、预算分配、去重、压缩和结构化。最近我还补了 Context 工作台，可以 explain 每次上下文的来源、budget 和压缩结果，也能跑 context eval。  

最后讲两个工程向的点。  

第一是评测。我给 Memory、RAG、Skills、Context 都做了离线 eval。比如 Memory 有 recall、precision、pollution rate、conflict resolution quality；RAG 有 recall、precision、MRR、leakage rate、source coverage；Skills 和 Context 也有各自的解析和覆盖率指标。虽然这些不是线上 KPI，但足够作为内部质量回归。  

第二是性能优化。聊天一开始其实很慢，因为它默认走了完整平台链路：history、memory、rag、后处理都同步跑。所以后面我做了 light/full context path、provider 短路、memory 后处理异步化、模型 HTTP 连接复用和 RAG 短 TTL 缓存，简单聊天的体感延迟显著下降。deep_research 这条链现在仍然比较慢，但我也已经把 memory/RAG 沉淀、归档这些后处理移到后台，并且裁剪了任务数量和阶段 token 上限。  

如果我要总结这个项目的工程价值，我会说它不是几个 Agent 页面，而是一个真正拆清楚能力边界、运行时边界、数据边界和调试边界的平台工程。它最能体现的不是 Prompt 能力，而是平台设计、能力抽象、链路治理、评测和优化能力。

---

## 4. 讲稿使用建议

### 如果面试官打断
不要硬讲完。立刻切到对方关心的那条主线，比如：
- “如果您想听 Memory，我可以先展开讲记忆链路。”
- “如果更关注工程实现，我可以直接从运行时和平台分层开始讲。”

### 如果面试官很关注业务
就少讲目录，多讲：
- 为什么要做平台
- 为什么这两个应用能验证平台能力
- 用户能感知到什么

### 如果面试官很关注技术
就多讲：
- 分层
- 数据流
- 边界
- 异常处理
- 评测
- 性能优化
