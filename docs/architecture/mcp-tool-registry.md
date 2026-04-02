# MCP 与 ToolRegistry

## 结论

- `MCP` 是**协议与外部能力接入层**
- `ToolRegistry` 是**平台内部可调用工具注册层**

两者不是同一个东西，也不应该混为一谈。

## 在 AgentHub 里的分层

1. `MCPClient / MCPConnectionManager`
   - 负责连接 MCP server
   - 负责协议握手、工具发现、工具调用
   - 还能发现 resources / prompts

2. `MCPToolAdapter`
   - 把 MCP server 暴露出来的 tool 转成平台内部 `BaseTool`
   - 生成 `mcp_<server>_<tool>` 形式的内部工具名

3. `ToolRegistry`
   - 存放平台当前真正提供给 agent runtime 的工具
   - 里面既可以有内置工具，也可以有 MCP 派生工具

## 关系

- `MCP` 发现外部工具
- `MCPToolAdapter` 做协议到平台工具的桥接
- `ToolRegistry` 再把这些工具交给 agent runtime

也就是说：

`MCP server -> MCP client -> MCP tool adapter -> ToolRegistry -> agent runtime`

## 为什么不能把 MCP 直接等同于 ToolRegistry

因为 `ToolRegistry` 只关心“当前 agent 能调用什么工具”。

但 `MCP` 不只包含 tools，还可能包含：

- `resources`
- `prompts`
- 后续更多 MCP 能力

所以更准确的说法是：

- `ToolRegistry` 是 AgentHub 的内部运行时机制
- `MCP` 是 AgentHub 接入外部能力的标准协议
- `MCP` 发现到的 tools 会进入 `ToolRegistry`
- `resources / prompts` 不一定进入 `ToolRegistry`，它们更适合进入 Context / Skills 等链路
