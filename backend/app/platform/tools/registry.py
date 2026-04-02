from __future__ import annotations

from app.platform.tools.base import BaseTool, ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def list_specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    def build_prompt_fragment(self) -> str:
        if not self._tools:
            return ""
        sections: list[str] = ["Available tools:"]
        for tool in self._tools.values():
            params = ", ".join(
                f"{item.name}:{item.param_type}{' required' if item.required else ''}"
                for item in tool.parameters()
            )
            sections.append(f"- {tool.name}: {tool.description} | parameters: {params or 'none'}")
        sections.append('Tool call format: [TOOL_CALL:tool_name:{"arg":"value"}]')
        sections.append("After a tool runs, you will receive [TOOL_RESULT:tool_name] followed by JSON.")
        return "\n".join(sections)
