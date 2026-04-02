from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.platform.protocols.mcp.manager import MCPServerConfig


class MCPServerStore:
    """Persist custom MCP server definitions outside platform.toml."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list_servers(self) -> list[MCPServerConfig]:
        payload = self._read_payload()
        servers: list[MCPServerConfig] = []
        for item in payload.get("servers", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("server_name", "")).strip()
            if not name:
                continue
            servers.append(
                MCPServerConfig(
                    server_name=name,
                    enabled=bool(item.get("enabled", True)),
                    transport=str(item.get("transport", "stdio")),
                    command=str(item.get("command", "")),
                    args=[str(arg) for arg in item.get("args", [])],
                    url=str(item.get("url", "")),
                    env={str(key): str(value) for key, value in dict(item.get("env", {})).items()},
                    headers={str(key): str(value) for key, value in dict(item.get("headers", {})).items()},
                    description=str(item.get("description", "")),
                    request_timeout_seconds=float(item.get("request_timeout_seconds", 20.0)),
                    startup_timeout_seconds=float(item.get("startup_timeout_seconds", 15.0)),
                    allowed_app_ids=[str(value) for value in item.get("allowed_app_ids", [])],
                    source=str(item.get("source", "custom")),
                )
            )
        return servers

    def upsert_server(self, config: MCPServerConfig) -> None:
        payload = self._read_payload()
        servers = [item for item in payload.get("servers", []) if item.get("server_name") != config.server_name]
        servers.append(asdict(config))
        payload["servers"] = sorted(servers, key=lambda item: str(item.get("server_name", "")))
        self._write_payload(payload)

    def delete_server(self, server_name: str) -> bool:
        payload = self._read_payload()
        before = len(payload.get("servers", []))
        payload["servers"] = [item for item in payload.get("servers", []) if item.get("server_name") != server_name]
        if len(payload["servers"]) == before:
            return False
        self._write_payload(payload)
        return True

    def get_server(self, server_name: str) -> MCPServerConfig | None:
        for server in self.list_servers():
            if server.server_name == server_name:
                return server
        return None

    def _read_payload(self) -> dict[str, object]:
        if not self.path.exists():
            return {"servers": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"servers": []}

    def _write_payload(self, payload: dict[str, object]) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
