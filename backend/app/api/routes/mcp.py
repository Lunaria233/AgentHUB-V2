from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import shutil

from fastapi import APIRouter, HTTPException, Query
import httpx
from pydantic import BaseModel, Field

from app.platform.runtime.orchestrator import get_orchestrator
from app.platform.protocols.mcp.manager import MCPServerConfig
from app.platform.tools.mcp_adapter import build_mcp_tool_name


router = APIRouter()


class MCPCallRequest(BaseModel):
    app_id: str = Field(min_length=1)
    server_name: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class MCPReadResourceRequest(BaseModel):
    app_id: str = Field(min_length=1)
    server_name: str = Field(min_length=1)
    uri: str = Field(min_length=1)


class MCPGetPromptRequest(BaseModel):
    app_id: str = Field(min_length=1)
    server_name: str = Field(min_length=1)
    prompt_name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class MCPImportRequest(BaseModel):
    config_text: str = Field(min_length=2)
    allowed_app_ids: list[str] = Field(default_factory=lambda: ["chat"])
    enabled: bool = True


class MCPPrecheckRequest(BaseModel):
    config_text: str = Field(min_length=2)


class MCPServerUpdateRequest(BaseModel):
    enabled: bool | None = None
    allowed_app_ids: list[str] | None = None


def _allowed_servers_for_app(app_id: str) -> list[str]:
    orchestrator = get_orchestrator()
    return orchestrator.get_allowed_mcp_servers(app_id)


def _profile_for_app(app_id: str):
    orchestrator = get_orchestrator()
    return orchestrator.app_registry.get(app_id).profiles.mcp_profile


