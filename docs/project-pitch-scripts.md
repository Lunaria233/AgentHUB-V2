# AgentHub 项目讲稿

## 1. 自我介绍时的项目简要讲稿

### 版本 A：30 秒
我最近做的核心项目叫 `AgentHub`，它不是一个单独的聊天机器人，而是一个自研的多智能体应用平台。这个平台统一实现了模型层、上下文工程、Memory、RAG、MCP、Skills 和多应用运行时，在这个底座上落了聊天助手和深度研究助手两个应用。这个项目最有价值的地方不是“我做了几个 Agent demo”，而是我把 Agent 平台里最核心的能力链路真正跑通了，并且做了调试工作台、评测和性能优化。

### 版本 B：1 分钟
我最近重点做的项目是 `AgentHub`，定位是一个自研的多智能体应用平台。和普通单 Agent 项目不同，它不是只实现一个聊天应用，而是先做统一平台底座，再在上面承载多个智能体应用。  

这个平台里我重点做了几个核心模块：  
- 模型调用层和运行时  
- 平台级上下文工程  
- Memory 系统  
- RAG 系统  
- MCP 协议接入  
- Skills 技能系统  

然后我在这个底座上做了两个应用：一个是聊天助手，一个是深度研究助手。前者更像通用入口，后者是工作流型 Agent，可以做任务规划、搜索、总结、生成最终报告。这个项目比较能体现工程能力，因为我不只是做了功能，还做了评测、工作台、链路解释和性能优化。

### 版本 C：适合面试开场的 90 秒
我最近做的一个项目叫 `AgentHub`，它的核心目标是做一个自研的多智能体应用平台，而不是做一个单点 Agent demo。  

我一开始就把项目拆成两层：平台层和应用层。平台层负责统一能力底座，包括模型层、工具层、上下文工程、Memory、RAG、MCP、Skills、运行时和应用注册；应用层则在这个共享底座上配置出不同的智能体应用。  

当前我已经在这个平台上落了两个内置应用：聊天助手和深度研究助手。聊天助手支持多轮对话、长期记忆、知识注入、工具调用；深度研究助手支持研究任务规划、检索、任务总结、最终报告生成以及研究历史回放。  

这个项目的工程重点在于四条主线能力：Memory、RAG、MCP、Skills。我没有把它们做成概念展示，而是把它们真正接进运行时、前端工作台和评测闭环里。比如 Memory 支持 working / episodic / semantic / graph / 文档型 perceptual，RAG 支持文本/文件/URL 导入、Qdrant 混合检索和结构化引用，MCP 支持本地和远程 server，Skills 支持文件型 `SKILL.md` 加载和阶段化注入。  

如果面试官愿意深入，我通常会继续讲平台分层、四条主能力主线，以及聊天和研究两条链路是如何在这个底座上复用能力的。

---

## 2. 面试里项目简要介绍讲稿

### 版本 A：2 到 3 分钟
这个项目叫 `AgentHub`，我想解决的问题是：现在很多 Agent 项目其实只是一个应用 demo，能力都写死在应用内部，模型、知识、记忆、工具、协议接入、上下文处理都耦合在一起，后面一旦想扩成多个 Agent 应用，就会很难维护。  

所以我这个项目的目标不是只做一个聊天机器人，而是先做一个统一的多智能体平台底座。平台层负责提供公共能力，比如：
- 模型网关
- 上下文工程
- Memory
- RAG
- MCP
- Skills
- 工具执行
- 运行时和应用注册

在这个底座上，我先落了两个应用：  
- 一个是聊天助手，负责做多轮会话、长期记忆和知识增强  
- 一个是深度研究助手，负责多阶段 workflow，包括规划任务、检索资料、生成总结、汇总最终报告

这个项目最核心的地方有四条能力主线。  

第一条是 `Memory`。我做了 working / episodic / semantic / 文档型 perceptual / graph memory，支持冲突处理、遗忘策略、图关系写入、Qdrant 检索和 Neo4j 图后端，还做了独立的 memory eval。  

第二条是 `RAG`。我做了完整的 ingestion 和 retrieval pipeline，支持文本、文件、URL 导入，解析、分块、embedding、Qdrant 入库、混合检索、MQE / HyDE、结构化引用和评测。  

