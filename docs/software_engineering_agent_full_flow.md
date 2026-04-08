# Software Engineering Agent 完整流程说明（最小操作级 + 数据流）

## 1. 文档目的

这份文档面向实现和讲解两个目标：

1. 解释当前 AgentHub 中 `software_engineering` 智能体一次任务从输入到结束的完整执行链路。  
2. 把每一步拆到“最小操作级别”，明确输入、输出、状态变化、工具调用、数据落点、异常分支。  

本文严格基于当前仓库代码实现，不是概念设计。

---

## 2. 入口与核心组件

## 2.1 前端入口

- 页面：`frontend/src/pages/SoftwareEngineeringPage.vue`
- API 封装：`frontend/src/services/api.ts` 中 `streamSoftwareEngineering(...)`
- 流式协议：SSE（`text/event-stream`）

用户点击“开始执行”后，前端发送 payload：

- `session_id`
- `task`
- `mode`（`requirement_to_code` / `feedback_to_fix`）
- `user_id`
- `verify_command`（可空）
- `allow_modify_tests`
- `allow_install_dependency`
- `allow_network`
- `max_iterations`
- `working_directory`（可选）

## 2.2 后端入口

- 路由：`backend/app/api/routes/software_engineering.py`
- 流式接口：`POST /api/software-engineering/stream`
- 同步接口：`POST /api/software-engineering`
- 历史接口：`GET /api/software-engineering/history*`

## 2.3 运行时与平台底座

- Orchestrator：`backend/app/platform/runtime/orchestrator.py`
- Runtime 实现：`backend/app/apps/software_engineering/runtime.py`
- 数据模型：`backend/app/apps/software_engineering/models.py`
- 内置工具：`backend/app/apps/software_engineering/tools.py`
- Manifest（权限、能力、profile）：`backend/app/apps/software_engineering/manifest.py`

---

## 3. 一次任务的端到端主链路

下面按时序拆解每个最小操作。

## Step 0：前端提交任务

最小操作：

1. `submitTask()` 收集页面表单字段。
2. 调用 `streamSoftwareEngineering(payload, onEvent)`。
3. 前端建立 SSE 读取器，逐块解析 `data: {...}` 事件。

输入：

- 用户任务描述 + 约束开关。

输出：

- 持续事件流 `RunEvent[]`（status/tool_call/tool_result/message_done/done）。

落点：

- 当前页面内存态 `currentRun`（events、patches、executions、final_report...）。

---

## Step 1：路由层标准化请求

最小操作：

1. `SoftwareEngineeringRequest` 做字段校验。
2. `_to_runtime_payload(...)` 序列化成内部 JSON 字符串。
3. `orchestrator.stream_app(...)` 启动 runtime。

输入：

- HTTP JSON。

输出：

- 统一 runtime 输入字符串（避免上层字段耦合到 runtime）。

---

## Step 2：Orchestrator 构建运行环境

最小操作：

1. 读取 app manifest（`software_engineering`）。
2. 构建 ToolRegistry：
   - 注册 SE 内置工具：`repo_search_tool` / `file_read_tool` / `patch_write_tool` / `command_run_tool` / `dependency_tool`。
   - 若启用 MCP，自动发现并注册 `mcp_*` 工具适配器。
3. 构建 ContextBuilder（history/memory/rag/notes provider）。
4. 构建 ToolExecutor（含 trace 记录）。
5. 组装 RuntimeBuildContext 并实例化 `SoftwareEngineeringRuntime`。

输入：

- `app_id/session_id/user_id`。

输出：

- 带完整能力依赖的 runtime 实例。

关键点：

- `software_engineering` 是“平台内新增应用”，复用统一模型、memory、rag、mcp、skills、trace 体系。

---

## Step 3：Runtime 初始化与黑板创建

最小操作：

1. `stream(user_input)` 解析 JSON（支持普通 JSON / fenced JSON / 文本中嵌入 JSON）。
2. `_build_blackboard(...)` 创建 `Blackboard`：
   - `mode/task_goal/constraints/state/iteration/...`