def _mask_values(values: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for key, value in values.items():
        if not value:
            masked[key] = ""
        elif len(value) <= 6:
            masked[key] = "***"
        else:
            masked[key] = f"{value[:2]}***{value[-2:]}"
    return masked


def _server_to_payload(config: MCPServerConfig) -> dict[str, object]:
    return {
        "server_name": config.server_name,
        "enabled": config.enabled,
        "source": config.source,
        "transport": config.transport,
        "command": config.command,
        "args": list(config.args),
        "url": config.url,
        "description": config.description,
        "allowed_app_ids": list(config.allowed_app_ids),
        "env_keys": sorted(config.env.keys()),
        "env_masked": _mask_values(config.env),
        "header_keys": sorted(config.headers.keys()),
        "headers_masked": _mask_values(config.headers),
        "request_timeout_seconds": config.request_timeout_seconds,
        "startup_timeout_seconds": config.startup_timeout_seconds,
        "editable": config.source == "custom",
    }


def _config_from_raw_server(name: str, payload: dict[str, object], *, enabled: bool, allowed_app_ids: list[str]) -> MCPServerConfig:
    server_name = str(name).strip()
    if not server_name:
        raise ValueError("MCP server name is required")
    transport = str(payload.get("transport") or "").strip().lower()
    command = str(payload.get("command") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not transport:
        transport = "stdio" if command else "streamable_http" if url else "stdio"
    if transport == "stdio" and not command:
        raise ValueError(f"MCP server '{server_name}' is missing command for stdio transport")
    if transport != "stdio" and not url:
        raise ValueError(f"MCP server '{server_name}' is missing url for HTTP transport")
    return MCPServerConfig(
        server_name=server_name,
        enabled=enabled if "enabled" not in payload else bool(payload.get("enabled")),
        transport=transport,
        command=command,
        args=[str(item) for item in payload.get("args", [])],
        url=url,
        env={str(key): str(value) for key, value in dict(payload.get("env", {})).items()},
        headers={str(key): str(value) for key, value in dict(payload.get("headers", {})).items()},
        description=str(payload.get("description") or ""),
        request_timeout_seconds=float(payload.get("request_timeout_seconds", 20.0)),
        startup_timeout_seconds=float(payload.get("startup_timeout_seconds", 15.0)),
        allowed_app_ids=[str(item) for item in allowed_app_ids if str(item).strip()],
        source="custom",
    )


def _parse_import_configs(request: MCPImportRequest) -> list[MCPServerConfig]:
    try:
        payload = json.loads(request.config_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="MCP config must be a JSON object")

    servers_payload: dict[str, object]
    if "mcpServers" in payload and isinstance(payload["mcpServers"], dict):
        servers_payload = dict(payload["mcpServers"])
    elif "server_name" in payload or "command" in payload or "url" in payload:
        inferred_name = str(payload.get("server_name") or payload.get("name") or "").strip()
        if not inferred_name:
            raise HTTPException(status_code=400, detail="Single MCP config payload must include 'server_name' or 'name'")
        servers_payload = {inferred_name: payload}
    else:
        raise HTTPException(status_code=400, detail="Unsupported MCP config format. Expected {\"mcpServers\": {...}}")

    configs: list[MCPServerConfig] = []
    for name, raw_server in servers_payload.items():
        if not isinstance(raw_server, dict):
            continue
        try:
            configs.append(
                _config_from_raw_server(
                    str(name),
                    raw_server,
                    enabled=request.enabled,
                    allowed_app_ids=request.allowed_app_ids,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not configs:
        raise HTTPException(status_code=400, detail="No MCP server definitions were found in the provided JSON")
    return configs


def _parse_raw_server_map(config_text: str) -> dict[str, dict[str, object]]:
    try:
        payload = json.loads(config_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="MCP config must be a JSON object")
    if "mcpServers" in payload and isinstance(payload["mcpServers"], dict):
        return {
            str(name): dict(raw_server)
            for name, raw_server in dict(payload["mcpServers"]).items()
            if isinstance(raw_server, dict)
        }
    inferred_name = str(payload.get("server_name") or payload.get("name") or "").strip()
    if inferred_name:
        return {inferred_name: payload}
    raise HTTPException(status_code=400, detail="Unsupported MCP config format. Expected {\"mcpServers\": {...}}")


def _resolve_command(command: str) -> str:
    resolved = shutil.which(command)
    if resolved:
        return resolved
    if Path(command).exists():
        return str(Path(command).resolve())
    if command.lower() in {"node", "npm", "npx"}:
        program_files = Path(Path.home().drive + "\\Program Files") if Path.home().drive else Path(r"C:\Program Files")
        for suffix in (".cmd", ".exe"):
            candidate = program_files / "nodejs" / f"{command}{suffix}"
            if candidate.exists():
                return str(candidate)
    return ""


def _precheck_stdio(name: str, raw_server: dict[str, object]) -> dict[str, object]:
    command = str(raw_server.get("command") or "").strip()
    args = [str(item) for item in raw_server.get("args", [])]
    resolved = _resolve_command(command) if command else ""
    warnings: list[str] = []
    checks: dict[str, object] = {
        "command": command,
        "args": args,
        "command_found": bool(resolved),
        "resolved_command": resolved,
        "module_name": "",
        "module_installed": None,
        "likely_requires_preinstall": False,
        "launcher_kind": "stdio",
    }
    if not command:
        warnings.append(f"Server '{name}' is missing 'command'.")
    if command in {"python", "python3", "py"} and len(args) >= 2 and args[0] == "-m":
        module_name = args[1]
        installed = importlib.util.find_spec(module_name) is not None
        checks["launcher_kind"] = "python_module"
        checks["module_name"] = module_name
        checks["module_installed"] = installed
        checks["likely_requires_preinstall"] = True
        if not installed:
            warnings.append(f"Python module '{module_name}' is not installed in the current backend environment.")
    elif command == "npx":
        checks["launcher_kind"] = "npx"
        checks["likely_requires_preinstall"] = False
        warnings.append("npx usually does not require pre-install, but Node.js and network access must be available.")
    elif command == "uvx":
        checks["launcher_kind"] = "uvx"
        checks["likely_requires_preinstall"] = False
        warnings.append("uvx usually does not require pre-install, but uv must be installed locally.")
    elif command and not resolved:
        warnings.append(f"Command '{command}' was not found in the current backend environment.")
    return {
        "server_name": name,
        "transport": "stdio",
        "ready": bool(command and resolved) and checks.get("module_installed", True) is not False,
        "warnings": warnings,
        "checks": checks,
    }


def _precheck_http(name: str, raw_server: dict[str, object]) -> dict[str, object]:
    url = str(raw_server.get("url") or "").strip()
    parsed = urlparse(url) if url else None
    warnings: list[str] = []
    checks: dict[str, object] = {
        "url": url,
        "url_scheme": parsed.scheme if parsed else "",
        "has_query_auth": False,
        "query_auth_keys": [],
        "probe_status_code": None,
        "probe_reachable": False,
        "probe_error": "",
    }
    if not url:
        warnings.append(f"Server '{name}' is missing 'url'.")
    else:
        query_keys = sorted(parse_qs(parsed.query).keys())
        sensitive_query_keys = [key for key in query_keys if key.lower() in {"ak", "token", "key", "api_key"}]
        checks["has_query_auth"] = bool(sensitive_query_keys)
        checks["query_auth_keys"] = sensitive_query_keys
        if sensitive_query_keys:
            warnings.append("This HTTP MCP server uses query-string auth. The full URL will be stored in custom MCP config.")
        try:
            response = httpx.get(url, timeout=5.0, follow_redirects=True)
            checks["probe_status_code"] = response.status_code
            checks["probe_reachable"] = True
            if response.status_code >= 500:
                warnings.append(f"Server responded with HTTP {response.status_code} during probe.")
            elif response.status_code in {401, 403}:
                warnings.append("Server is reachable but rejected the probe. Auth may still be required.")
        except Exception as exc:
            checks["probe_error"] = str(exc)
            warnings.append(f"HTTP probe failed: {exc}")
    return {
        "server_name": name,
        "transport": "streamable_http",
        "ready": bool(url),
        "warnings": warnings,
        "checks": checks,
    }


def _precheck_servers(config_text: str) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for name, raw_server in _parse_raw_server_map(config_text).items():
        command = str(raw_server.get("command") or "").strip()
        url = str(raw_server.get("url") or "").strip()
        transport = str(raw_server.get("transport") or "").strip().lower()
        if not transport:
            transport = "stdio" if command else "streamable_http" if url else "stdio"
        if transport == "stdio":
            results.append(_precheck_stdio(name, raw_server))
        else:
            results.append(_precheck_http(name, raw_server))
    return results


@router.get("/status")
def get_mcp_status() -> dict[str, object]:
    orchestrator = get_orchestrator()
    return {
        "enabled": orchestrator.settings.mcp_enabled,
        **orchestrator.mcp_manager.status(),
    }


@router.get("/catalog")
def get_mcp_catalog(
    app_id: str = Query(..., min_length=1),
    refresh: bool = Query(default=False),
) -> dict[str, object]:
    orchestrator = get_orchestrator()
    manifest = orchestrator.app_registry.get(app_id)
    mcp_profile = manifest.profiles.mcp_profile
    allowed_servers = _allowed_servers_for_app(app_id)
    return {
        "app_id": app_id,
        "enabled": manifest.capabilities.mcp and orchestrator.settings.mcp_enabled and mcp_profile.enabled,
        "allowed_servers": allowed_servers,
        "catalog": orchestrator.mcp_manager.catalog(allowed_servers, refresh=refresh),
        "exposed_tool_names": {
            server_name: [
                build_mcp_tool_name(server_name, item.name)
                for item in orchestrator.mcp_manager.discover_tools(server_name, refresh=refresh)
            ]
            for server_name in allowed_servers
        },
    }


@router.get("/servers")
def list_mcp_servers() -> dict[str, object]:
    orchestrator = get_orchestrator()
    return {
        "enabled": orchestrator.settings.mcp_enabled,
        "servers": [_server_to_payload(config) for config in orchestrator.list_mcp_servers()],
    }


@router.post("/import")
def import_mcp_servers(request: MCPImportRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    imported: list[dict[str, object]] = []
    for config in _parse_import_configs(request):
        try:
            imported_config = orchestrator.upsert_custom_mcp_server(config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        imported.append(_server_to_payload(imported_config))
    return {"imported": imported}


@router.post("/precheck")
def precheck_mcp_servers(request: MCPPrecheckRequest) -> dict[str, object]:
    return {
        "results": _precheck_servers(request.config_text),
    }


@router.patch("/servers/{server_name}")
def update_mcp_server(server_name: str, request: MCPServerUpdateRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    config = next((item for item in orchestrator.list_mcp_servers() if item.server_name == server_name), None)
    if config is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' was not found")
    if config.source != "custom":
        raise HTTPException(status_code=400, detail=f"MCP server '{server_name}' is managed by platform.toml")
    if request.allowed_app_ids is not None:
        config.allowed_app_ids = [str(item) for item in request.allowed_app_ids if str(item).strip()]
        orchestrator.upsert_custom_mcp_server(config)
    if request.enabled is not None:
        config = orchestrator.set_custom_mcp_server_enabled(server_name, request.enabled)
    return _server_to_payload(config)


@router.delete("/servers/{server_name}")
def delete_mcp_server(server_name: str) -> dict[str, object]:
    orchestrator = get_orchestrator()
    try:
        deleted = orchestrator.delete_custom_mcp_server(server_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' was not found")
    return {"deleted": True, "server_name": server_name}


@router.post("/call")
def call_mcp_tool(request: MCPCallRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    allowed_servers = set(_allowed_servers_for_app(request.app_id))
    if request.server_name not in allowed_servers:
        raise HTTPException(status_code=403, detail=f"MCP server '{request.server_name}' is not allowed for app '{request.app_id}'")
    allowed_tools = set(_profile_for_app(request.app_id).allowed_tools)
    if allowed_tools and request.tool_name not in allowed_tools:
        raise HTTPException(status_code=403, detail=f"MCP tool '{request.tool_name}' is not allowed for app '{request.app_id}'")
    result = orchestrator.mcp_manager.call_tool(request.server_name, request.tool_name, dict(request.arguments))
    if not result.get("ok", False):
        raise HTTPException(status_code=400, detail=result.get("error", "MCP tool call failed"))
    return result


@router.post("/resource/read")
def read_mcp_resource(request: MCPReadResourceRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    allowed_servers = set(_allowed_servers_for_app(request.app_id))
    if request.server_name not in allowed_servers:
        raise HTTPException(status_code=403, detail=f"MCP server '{request.server_name}' is not allowed for app '{request.app_id}'")
    allowed_resources = set(_profile_for_app(request.app_id).allowed_resources)
    if allowed_resources and request.uri not in allowed_resources:
        raise HTTPException(status_code=403, detail=f"MCP resource '{request.uri}' is not allowed for app '{request.app_id}'")
    result = orchestrator.mcp_manager.read_resource(request.server_name, request.uri)
    if result is None:
        raise HTTPException(status_code=400, detail="MCP resource read failed")
    return {
        "server_name": result.server_name,
        "uri": result.uri,
        "contents": result.contents,
        "raw": result.raw,
    }


@router.post("/prompt/get")
def get_mcp_prompt(request: MCPGetPromptRequest) -> dict[str, object]:
    orchestrator = get_orchestrator()
    allowed_servers = set(_allowed_servers_for_app(request.app_id))
    if request.server_name not in allowed_servers:
        raise HTTPException(status_code=403, detail=f"MCP server '{request.server_name}' is not allowed for app '{request.app_id}'")
    allowed_prompts = set(_profile_for_app(request.app_id).allowed_prompts)
    if allowed_prompts and request.prompt_name not in allowed_prompts:
        raise HTTPException(status_code=403, detail=f"MCP prompt '{request.prompt_name}' is not allowed for app '{request.app_id}'")
    result = orchestrator.mcp_manager.get_prompt(request.server_name, request.prompt_name, dict(request.arguments))
    if result is None:
        raise HTTPException(status_code=400, detail="MCP prompt retrieval failed")
    return {
        "server_name": result.server_name,
        "prompt_name": result.prompt_name,
        "description": result.description,
        "messages": result.messages,
        "raw": result.raw,
    }