第三条是 `MCP`。我把本地 `stdio` 和远程 `streamable_http` MCP server 都接进来了，做成统一的协议接入层，再通过 adapter 把工具暴露给 runtime。  

第四条是 `Skills`。我做了文件型 `SKILL.md` 技能系统，支持 `references / scripts / assets`，并让技能按 app 和 stage 注入到运行时。  

另外我还给这些能力都做了前端工作台，比如 Memory 中心、RAG 工作台、MCP 工作台、Skills 工作台、Context 工作台，这样不仅能跑，也能调试和解释。  

整体上，这个项目比较能体现我的工程能力，因为它不是拼 demo，而是围绕“平台复用、能力隔离、链路闭环、调试评测、性能优化”来设计和实现的。

### 版本 B：适合技术面试官继续追问的 4 到 5 分钟
如果从系统设计角度讲，这个项目的关键是我从一开始就把“平台能力”和“具体 Agent 应用”分开。  

平台层包含：
- 模型层：负责统一 OpenAI-compatible 接口
- ContextBuilder：负责统一 history、memory、rag、notes、inline packets 的上下文构建
- MemoryService：负责长期状态、偏好、任务事实和图关系
- RAGService：负责外部知识文档的导入、切块、索引、检索和引用
- MCPManager：负责 MCP server 的连接、catalog、tools/resources/prompts
- SkillRuntime：负责技能加载、解析和按阶段注入
- Orchestrator：负责装配 app runtime

应用层只关心自己的 manifest、prompt、profile 和 workflow。  

聊天助手这条链路会走：  
用户输入 -> history 写入 -> ContextBuilder -> 技能注入 -> 模型调用 -> 工具/MCP 调用（如果需要） -> assistant answer -> 异步 memory 写入。  

深度研究助手这条链路更复杂：  
用户给 topic -> planner 生成任务 -> search 工具检索 -> summarize 任务 -> note/memory/rag 异步沉淀 -> reporter 写最终报告。  

这里最难的点不是“调模型”，而是这几条能力线之间的边界要分清楚：  
- History 是原始对话日志  
- Memory 是提炼后的长期状态  
- RAG 是外部知识检索  
- MCP 是协议接入层  
- Skills 是领域行为和阶段策略  
- ContextBuilder 是它们进入模型前的统一编排层  

我后面还做了两件很重要的事情。第一是评测，Memory 和 RAG 都做了独立 eval，Skills 和 Context 也有自己的检查与评测。第二是性能优化，比如 chat 走轻量路径，后处理异步化，模型 HTTP 连接复用，RAG 检索缓存等。  

所以如果面试官问“这个项目最核心的价值是什么”，我会回答：它不是某个应用做得多花哨，而是我把一个多 Agent 平台真正拆成了平台底座和应用层，并让几条核心能力链路都形成了可运行、可解释、可评测的闭环。

---

## 3. 面试里详细介绍项目时的完整讲稿

### 讲法建议
详细介绍时不要一开始就按文件讲。建议按这个顺序：
1. 业务问题和项目目标
2. 平台分层
3. 两个应用怎么验证平台能力
4. 四条核心能力主线
5. 评测、调试、性能优化
6. 边界与后续方向

### 详细讲稿（7 到 10 分钟）
我这个项目叫 `AgentHub`，是一个自研的多智能体应用平台。  

我做它的出发点是：我发现很多 Agent 项目其实只有一个应用，里面把 Prompt、工具、知识检索、记忆、协议接入全都写在一起，这种方式虽然能快速出 demo，但是一旦你想扩成多个 Agent 应用，就会出现几个问题：  
- 能力边界不清  
- 各个 Agent 互相污染  
- 很难调试和复用  
- 很难做评测和性能治理  

所以我这个项目一开始就不是以“做一个助手”为目标，而是以“做一个统一的 Agent 平台底座”为目标。  

系统上我把它分成两层。  

第一层是平台共享层，负责提供统一能力，包括模型网关、会话历史、ContextBuilder、Memory、RAG、MCP、Skills、ToolRegistry、Runtime、AppRegistry、评测和前端工作台。  