3. 创建 `ToolContext`：
   - `app_id/session_id/user_id/trace_id`
   - `metadata` 注入执行约束（`allow_install_dependency/allow_network/...`）。
4. 写入历史消息：`history_service.add_user_message(...)`。
5. 发首个事件：`STATUS: Coordinator INIT Task initialized`。

输入：

- runtime payload。

输出：

- 任务态黑板（Blackboard）+ 工具上下文（ToolContext）。

---

## Step 4：状态机主循环

状态机：

- `INIT -> PLANNING -> RETRIEVING -> CODING -> RUNNING -> (SUCCESS | DIAGNOSING)`
- `DIAGNOSING -> (RETRIEVING | CODING | RUNNING | SUCCESS | FAILED)`

循环条件：

- 未成功/失败 且 `iteration < max_iterations`。

注意：

- `iteration` 在进入 `CODING` 前自增（代表一次编码迭代）。

---

## 4. 各阶段最小操作与数据流

## 4.1 PLANNER 阶段

最小操作：

1. 根据 `se.plan` profile 通过 ContextBuilder 组装 prompt。
2. 注入 skill 信息（stage=`se.plan`）。
3. 调模型，解析 JSON 为 `TaskPlan`。
4. 若模型未给 steps，则填充 3 条 fallback steps。
5. 若用户没强制 verify command，可被 planner 建议覆盖（并做 sanitize）。
6. 更新黑板：
   - `board.plan = plan`
   - `board.state = RETRIEVING`
7. 写 task memory + trace + status 事件。

输入：

- task/constraints/context/skills/tool specs。

输出：

- 结构化 plan（goal/summary/modules/steps/verify_command）。

---

## 4.2 RETRIEVER 阶段

最小操作：

1. 调模型生成 `queries/focus_files/mcp_actions` 建议。
2. 对每个 query：
   - `repo_search_tool`
   - 对命中文件再 `file_read_tool`
   - 生成 `RetrievedSnippet`
3. 若有 `mcp_actions`，执行最多 2 个 MCP 工具并回收文本片段。
4. 若 RAG profile 开启，调用 `rag_service.retrieve(...)` 补充片段。
5. 更新黑板：
   - `board.retrieved_context = snippets[:12]`
   - `board.state = CODING`
6. 写 task memory + trace + status。

输入：

- plan + recent failures + mcp tool list。

输出：

- 可供 Coder 使用的检索上下文片段集合。

---

## 4.3 CODER 阶段

最小操作：

1. 构建 `se.code` prompt（goal + constraints + plan + failures + retrieved_context + skills）。
2. 调模型解析 JSON，读取：
   - `edits[]`
   - `verify_command`
   - `summary`
3. verify_command 处理：
   - 若用户手填，则锁定不覆盖。
   - 若模型建议不合理（例如需求任务给出全量 unittest），会 sanitize 成 fallback。
4. 若 `edits` 为空：
   - requirement 模式会进行一次 strict retry（强制返回 JSON edits）。
   - 模型调用错误会直接 `FAILED`（快速失败，不再静默循环）。
5. 若有 edits：
   - 调 `patch_write_tool` 应用补丁。
   - 写入 `board.patch_history`。
   - `board.state = RUNNING`
6. 若无 edits 且非致命错误：
   - `board.state = RETRIEVING`（避免“零改动反复跑验证”）。
7. 写 task memory + trace + status。

输入：

- 计划 + 检索上下文 + 失败历史 + 约束。

输出：

- 代码补丁（文件内容替换/追加）和下一步验证命令。

---

## 4.4 RUNNING（Executor）阶段

最小操作：

1. 调 `command_run_tool` 执行 `verify_command`。
2. 记录 `ExecutionRecord`（exit/stdout/stderr/duration...）。
3. 缺依赖检测：
   - 仅在 `allow_install_dependency && allow_network` 下启用。
   - 从 stderr 匹配 `No module named ...` 提取模块名。
