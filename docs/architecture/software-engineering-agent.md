# Software Engineering Agent (MVP)

## 1. 目标
在 AgentHub 内新增一个业务应用 `software_engineering`，实现两条主链路：
- Requirement-to-Code
- Feedback-to-Fix

并通过 runtime harness（状态机 + 路由 + 可观测）形成可验证闭环。

## 2. 后端模块
- `backend/app/apps/software_engineering/manifest.py`
- `backend/app/apps/software_engineering/agent.py`
- `backend/app/apps/software_engineering/runtime.py`
- `backend/app/apps/software_engineering/tools.py`
- `backend/app/apps/software_engineering/models.py`
- `backend/app/apps/software_engineering/archive.py`
- `backend/app/api/routes/software_engineering.py`

## 3. Runtime Harness
- Blackboard（共享任务上下文）
- 状态机：`INIT -> PLANNING -> RETRIEVING -> CODING -> RUNNING -> DIAGNOSING -> SUCCESS/FAILED`
- Router：Diagnoser 输出 + 规则兜底决定下一状态
- Trace：每轮记录 agent、状态、摘要
- SSE：前端可见状态事件、工具调用、工具结果、最终报告
- 最终验收：以 `verify_command` 的真实退出码为准

## 4. 工具
应用复用平台 ToolRegistry，并注入 SE 工具：
- `repo_search_tool`
- `file_read_tool`
- `patch_write_tool`
- `command_run_tool`
- `dependency_tool`

此外，MCP 工具会按平台配置自动注入为 `mcp_<server>_<tool>`，并在 Retriever/Diagnoser 阶段可被动态调用。
调用触发后会进入同一条事件流（`tool_call` / `tool_result`），并写入运行历史与 trace。

## 5. 前端入口
- 路由：`/software-engineering/:sessionId?`
- 页面：`frontend/src/pages/SoftwareEngineeringPage.vue`
- 能力：任务输入、约束输入、SSE 过程流、Patch/Diff、执行日志、最终报告、历史运行查看

## 6. API
- `POST /api/software-engineering`
- `POST /api/software-engineering/stream`
- `GET /api/software-engineering/history`
- `GET /api/software-engineering/history/{session_id}`

## 6.1 Skills 与 MCP 的实际接入方式
- Skills：
  - `se.plan` -> `requirement_to_plan`
  - `se.retrieve` -> `tool_use_hygiene`, `source_grounding`
  - `se.code` -> `patch_summary`, `tool_use_hygiene`
  - `se.diagnose` -> `error_summary`
  - `se.report` -> `final_report`, `source_grounding`
- MCP：
  - 通过 ToolRegistry 暴露为标准工具名 `mcp_*`
  - Retriever/Diagnoser 可在 LLM 输出 JSON 中声明 `mcp_actions`，runtime 会执行并把结果转为可检索上下文

如果你导入的是自定义外部 MCP server，需确保该 server 的 `allowed_app_ids` 包含 `software_engineering`。

## 7. Mini Eval Harness
- 目录：`backend/eval/software_engineering`
- 任务：6 个固定 case（Requirement-to-Code + Feedback-to-Fix）
- 模式：
  - `single_loop`（baseline）
  - `multi_agent_dynamic`（完整 harness）
- 指标：
  - success rate
  - average iterations
  - average duration
  - average tool calls
  - task-type success rate

运行命令：

```bash
cd backend
python scripts/run_se_eval.py --mode both
```

可选参数：
- `--limit 2`：仅跑前 2 个 case
- `--keep-workspace`：保留临时 fixture 副本
- `--output app/storage/se_eval/result.json`：保存结果

## 8. 两个最小演示场景

### Demo 1: Requirement-to-Code
前端进入 `软件工程智能体` 页面，输入：

```text
为现有模块新增 CSV 平均值函数，忽略非数字行，并通过验证命令
```

约束示例：
- verify_command: `python -m unittest discover -s tests -p "test_*.py"`
- allow_modify_tests: false
- max_iterations: 4

### Demo 2: Feedback-to-Fix
输入：

```text
修复当前 failing test，不允许修改测试文件
```

并指定 verify command。页面会展示：
- 状态流转（Planner/Retriever/Coder/Executor/Diagnoser）
- patch diff
- 执行日志
- final report
