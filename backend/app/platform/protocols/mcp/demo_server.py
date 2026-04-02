from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(os.getenv("AGENTHUB_MCP_ROOT", ".")).resolve()
PROTOCOL_VERSION = "2025-06-18"


TOOLS = [
    {
        "name": "echo_text",
        "description": "Echo text back to the caller for MCP smoke tests.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to echo back"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "list_workspace",
        "description": "List files under the configured MCP root.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside the workspace root"},
            },
        },
    },
    {
        "name": "read_text_file",
        "description": "Read a UTF-8 text file under the configured MCP root.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path inside the workspace root"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "current_time",
        "description": "Return the server time and root path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "description": "Optional timezone label for display only"},
            },
        },
    },
]

RESOURCES = [
    {
        "uri": "info://server",
        "name": "server_info",
        "title": "AgentHub MCP Demo Server",
        "description": "Static demo server metadata",
        "mimeType": "application/json",
    },
    {
        "uri": "info://workspace",
        "name": "workspace_info",
        "title": "Workspace Root",
        "description": "Current allowed workspace root for MCP demo server",
        "mimeType": "text/plain",
    },
]

PROMPTS = [
    {
        "name": "workspace_helper",
        "title": "Workspace Helper",
        "description": "Prompt that explains how to use the demo workspace tools.",
        "arguments": [
            {"name": "goal", "description": "User goal for workspace inspection", "required": False},
        ],
    }
]


def _read_resource(uri: str) -> dict[str, Any]:
    if uri == "info://server":
        payload = {
            "name": "agenthub-demo-mcp",
            "version": "0.1.0",
            "root": str(ROOT),
            "tools": [item["name"] for item in TOOLS],
        }
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(payload, ensure_ascii=False, indent=2),
                }
            ]
        }
    if uri == "info://workspace":
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/plain",
                    "text": str(ROOT),
                }
            ]
        }
    return {"contents": []}


def _get_prompt(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "workspace_helper":
        goal = str(arguments.get("goal", "")).strip()
        text = (
            "You can use the following MCP tools to inspect the current workspace:\n"
            "- echo_text\n"
            "- list_workspace\n"
            "- read_text_file\n"
            "- current_time\n"
        )
        if goal:
            text += f"\nCurrent goal: {goal}"
        return {
            "description": "Workspace helper prompt",
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }
    return {"description": "", "messages": []}


def _safe_path(relative_path: str) -> Path:
    candidate = (ROOT / relative_path).resolve()
    if ROOT != candidate and ROOT not in candidate.parents:
        raise ValueError("Path escapes MCP workspace root")
    return candidate


def _tool_result_text(text: str, *, structured: dict[str, Any] | None = None, is_error: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
    if structured is not None:
        payload["structuredContent"] = structured
    return payload


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "echo_text":
        text = str(arguments.get("text", ""))
        return _tool_result_text(text, structured={"echo": text})
    if name == "list_workspace":
        relative = str(arguments.get("path", ".") or ".")
        target = _safe_path(relative)
        if not target.exists():
            return _tool_result_text(f"Path not found: {relative}", is_error=True)
        entries = []
        for item in sorted(target.iterdir(), key=lambda path: (path.is_file(), path.name.lower())):
            entries.append({"name": item.name, "is_dir": item.is_dir()})
        text = "\n".join(f"{'[DIR]' if entry['is_dir'] else '[FILE]'} {entry['name']}" for entry in entries) or "(empty)"
        return _tool_result_text(text, structured={"entries": entries, "path": str(target)})
    if name == "read_text_file":
        relative = str(arguments.get("path", ""))
        target = _safe_path(relative)
        if not target.exists() or not target.is_file():
            return _tool_result_text(f"File not found: {relative}", is_error=True)
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return _tool_result_text(f"File is not valid UTF-8 text: {relative}", is_error=True)
        preview = content[:4000]
        return _tool_result_text(preview, structured={"path": str(target), "preview_length": len(preview)})
    if name == "current_time":
        timezone = str(arguments.get("timezone", "local") or "local")
        now = datetime.now().isoformat(timespec="seconds")
        text = f"Current server time: {now}\nTimezone label: {timezone}\nWorkspace root: {ROOT}"
        return _tool_result_text(text, structured={"timestamp": now, "timezone": timezone, "root": str(ROOT)})
    return _tool_result_text(f"Unknown tool: {name}", is_error=True)


def _handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = str(message.get("method", ""))
    params = dict(message.get("params", {}))

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "agenthub-demo-mcp",
                    "version": "0.1.0",
                    "description": "Built-in MCP demo server for AgentHub",
                },
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        result = _call_tool(str(params.get("name", "")), dict(params.get("arguments", {})))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": RESOURCES}}
    if method == "resources/read":
        return {"jsonrpc": "2.0", "id": request_id, "result": _read_resource(str(params.get("uri", "")))} 
    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"prompts": PROMPTS}}
    if method == "prompts/get":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": _get_prompt(str(params.get("name", "")), dict(params.get("arguments", {}))),
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        response = _handle_request(message)
        if response is None:
            continue
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
