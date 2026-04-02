from __future__ import annotations

from typing import Any

from app.platform.core.errors import ToolExecutionError
from app.platform.observability.tracing import TraceService
from app.platform.tools.base import ToolContext
from app.platform.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, trace_service: TraceService | None = None) -> None:
        self.registry = registry
        self.trace_service = trace_service

    def execute_tool(self, tool_name: str, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        tool = self.registry.get(tool_name)
        if tool is None:
            raise ToolExecutionError(f"Unknown tool: {tool_name}")
        result = tool.run(arguments=arguments, context=context)
        if self.trace_service:
            self.trace_service.log_tool_call(context=context, tool_name=tool_name, arguments=arguments, result=result)
        return result

    def safe_execute_tool(self, tool_name: str, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        try:
            return self.execute_tool(tool_name=tool_name, arguments=arguments, context=context)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
