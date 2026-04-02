from __future__ import annotations

import itertools
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx


DEFAULT_PROTOCOL_VERSION = "2025-06-18"


class MCPError(RuntimeError):
    """Base MCP exception."""


class MCPTransportError(MCPError):
    """Raised when a transport cannot be started or used."""


class MCPProtocolError(MCPError):
    """Raised when the remote server returns a protocol error."""

    def __init__(self, message: str, *, code: int | None = None, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


@dataclass(slots=True)
class MCPToolDescriptor:
    name: str
    description: str
    input_schema: dict[str, Any]
    title: str = ""
    server_name: str = ""


@dataclass(slots=True)
class MCPResourceDescriptor:
    uri: str
    name: str = ""
    title: str = ""
    description: str = ""
    mime_type: str = ""
    server_name: str = ""


@dataclass(slots=True)
class MCPPromptArgumentDescriptor:
    name: str
    description: str = ""
    required: bool = False


@dataclass(slots=True)
class MCPPromptDescriptor:
    name: str
    title: str = ""
    description: str = ""
    arguments: list[MCPPromptArgumentDescriptor] = field(default_factory=list)
    server_name: str = ""


@dataclass(slots=True)
class MCPResourceReadResult:
    server_name: str
    uri: str
    contents: list[dict[str, Any]]
    raw: dict[str, Any]


@dataclass(slots=True)
class MCPPromptRenderResult:
    server_name: str
    prompt_name: str
    description: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class MCPClient:
    """Minimal stdio-first MCP client for platform integration.

    The design follows the same layering as hello_agents chapter 10:
    1. protocol/transport layer -> this client
    2. tool adapter layer -> MCPToolAdapter
    3. agent/runtime integration -> ToolRegistry / Orchestrator
    """

    def __init__(
        self,
        server_name: str,
        transport: str = "stdio",
        *,
        command: str = "",
        args: list[str] | None = None,
        url: str = "",
        env: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        request_timeout_seconds: float = 20.0,
        startup_timeout_seconds: float = 15.0,
    ) -> None:
        self.server_name = server_name
        self.transport = transport
        self.command = command
        self.args = list(args or [])
        self.url = url
        self.env = dict(env or {})
        self.headers = dict(headers or {})
        self.request_timeout_seconds = request_timeout_seconds
        self.startup_timeout_seconds = startup_timeout_seconds

        self.connected = False
        self.protocol_version = ""
        self.server_info: dict[str, Any] = {}
        self.capabilities: dict[str, Any] = {}
        self.last_error = ""
        self.last_started_at = 0.0
        self.session_id = ""

        self._process: subprocess.Popen[str] | None = None
        self._http_client: httpx.Client | None = None
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._request_counter = itertools.count(1)
        self._write_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._stderr_buffer: deque[str] = deque(maxlen=80)
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None

        self._tool_cache: list[MCPToolDescriptor] = []
        self._resource_cache: list[MCPResourceDescriptor] = []
        self._prompt_cache: list[MCPPromptDescriptor] = []

    def connect(self) -> None:
        with self._lifecycle_lock:
            if self.connected and self._process and self._process.poll() is None:
                return
            self.close()
            self.last_error = ""
            if self.transport in {"streamable_http", "http", "sse", "http_stream"}:
                self._connect_http()
                return
            if self.transport != "stdio":
                raise MCPTransportError(f"Transport '{self.transport}' is not implemented for MCP server '{self.server_name}'")
            process_command = self._build_process_command()
            env = os.environ.copy()
            env.update({key: value for key, value in self.env.items() if value is not None})
            try:
                self._process = subprocess.Popen(
                    process_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=env,
                )
            except FileNotFoundError as exc:
                self.last_error = str(exc)
                raise MCPTransportError(
                    f"Failed to start MCP server '{self.server_name}': command '{self.command}' was not found"
                ) from exc

            self.last_started_at = time.time()
            self._stdout_thread = threading.Thread(target=self._read_stdout_loop, name=f"mcp-stdout-{self.server_name}", daemon=True)
            self._stderr_thread = threading.Thread(target=self._read_stderr_loop, name=f"mcp-stderr-{self.server_name}", daemon=True)
            self._stdout_thread.start()
            self._stderr_thread.start()

            try:
                result = self._send_request(
                    "initialize",
                    {
                        "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                        "capabilities": {
                            "roots": {"listChanged": False},
                            "sampling": {},
                        },
                        "clientInfo": {
                            "name": "AgentHub",
                            "title": "AgentHub MCP Client",
                            "version": "0.1.0",
                        },
                    },
                    timeout_seconds=self.startup_timeout_seconds,
                    allow_unconnected=True,
                )
                self.protocol_version = str(result.get("protocolVersion", DEFAULT_PROTOCOL_VERSION))
                self.server_info = dict(result.get("serverInfo", {}))
                self.capabilities = dict(result.get("capabilities", {}))
                self._send_notification("notifications/initialized")
                self.connected = True
            except Exception as exc:
                self.last_error = str(exc)
                self.close(force=True)
                raise

    def ensure_connected(self) -> None:
        if self.transport in {"streamable_http", "http", "sse", "http_stream"}:
            if not self.connected or self._http_client is None:
                self.connect()
            return
        if not self.connected or self._process is None or self._process.poll() is not None:
            self.connect()

    def close(self, *, force: bool = False) -> None:
        process = self._process
        http_client = self._http_client
        self.connected = False
        self.session_id = ""
        self._tool_cache = []
        self._resource_cache = []
        self._prompt_cache = []
        if http_client is not None:
            try:
                if self.url and self.session_id:
                    try:
                        http_client.delete(self.url, headers=self._build_http_headers(include_accept=False))
                    except Exception:
                        pass
                http_client.close()
            finally:
                self._http_client = None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
        if force and process.poll() is None:
            process.kill()
        else:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                if process.poll() is None:
                    process.kill()
        self._process = None
        for pending in list(self._pending.values()):
            pending.put({"error": {"message": "MCP server connection closed"}})
        self._pending.clear()

    def list_tools(self, *, refresh: bool = False) -> list[MCPToolDescriptor]:
        self.ensure_connected()
        if self._tool_cache and not refresh:
            return list(self._tool_cache)
        tools: list[MCPToolDescriptor] = []
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self._send_request("tools/list", params)
            for item in list(result.get("tools", [])):
                if not isinstance(item, dict):
                    continue
                tools.append(
                    MCPToolDescriptor(
                        name=str(item.get("name", "")),
                        description=str(item.get("description", "")),
                        input_schema=dict(item.get("inputSchema", {})),
                        title=str(item.get("title", "")),
                        server_name=self.server_name,
                    )
                )
            cursor = result.get("nextCursor")
            if not cursor:
                break
        self._tool_cache = tools
        return list(self._tool_cache)

    def list_resources(self, *, refresh: bool = False) -> list[MCPResourceDescriptor]:
        self.ensure_connected()
        if self._resource_cache and not refresh:
            return list(self._resource_cache)
        try:
            result = self._send_request("resources/list", {})
        except MCPProtocolError as exc:
            if exc.code == -32601:
                return []
            raise
        resources: list[MCPResourceDescriptor] = []
        for item in list(result.get("resources", [])):
            if not isinstance(item, dict):
                continue
            resources.append(
                MCPResourceDescriptor(
                    uri=str(item.get("uri", "")),
                    name=str(item.get("name", "")),
                    title=str(item.get("title", "")),
                    description=str(item.get("description", "")),
                    mime_type=str(item.get("mimeType", "")),
                    server_name=self.server_name,
                )
            )
        self._resource_cache = resources
        return list(self._resource_cache)

    def list_prompts(self, *, refresh: bool = False) -> list[MCPPromptDescriptor]:
        self.ensure_connected()
        if self._prompt_cache and not refresh:
            return list(self._prompt_cache)
        try:
            result = self._send_request("prompts/list", {})
        except MCPProtocolError as exc:
            if exc.code == -32601:
                return []
            raise
        prompts: list[MCPPromptDescriptor] = []
        for item in list(result.get("prompts", [])):
            if not isinstance(item, dict):
                continue
            arguments: list[MCPPromptArgumentDescriptor] = []
            for argument in list(item.get("arguments", [])):
                if not isinstance(argument, dict):
                    continue
                arguments.append(
                    MCPPromptArgumentDescriptor(
                        name=str(argument.get("name", "")),
                        description=str(argument.get("description", "")),
                        required=bool(argument.get("required", False)),
                    )
                )
            prompts.append(
                MCPPromptDescriptor(
                    name=str(item.get("name", "")),
                    title=str(item.get("title", "")),
                    description=str(item.get("description", "")),
                    arguments=arguments,
                    server_name=self.server_name,
                )
            )
        self._prompt_cache = prompts
        return list(self._prompt_cache)

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.ensure_connected()
        result = self._send_request("tools/call", {"name": tool_name, "arguments": arguments})
        content = list(result.get("content", []))
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        return {
            "ok": not bool(result.get("isError", False)),
            "server_name": self.server_name,
            "tool_name": tool_name,
            "content": content,
            "text": "\n".join(part for part in text_parts if part).strip(),
            "structured_content": result.get("structuredContent"),
            "is_error": bool(result.get("isError", False)),
            "raw": result,
        }

    def read_resource(self, uri: str) -> MCPResourceReadResult:
        self.ensure_connected()
        result = self._send_request("resources/read", {"uri": uri})
        contents = list(result.get("contents", []))
        return MCPResourceReadResult(
            server_name=self.server_name,
            uri=uri,
            contents=[item for item in contents if isinstance(item, dict)],
            raw=result,
        )

    def get_prompt(self, prompt_name: str, arguments: dict[str, Any] | None = None) -> MCPPromptRenderResult:
        self.ensure_connected()
        result = self._send_request("prompts/get", {"name": prompt_name, "arguments": arguments or {}})
        return MCPPromptRenderResult(
            server_name=self.server_name,
            prompt_name=prompt_name,
            description=str(result.get("description", "")),
            messages=[item for item in list(result.get("messages", [])) if isinstance(item, dict)],
            raw=result,
        )

    def status_snapshot(self) -> dict[str, Any]:
        process = self._process
        if self.transport in {"streamable_http", "http", "sse", "http_stream"}:
            connected = self.connected and self._http_client is not None
        else:
            connected = self.connected and process is not None and process.poll() is None
        return {
            "server_name": self.server_name,
            "transport": self.transport,
            "command": self.command,
            "args": list(self.args),
            "url": self.url,
            "headers": self._safe_headers_snapshot(),
            "connected": connected,
            "protocol_version": self.protocol_version,
            "server_info": dict(self.server_info),
            "capabilities": dict(self.capabilities),
            "last_error": self.last_error,
            "last_started_at": self.last_started_at,
            "session_id": self.session_id,
            "stderr_tail": list(self._stderr_buffer),
            "tools_count": len(self._tool_cache),
            "resources_count": len(self._resource_cache),
            "prompts_count": len(self._prompt_cache),
        }

    def _build_process_command(self) -> list[str]:
        if not self.command:
            raise MCPTransportError(f"MCP server '{self.server_name}' is missing a launch command")
        resolved_command = self._resolve_command(self.command)
        if os.name == "nt" and Path(resolved_command).suffix.lower() in {".cmd", ".bat"}:
            return ["cmd", "/c", resolved_command, *self.args]
        return [resolved_command, *self.args]

    @staticmethod
    def _resolve_command(command: str) -> str:
        resolved = shutil.which(command)
        if resolved:
            return resolved
        if os.name == "nt" and command.lower() in {"node", "npm", "npx"}:
            program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
            candidate = Path(program_files) / "nodejs" / f"{command}.cmd"
            if candidate.exists():
                return str(candidate)
            fallback = Path(program_files) / "nodejs" / f"{command}.exe"
            if fallback.exists():
                return str(fallback)
        return command

    def _send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        self._write_message(payload)

    def _send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
        allow_unconnected: bool = False,
    ) -> dict[str, Any]:
        if self.transport in {"streamable_http", "http", "sse", "http_stream"}:
            return self._send_http_request(
                method,
                params,
                timeout_seconds=timeout_seconds,
                allow_unconnected=allow_unconnected,
            )
        if not allow_unconnected:
            self.ensure_connected()
        if self._process is None or self._process.stdin is None:
            raise MCPTransportError(f"MCP server '{self.server_name}' is not running")
        request_id = next(self._request_counter)
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._pending[request_id] = response_queue
        try:
            self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params or {},
                }
            )
            timeout_value = timeout_seconds or self.request_timeout_seconds
            try:
                response = response_queue.get(timeout=timeout_value)
            except queue.Empty as exc:
                self.last_error = f"Timed out waiting for MCP response from '{self.server_name}' for method '{method}'"
                self.close(force=True)
                raise MCPTransportError(self.last_error) from exc
        finally:
            self._pending.pop(request_id, None)
        if "error" in response:
            error = response["error"] or {}
            message = str(error.get("message", f"MCP request '{method}' failed"))
            self.last_error = message
            raise MCPProtocolError(message, code=error.get("code"), data=error.get("data"))
        return dict(response.get("result", {}))

    def _write_message(self, payload: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise MCPTransportError(f"MCP server '{self.server_name}' is not running")
        with self._write_lock:
            try:
                self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                self._process.stdin.flush()
            except OSError as exc:
                self.last_error = str(exc)
                raise MCPTransportError(f"Failed to write to MCP server '{self.server_name}': {exc}") from exc

    def _read_stdout_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self._stderr_buffer.append(f"stdout(non-json): {line}")
                    continue
                if isinstance(message, list):
                    for item in message:
                        if isinstance(item, dict):
                            self._dispatch_message(item)
                    continue
                if isinstance(message, dict):
                    self._dispatch_message(message)
        finally:
            self.connected = False
            for pending in list(self._pending.values()):
                pending.put({"error": {"message": f"MCP server '{self.server_name}' disconnected"}})
            self._pending.clear()

    def _dispatch_message(self, message: dict[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            response_queue = self._pending.get(int(message["id"]))
            if response_queue is not None:
                response_queue.put(message)
            return
        if "method" in message:
            if "id" in message:
                self._handle_server_request(message)
            else:
                self._handle_notification(message)

    def _handle_notification(self, message: dict[str, Any]) -> None:
        method = str(message.get("method", ""))
        if method == "notifications/tools/list_changed":
            self._tool_cache = []
        elif method == "notifications/resources/list_changed":
            self._resource_cache = []
        elif method == "notifications/prompts/list_changed":
            self._prompt_cache = []

    def _handle_server_request(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = str(message.get("method", ""))
        if request_id is None:
            return
        if method == "ping":
            response = {"jsonrpc": "2.0", "id": request_id, "result": {}}
        elif method == "roots/list":
            response = {"jsonrpc": "2.0", "id": request_id, "result": {"roots": []}}
        else:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Client does not implement MCP method '{method}'"},
            }
        try:
            self._write_message(response)
        except MCPError:
            self.last_error = f"Failed to respond to MCP request '{method}' from '{self.server_name}'"

    def _read_stderr_loop(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for raw_line in process.stderr:
            line = raw_line.rstrip()
            if line:
                self._stderr_buffer.append(line)

    def _connect_http(self) -> None:
        if not self.url:
            raise MCPTransportError(f"MCP server '{self.server_name}' is missing a URL for HTTP transport")
        self._http_client = httpx.Client(timeout=self.request_timeout_seconds)
        self.last_started_at = time.time()
        result = self._send_http_request(
            "initialize",
            {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {
                    "roots": {"listChanged": False},
                    "sampling": {},
                },
                "clientInfo": {
                    "name": "AgentHub",
                    "title": "AgentHub MCP Client",
                    "version": "0.1.0",
                },
            },
            timeout_seconds=self.startup_timeout_seconds,
            allow_unconnected=True,
        )
        self.protocol_version = str(result.get("protocolVersion", DEFAULT_PROTOCOL_VERSION))
        self.server_info = dict(result.get("serverInfo", {}))
        self.capabilities = dict(result.get("capabilities", {}))
        self.connected = True
        try:
            self._send_http_notification("notifications/initialized")
        except Exception:
            pass

    def _send_http_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self._http_client is None:
            raise MCPTransportError(f"MCP server '{self.server_name}' is not running")
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        response = self._http_client.post(
            self.url,
            json=payload,
            headers=self._build_http_headers(),
        )
        if response.status_code >= 400:
            self.last_error = f"HTTP notification failed with status {response.status_code}"

    def _send_http_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
        allow_unconnected: bool = False,
        _retry_on_session_loss: bool = True,
    ) -> dict[str, Any]:
        if not allow_unconnected:
            self.ensure_connected()
        if self._http_client is None:
            raise MCPTransportError(f"MCP server '{self.server_name}' is not running")
        request_id = next(self._request_counter)
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        try:
            response = self._http_client.post(
                self.url,
                json=payload,
                headers=self._build_http_headers(),
                timeout=timeout_seconds or self.request_timeout_seconds,
            )
        except Exception as exc:
            self.last_error = str(exc)
            raise MCPTransportError(f"HTTP MCP request to '{self.server_name}' failed: {exc}") from exc
        if response.status_code == 404 and self.session_id and _retry_on_session_loss and method != "initialize":
            self.session_id = ""
            self.connected = False
            self.connect()
            return self._send_http_request(
                method,
                params,
                timeout_seconds=timeout_seconds,
                allow_unconnected=False,
                _retry_on_session_loss=False,
            )
        self._capture_http_session(response)
        if response.status_code >= 400:
            message = self._extract_http_error_message(response)
            self.last_error = message
            raise MCPTransportError(message)
        message = self._decode_http_rpc_response(response, expected_id=request_id)
        if "error" in message:
            error = message["error"] or {}
            raise MCPProtocolError(
                str(error.get("message", f"MCP request '{method}' failed")),
                code=error.get("code"),
                data=error.get("data"),
            )
        return dict(message.get("result", {}))

    def _capture_http_session(self, response: httpx.Response) -> None:
        session_header = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
        if session_header:
            self.session_id = session_header

    def _build_http_headers(self, *, include_accept: bool = True) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "MCP-Protocol-Version": self.protocol_version or DEFAULT_PROTOCOL_VERSION,
        }
        if include_accept:
            headers["Accept"] = "application/json, text/event-stream"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        headers.update(self.headers)
        return headers

    def _decode_http_rpc_response(self, response: httpx.Response, *, expected_id: int) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type or response.text.strip().startswith("{"):
            try:
                payload = response.json()
            except Exception as exc:
                raise MCPTransportError(f"Invalid JSON response from MCP server '{self.server_name}': {exc}") from exc
            if not isinstance(payload, dict):
                raise MCPTransportError(f"MCP server '{self.server_name}' returned non-object JSON response")
            return payload
        if "text/event-stream" in content_type:
            return self._decode_sse_rpc_response(response, expected_id=expected_id)
        raise MCPTransportError(
            f"Unsupported HTTP response content-type from MCP server '{self.server_name}': {content_type or 'unknown'}"
        )

    def _decode_sse_rpc_response(self, response: httpx.Response, *, expected_id: int) -> dict[str, Any]:
        event_data: list[str] = []
        with response:
            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line:
                    if not event_data:
                        continue
                    data = "\n".join(event_data)
                    event_data = []
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict) and payload.get("id") == expected_id and (
                        "result" in payload or "error" in payload
                    ):
                        return payload
                    continue
                if line.startswith("data:"):
                    event_data.append(line[5:].lstrip())
        raise MCPTransportError(f"Did not receive an MCP response event from '{self.server_name}'")

    def _extract_http_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            return f"HTTP MCP request failed with status {response.status_code}: {response.text[:400]}"
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
            if payload.get("message"):
                return str(payload["message"])
        return f"HTTP MCP request failed with status {response.status_code}"

    def _safe_headers_snapshot(self) -> dict[str, str]:
        masked: dict[str, str] = {}
        for key, value in self.headers.items():
            if key.lower() in {"authorization", "x-api-key", "api-key"}:
                masked[key] = "***"
            else:
                masked[key] = value
        return masked

    def __del__(self) -> None:
        try:
            self.close(force=False)
        except Exception:
            pass
