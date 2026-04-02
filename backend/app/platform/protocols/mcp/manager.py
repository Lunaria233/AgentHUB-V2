from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any

from app.platform.protocols.mcp.client import (
    MCPClient,
    MCPPromptRenderResult,
    MCPPromptDescriptor,
    MCPResourceReadResult,
    MCPResourceDescriptor,
    MCPToolDescriptor,
)


@dataclass(slots=True)
class MCPServerConfig:
    server_name: str
    enabled: bool = True
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    description: str = ""
    request_timeout_seconds: float = 20.0
    startup_timeout_seconds: float = 15.0
    allowed_app_ids: list[str] = field(default_factory=list)
    source: str = "static"


class MCPConnectionManager:
    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._configs: dict[str, MCPServerConfig] = {}

    def register_server(self, config: MCPServerConfig) -> MCPClient:
        existing = self._clients.get(config.server_name)
        if existing is not None:
            try:
                existing.close()
            except Exception:
                pass
        env = os.environ.copy()
        env.update(config.env)
        client = MCPClient(
            server_name=config.server_name,
            transport=config.transport,
            command=config.command,
            args=config.args,
            url=config.url,
            env=env,
            headers=config.headers,
            request_timeout_seconds=config.request_timeout_seconds,
            startup_timeout_seconds=config.startup_timeout_seconds,
        )
        self._configs[config.server_name] = config
        self._clients[config.server_name] = client
        if config.enabled:
            try:
                client.connect()
            except Exception as exc:
                client.last_error = str(exc)
        return client

    def unregister_server(self, server_name: str) -> bool:
        client = self._clients.pop(server_name, None)
        self._configs.pop(server_name, None)
        if client is None:
            return False
        try:
            client.close()
        except Exception:
            pass
        return True

    def set_enabled(self, server_name: str, enabled: bool) -> bool:
        config = self._configs.get(server_name)
        client = self._clients.get(server_name)
        if config is None or client is None:
            return False
        config.enabled = enabled
        if enabled:
            try:
                client.connect()
            except Exception as exc:
                client.last_error = str(exc)
        else:
            try:
                client.close()
            except Exception:
                pass
        return True

    def list_configs(self) -> list[MCPServerConfig]:
        return list(self._configs.values())

    def get_client(self, server_name: str) -> MCPClient | None:
        return self._clients.get(server_name)

    def get_config(self, server_name: str) -> MCPServerConfig | None:
        return self._configs.get(server_name)

    def ensure_connected(self, server_name: str) -> MCPClient | None:
        client = self.get_client(server_name)
        if client is None:
            return None
        try:
            client.ensure_connected()
        except Exception as exc:
            client.last_error = str(exc)
        return client

    def discover_tools(self, server_name: str, *, refresh: bool = False) -> list[MCPToolDescriptor]:
        client = self.ensure_connected(server_name)
        if client is None:
            return []
        try:
            return client.list_tools(refresh=refresh)
        except Exception as exc:
            client.last_error = str(exc)
            return []

    def discover_resources(self, server_name: str, *, refresh: bool = False) -> list[MCPResourceDescriptor]:
        client = self.ensure_connected(server_name)
        if client is None:
            return []
        try:
            return client.list_resources(refresh=refresh)
        except Exception as exc:
            if "Method not found" in str(exc):
                if client.last_error == str(exc):
                    client.last_error = ""
            else:
                client.last_error = str(exc)
            return []

    def discover_prompts(self, server_name: str, *, refresh: bool = False) -> list[MCPPromptDescriptor]:
        client = self.ensure_connected(server_name)
        if client is None:
            return []
        try:
            return client.list_prompts(refresh=refresh)
        except Exception as exc:
            if "Method not found" in str(exc):
                if client.last_error == str(exc):
                    client.last_error = ""
            else:
                client.last_error = str(exc)
            return []

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        client = self.ensure_connected(server_name)
        if client is None:
            return {"ok": False, "error": f"MCP server '{server_name}' is not registered"}
        try:
            return client.call_tool(tool_name, arguments)
        except Exception as exc:
            client.last_error = str(exc)
            return {"ok": False, "error": str(exc), "server_name": server_name, "tool_name": tool_name}

    def read_resource(self, server_name: str, uri: str) -> MCPResourceReadResult | None:
        client = self.ensure_connected(server_name)
        if client is None:
            return None
        try:
            return client.read_resource(uri)
        except Exception as exc:
            client.last_error = str(exc)
            return None

    def get_prompt(self, server_name: str, prompt_name: str, arguments: dict[str, Any] | None = None) -> MCPPromptRenderResult | None:
        client = self.ensure_connected(server_name)
        if client is None:
            return None
        try:
            return client.get_prompt(prompt_name, arguments)
        except Exception as exc:
            client.last_error = str(exc)
            return None

    def list_server_names(self, *, enabled_only: bool = False) -> list[str]:
        if not enabled_only:
            return list(self._configs.keys())
        return [name for name, config in self._configs.items() if config.enabled]

    def status(self) -> dict[str, Any]:
        servers: list[dict[str, Any]] = []
        for server_name in self.list_server_names():
            config = self._configs[server_name]
            client = self._clients.get(server_name)
            if config.enabled and client is not None:
                if not client.status_snapshot().get("tools_count"):
                    self.discover_tools(server_name)
                if not client.status_snapshot().get("resources_count"):
                    self.discover_resources(server_name)
                if not client.status_snapshot().get("prompts_count"):
                    self.discover_prompts(server_name)
            snapshot = client.status_snapshot() if client else {}
            servers.append(
                {
                    "server_name": server_name,
                    "enabled": config.enabled,
                    "source": config.source,
                    "allowed_app_ids": list(config.allowed_app_ids),
                    "transport": config.transport,
                    "command": config.command,
                    "args": list(config.args),
                    "url": config.url,
                    "description": config.description,
                    "headers": dict(config.headers),
                    **snapshot,
                }
            )
        return {"servers": servers}

    def catalog(self, server_names: list[str] | None = None, *, refresh: bool = False) -> dict[str, Any]:
        selected = server_names or self.list_server_names(enabled_only=True)
        payload: dict[str, Any] = {}
        for server_name in selected:
            payload[server_name] = {
                "tools": [asdict(item) for item in self.discover_tools(server_name, refresh=refresh)],
                "resources": [asdict(item) for item in self.discover_resources(server_name, refresh=refresh)],
                "prompts": [asdict(item) for item in self.discover_prompts(server_name, refresh=refresh)],
            }
        return payload

    def close_all(self) -> None:
        for client in self._clients.values():
            try:
                client.close()
            except Exception:
                continue