4. 依赖修复分支：
   - 先构建候选包名：
     - 原模块名
     - 别名映射（如 `skimage -> scikit-image`）
     - 下划线转连字符
   - 优先遍历 MCP 安装工具（工具名匹配 `mcp_*install_package*`）。
   - 参数自动适配：`package_name` / `package` / 第一个必填参数。
   - 失败后从返回文本抽取 hint（`did you mean / please install / pip install`）动态扩展候选。
   - MCP 不行再 fallback 到本地 `dependency_tool`（`python -m pip install ...`）。
   - 安装成功后发状态并返回 RUNNING，让主循环再次执行验证命令。
5. 非依赖分支：
   - exit_code=0：
     - 若 requirement 模式但没有 patch，回 RETRIEVING 要求生成真实改动。
     - 否则 `SUCCESS`。
   - exit_code!=0：进入 `DIAGNOSING`。

输出：

- 验证结果 +（可选）自动依赖修复动作。

---

## 4.5 DIAGNOSER 阶段

最小操作：

1. 用 `se.diagnose` prompt 分析最新执行失败。
2. 可执行最多 2 个 MCP 诊断动作，追加上下文片段。
3. 解析 `next_state/reason/failure_type/proposed_action`。
4. 若模型未给明确 next_state，用启发式推断：
   - `no module named` 且允许安装 -> RUNNING
   - syntax/assert/traceback -> CODING
   - file not found -> RETRIEVING
5. 卡死保护：
   - 重复失败且无有效 patch，强制 RETRIEVING。
   - 多轮 identical failure，直接 FAILED。
6. 更新黑板 + memory + trace + status。

---

## Step 5：收敛与结果固化

最小操作：

1. 生成 final report（模型生成；失败时 fallback 模板）。
2. 采集最终代码文件（从 patch_history 对应路径读取）。
3. 写 assistant history。
4. 写 memory（final fact）。
5. 发 `message_done`（含 final_report、patches、executions、final_code_files、iteration_count）。
6. 发 `done`。
7. 持久化 run 记录到 `se_run_store`（完整事件与轨迹）。

---

## 5. 核心数据结构与数据流向

## 5.1 Blackboard（运行时共享状态）

主要字段：

- 任务输入：`mode/task_goal/constraints`
- 执行状态：`state/iteration`
- 过程产物：`plan/retrieved_context/patch_history/execution_history/diagnosis_history`
- 质量保护：`failed_attempts`
- 可观测：`trace`
- 结果：`final_result/final_report`

流向：

- Planner 写 `plan`
- Retriever 写 `retrieved_context`
- Coder 写 `patch_history`
- Executor 写 `execution_history`
- Diagnoser 写 `diagnosis_history`
- Final 阶段读取所有字段汇总输出

## 5.2 ToolContext（工具执行上下文）

关键元数据：

- `repo_root`
- `allow_modify_tests`
- `allow_install_dependency`
- `allow_network`

作用：

- 工具层约束执行权限（例如 dependency_tool 会检查安装与网络开关）。

## 5.3 事件流（SSE）

事件类型：

- `status`
- `tool_call`
- `tool_result`
- `error`
- `message_done`
- `done`

前端感知：

- 中间过程面板：`status/tool_call/tool_result`
- Patch/Diff 面板：由 `patch_write_tool` 的结果增量更新
- 执行日志面板：由 `command_run_tool` 结果增量更新
- 最终报告：`message_done.final_report`

---

## 6. 持久化与可观测落点

## 6.1 历史消息（History）

- 写入时机：
  - 任务开始：user message
  - 任务结束：assistant final report

## 6.2 Memory

- 过程记忆：每个阶段写 working memory（summary）
- 结果记忆：结束写 fact（任务完成状态、迭代数、patch 数）

## 6.3 Trace

- ToolExecutor 调用工具时写 trace
- runtime `_trace_step` 记录阶段摘要到 `board.trace`

