# MCP 接入清单

## 本地 / 社区 stdio MCP server

需要的信息：

- `server_name`
- `transport = "stdio"`
- `command`
- `args`
- `description`
- 可选：`env`
- 允许给哪些 app 使用
- 可选：允许哪些 `tools / resources / prompts`

示例：

```toml
[[mcp.servers]]
name = "filesystem"
enabled = true
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "."]
description = "Filesystem MCP server"

[apps.chat]
allowed_mcp_servers = ["demo", "filesystem"]
```

## 远程 / 外部 MCP server

需要的信息：

- `server_name`
- `transport = "streamable_http"`
- `url`
- 可选：`headers`
- 可选：哪些 app 可以访问
- 可选：允许哪些 `tools / resources / prompts`

示例：

```toml
[[mcp.servers]]
name = "remote_docs"
enabled = true
transport = "streamable_http"
url = "https://example.com/mcp"
description = "Remote docs MCP server"
headers = { Authorization = "Bearer ${REMOTE_MCP_TOKEN}" }
```

## 共存关系

本地 stdio MCP server 与远程 HTTP MCP server 可以共存。

AgentHub 会统一通过 `MCPConnectionManager` 管理它们，并按 app 的 allowlist 决定哪些 server 会被注入到当前 agent runtime。

## 当前 AgentHub 已支持

- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`
- `prompts/list`
- `prompts/get`
- 本地 stdio transport
- 远程 streamable HTTP transport
- app 级 `server / tool / resource / prompt` 过滤
