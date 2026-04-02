from __future__ import annotations

import re
from typing import Any

from app.platform.protocols.mcp.client import MCPToolDescriptor
from app.platform.protocols.mcp.manager import MCPConnectionManager
from app.platform.tools.base import BaseTool, ToolContext, ToolParameter


def sanitize_mcp_tool_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_").lower()


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    return f"mcp_{sanitize_mcp_tool_name(server_name)}_{sanitize_mcp_tool_name(tool_name)}"


class MCPToolAdapter(BaseTool):
    def __init__(self, manager: MCPConnectionManager, descriptor: MCPToolDescriptor, *, exposed_name: str | None = None) -> None:
        self.manager = manager
        self.descriptor = descriptor
        self._name = exposed_name or build_mcp_tool_name(descriptor.server_name, descriptor.name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        source = f"[MCP:{self.descriptor.server_name}]"
        if self.descriptor.description:
            return f"{source} {self.descriptor.description} (source tool: {self.descriptor.name})"
        return f"{source} source tool: {self.descriptor.name}"

    def parameters(self) -> list[ToolParameter]:
        schema = self.descriptor.input_schema or {}
        properties = dict(schema.get("properties", {}))
        required = {str(item) for item in schema.get("required", [])}
        parameters: list[ToolParameter] = []
        for name, spec in properties.items():
            if not isinstance(spec, dict):
                continue
            parameters.append(
                ToolParameter(
                    name=name,
                    description=str(spec.get("description", "")),
                    required=name in required,
                    param_type=str(spec.get("type", "string")),
                )
            )
        return parameters

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        _ = context
        return self.manager.call_tool(
            self.descriptor.server_name,
            self.descriptor.name,
            arguments,
        )
