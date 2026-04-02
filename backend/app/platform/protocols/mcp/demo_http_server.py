from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from app.platform.protocols.mcp.demo_server import PROTOCOL_VERSION, PROMPTS, RESOURCES, TOOLS, _call_tool, _get_prompt, _read_resource


SESSION_ID = "agenthub-demo-http-session"


class DemoHTTPMCPHandler(BaseHTTPRequestHandler):
    server_version = "AgentHubDemoMCP/0.1"
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_json_body()
        request_id = body.get("id")
        method = str(body.get("method", ""))
        params = dict(body.get("params", {}))

        if method == "initialize":
            self._send_json(
                {
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
                            "name": "agenthub-demo-http-mcp",
                            "version": "0.1.0",
                            "description": "HTTP MCP demo server for AgentHub",
                        },
                    },
                },
                headers={"Mcp-Session-Id": SESSION_ID},
            )
            return
        if method == "notifications/initialized":
            self._send_empty(202)
            return
        if method == "tools/list":
            self._send_json({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
            return
        if method == "tools/call":
            self._send_json({"jsonrpc": "2.0", "id": request_id, "result": _call_tool(str(params.get("name", "")), dict(params.get("arguments", {})))})
            return
        if method == "resources/list":
            self._send_json({"jsonrpc": "2.0", "id": request_id, "result": {"resources": RESOURCES}})
            return
        if method == "resources/read":
            self._send_json({"jsonrpc": "2.0", "id": request_id, "result": _read_resource(str(params.get("uri", "")))})
            return
        if method == "prompts/list":
            self._send_json({"jsonrpc": "2.0", "id": request_id, "result": {"prompts": PROMPTS}})
            return
        if method == "prompts/get":
            self._send_json({"jsonrpc": "2.0", "id": request_id, "result": _get_prompt(str(params.get("name", "")), dict(params.get("arguments", {})))})
            return
        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            },
            status=404,
        )

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_empty(204)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_json(self, payload: dict[str, Any], *, status: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), DemoHTTPMCPHandler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        threading.Thread(target=server.shutdown, daemon=True).start()


if __name__ == "__main__":
    run_server()