第二层是应用层，当前有两个应用。  
一个是聊天助手，它是通用入口，主要验证聊天、多轮上下文、记忆、知识注入和工具调用；  
另一个是深度研究助手，它更像 workflow 型 Agent，用来验证任务规划、搜索、任务总结、最终报告、研究归档和多阶段 context 构建。  

然后我重点做了四条平台能力主线。  

第一条是 `Memory`。  
我没有把 memory 做成简单的聊天历史缓存，而是做成了平台级记忆系统。它支持 working、episodic、semantic、文档型 perceptual 和记忆图谱。写入时会做候选提取、冲突判断、图关系抽取、embedding 写入和图后端写入；检索时支持 lexical + vector + graph recall，再和 importance、memory type、recency 这些因素一起排序。Memory 和 history 是分开的：history 记录原始消息，memory 记录提炼后的长期状态。  

第二条是 `RAG`。  
我做的是完整的 ingestion 和 retrieval pipeline。知识输入支持文本、文件、URL 以及 agent 自己生成的内容。导入之后会 parse、chunk、补 metadata、做 embedding、写入 SQLite 和 Qdrant。检索时按权限 scope 规划，再做 lexical / vector / hybrid retrieval，支持 query rewrite、MQE、HyDE、rerank 和结构化 citations。然后通过 ContextBuilder 注入模型，不是简单把检索结果拼到 prompt 后面。  

第三条是 `MCP`。  
我把 MCP 作为协议接入层来做，不是简单把它当工具集合。当前支持 `stdio` 和 `streamable_http` 两类 server。MCPManager 负责管理 server catalog 和连接，client 负责实际握手和调用，adapter 负责把 MCP tools 映射成平台内部工具。现在前端还有 MCP 工作台，可以导入 server 配置、预检、启停、查看 tools/resources/prompts 和测试调用。  

第四条是 `Skills`。  
Skills 这块我参考了技能包的设计方式，做成文件型 `SKILL.md` 系统，并支持 `references / scripts / assets`。Skill 不是一句 Prompt，而是一个 bundle，包含 prompt fragments、资源、脚本和阶段配置。运行时会按 app 和 stage 解析生效的 skill，再注入到上下文或系统提示中。我还给它做了目录扫描、重载、工作台和 eval。  

在这几条能力之上，`ContextBuilder` 是平台里的中枢。  
所有 history、memory、RAG、notes、inline packets，最后都要通过 ContextBuilder 进入模型。ContextBuilder 负责 gather、budget 分配、去重、压缩、结构化和 prompt 输出。最近我还加了 context explain/eval，可以看到每次上下文到底用了什么来源、占了多少 token、压缩了什么。  

最后，我又补了两块平台质量能力。  
第一块是评测。Memory、RAG、Skills、Context 现在都有各自的 eval，虽然不是线上 benchmark，但已经足够做内部质量回归。  
第二块是性能优化。比如聊天现在有轻量路径，简单问题默认只查必要的 history/memory；模型调用用了连接复用；chat 的 memory 后处理和 research 的归档、memory/RAG 沉淀都改成了异步后台执行；RAG 还做了短 TTL 缓存。  

如果让我总结这个项目的价值，我会说它最核心的不是“做了一个聊天助手”，而是我把一个多 Agent 平台拆成了清晰的层次，并且让几条最关键的能力链路都形成了可运行、可解释、可调试、可评测的闭环。

---

## 4. 面试中讲这个项目时的常见节奏

### 1 分钟
只讲：平台定位 + 两个应用 + 四条能力主线。

### 3 分钟
再加：平台分层、能力边界、评测。

### 5 分钟
再加：chat 链路、research 链路、Memory/RAG/MCP/Skills 的实现方式。

### 10 分钟
再加：ContextBuilder、性能优化、异常处理、为什么这样做、替代方案和权衡。

---

## 5. 建议你练习时重点记住的句子

### 项目定位
这个项目不是单点 Agent demo，而是一个自研的多智能体应用平台。

### 平台价值
我重点做的是共享底座和应用分层，而不是每个 Agent 各写一套。

### 边界划分
History、Memory、RAG、MCP、Skills 各自负责不同的问题，ContextBuilder 负责把它们统一编排进模型。

### 工程亮点
我不只是让功能能跑，还补了工作台、评测和性能优化，让这个项目具备真正的工程闭环。