## 6.4 运行归档

- `SERunStore.save_run(...)` 保存：
  - constraints/plan/patches/executions/diagnoses/trace/events/final_code_files/final_report

---

## 7. 关键分支与边界行为

## 7.1 用户是否指定 verify_command

- 指定了：runtime 视为“用户强约束”，Planner/Coder 不覆盖。
- 未指定：runtime 自动默认并允许 Planner/Coder 提议（带 sanitize）。

## 7.2 需求任务的默认验证命令

- requirement：默认 `python -m compileall .`
- feedback/fix：默认 `python -m unittest discover -s tests -p "test_*.py"`

## 7.3 0 patch 保护

- 即便验证通过，如果 requirement 模式下 `patch_history` 为空，也不会直接 SUCCESS，而是回 RETRIEVING 要求生成真实改动。

## 7.4 模型不可用保护

- Coder 调模型失败时会直接进入 FAILED，并把错误写进状态消息，不再静默循环。

## 7.5 依赖安装权限边界

- 必须同时满足：
  - `allow_install_dependency = true`
  - `allow_network = true`
- 否则缺包只会作为普通失败进入诊断，不执行安装。

---

## 8. 一次“缺依赖自动修复”最小链路示例

1. Coder 生成 patch 引入 `import skimage.metrics`。  
2. Executor 跑 `verify_command`，stderr 出现 `No module named 'skimage'`。  
3. `_extract_missing_dependency` 提取模块名 `skimage`。  
4. `_build_dependency_candidates` 生成候选：`["skimage", "scikit-image"]`。  
5. 优先调用 MCP 安装工具（若存在），先装 `skimage`。  
6. 若失败，从结果文本抽取 hint（`Did you mean scikit-image`），加入候选。  
7. 继续尝试 `scikit-image`。  
8. 安装成功后发状态 `Dependency installed (...)`，返回 RUNNING。  
9. 主循环再次执行同一 `verify_command`。  
10. 通过则 SUCCESS；失败则 DIAGNOSING。  

---

## 9. 你在前端能直接观察到什么

1. `中间过程`：可以看到状态机流转（Planner -> Retriever -> Coder -> Executor -> ...）。
2. `Patch / Diff`：每次 `patch_write_tool` 的落地文件与 diff。
3. `执行日志`：每次 `command_run_tool` 的 exit code/stdout/stderr。
4. `最终代码`：`message_done.final_code_files` 聚合输出。
5. `最终报告`：任务总结与结果状态。

---

## 10. 这套实现当前的“完整度定位”

已具备：

- 多角色动态协作（Planner/Retriever/Coder/Executor/Diagnoser）
- 非固定编排闭环（失败后可回检索、回编码、回执行）
- 约束驱动执行（verify/install/network/test-modify）
- 自动依赖修复（MCP优先 + 本地fallback + 名称hint）
- SSE 全过程可视化
- run 归档 + memory/history/trace 集成

仍是工程化 MVP（不是全自动大规模改仓系统）：

- 安装触发目前主打 `No module named` 类错误
- 仓库检索策略是轻量文本检索，不是语义代码图检索
- patch 是“全文件写入风格”，不是 AST 级编辑器

---

## 11. 快速定位索引（按文件）

- 前端页面：`frontend/src/pages/SoftwareEngineeringPage.vue`
- 前端流式 API：`frontend/src/services/api.ts`
- 后端路由：`backend/app/api/routes/software_engineering.py`
- 应用 manifest：`backend/app/apps/software_engineering/manifest.py`
- runtime 主流程：`backend/app/apps/software_engineering/runtime.py`
- SE 工具集：`backend/app/apps/software_engineering/tools.py`
- orchestrator 装配：`backend/app/platform/runtime/orchestrator.py`
- MCP 工具适配：`backend/app/platform/tools/mcp_adapter.py`
- MCP 连接管理：`backend/app/platform/protocols/mcp/manager.py`

