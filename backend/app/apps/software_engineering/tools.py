from __future__ import annotations

import difflib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from app.platform.tools.base import BaseTool, ToolContext, ToolParameter


TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".cfg",
    ".rst",
    ".env",
    ".tsx",
    ".ts",
    ".js",
    ".jsx",
    ".html",
    ".css",
    ".scss",
}

SKIP_DIR_PARTS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
}

SKIP_PATH_SUBSTRINGS = (
    "/backend/app/storage/",
    "/app/storage/",
    "/frontend/dist/",
)


def _resolve_repo_root(context: ToolContext, default_repo_root: Path) -> Path:
    root = str(context.metadata.get("repo_root", "")).strip()
    if not root:
        return default_repo_root
    return Path(root).resolve()


def _resolve_path(repo_root: Path, relative_path: str) -> Path:
    target = (repo_root / relative_path).resolve()
    if repo_root not in target.parents and target != repo_root:
        raise ValueError("Path escapes repository root")
    return target


def _is_test_path(relative_path: str) -> bool:
    lowered = relative_path.replace("\\", "/").lower()
    return lowered.startswith("tests/") or "/tests/" in lowered or lowered.endswith("_test.py") or lowered.endswith("test.py")


class RepoSearchTool(BaseTool):
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    @property
    def name(self) -> str:
        return "repo_search_tool"

    @property
    def description(self) -> str:
        return "Search repository text files by keyword."

    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="query", description="Search query", required=True),
            ToolParameter(name="limit", description="Max result count", required=False, param_type="integer"),
        ]

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip().lower()
        limit = int(arguments.get("limit", 8) or 8)
        if not query:
            return {"ok": False, "error": "query is required"}
        repo_root = _resolve_repo_root(context, self.repo_root)
        tokens = [token for token in query.split() if token]
        results: list[dict[str, Any]] = []
        for path in repo_root.rglob("*"):
            if not path.is_file():
                continue
            rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
            rel_parts = set(rel_path.split("/"))
            if rel_parts & SKIP_DIR_PARTS:
                continue
            lowered_rel_path = f"/{rel_path.lower()}"
            if any(marker in lowered_rel_path for marker in SKIP_PATH_SUBSTRINGS):
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            if path.stat().st_size > 512 * 1024:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lowered = text.lower()
            if not all(token in lowered for token in tokens):
                continue
            first = lowered.find(tokens[0])
            start = max(0, first - 120)
            end = min(len(text), first + 220)
            preview = text[start:end].replace("\n", " ").strip()
            results.append(
                {
                    "path": rel_path,
                    "preview": preview,
                    "score": sum(lowered.count(token) for token in tokens),
                }
            )
            if len(results) >= limit * 3:
                break
        results.sort(key=lambda item: float(item.get("score", 0)), reverse=True)
        return {"ok": True, "query": query, "results": results[:limit]}


class FileReadTool(BaseTool):
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    @property
    def name(self) -> str:
        return "file_read_tool"

    @property
    def description(self) -> str:
        return "Read file content from repository."

    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="path", description="Relative file path", required=True),
            ToolParameter(name="max_chars", description="Maximum returned chars", required=False, param_type="integer"),
        ]

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        relative_path = str(arguments.get("path", "")).strip()
        max_chars = int(arguments.get("max_chars", 12000) or 12000)
        if not relative_path:
            return {"ok": False, "error": "path is required"}
        repo_root = _resolve_repo_root(context, self.repo_root)
        target = _resolve_path(repo_root, relative_path)
        if not target.exists() or not target.is_file():
            return {"ok": False, "error": f"file not found: {relative_path}"}
        text = target.read_text(encoding="utf-8", errors="ignore")
        clipped = text[:max_chars]
        return {
            "ok": True,
            "path": str(target.relative_to(repo_root)).replace("\\", "/"),
            "content": clipped,
            "truncated": len(text) > len(clipped),
            "line_count": text.count("\n") + 1,
        }


class PatchWriteTool(BaseTool):
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    @property
    def name(self) -> str:
        return "patch_write_tool"

    @property
    def description(self) -> str:
        return "Write or append file content as patch operations."

    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="path", description="Relative file path", required=False),
            ToolParameter(name="content", description="File content", required=False),
            ToolParameter(name="mode", description="replace|append", required=False),
            ToolParameter(name="files", description="Batch file operations", required=False, param_type="array"),
        ]

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        allow_modify_tests = bool(context.metadata.get("allow_modify_tests", False))
        repo_root = _resolve_repo_root(context, self.repo_root)
        operations = self._normalize_operations(arguments)
        if not operations:
            return {"ok": False, "error": "no patch operations provided"}

        applied: list[dict[str, Any]] = []
        for item in operations:
            relative_path = str(item.get("path", "")).strip()
            mode = str(item.get("mode", "replace")).strip().lower()
            content = str(item.get("content", ""))
            if not relative_path:
                return {"ok": False, "error": "patch operation missing path"}
            if _is_test_path(relative_path) and not allow_modify_tests:
                return {"ok": False, "error": f"test modification blocked by constraints: {relative_path}"}
            target = _resolve_path(repo_root, relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            original = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else ""
            if mode == "append":
                next_text = f"{original}{content}"
            else:
                next_text = content
            target.write_text(next_text, encoding="utf-8")
            diff_preview = "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    next_text.splitlines(keepends=True),
                    fromfile=f"a/{relative_path}",
                    tofile=f"b/{relative_path}",
                    n=1,
                )
            )
            applied.append(
                {
                    "path": relative_path.replace("\\", "/"),
                    "mode": mode,
                    "summary": str(item.get("summary", "")).strip(),
                    "diff_preview": diff_preview[:2400],
                }
            )
        return {"ok": True, "applied": applied}

    @staticmethod
    def _normalize_operations(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        files = arguments.get("files")
        if isinstance(files, list):
            return [item for item in files if isinstance(item, dict)]
        if "path" in arguments and "content" in arguments:
            return [
                {
                    "path": arguments.get("path", ""),
                    "content": arguments.get("content", ""),
                    "mode": arguments.get("mode", "replace"),
                    "summary": arguments.get("summary", ""),
                }
            ]
        return []


class CommandRunTool(BaseTool):
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    @property
    def name(self) -> str:
        return "command_run_tool"

    @property
    def description(self) -> str:
        return "Run verification command and capture stdout/stderr."

    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="command", description="Command to execute", required=True),
            ToolParameter(name="timeout_seconds", description="Execution timeout", required=False, param_type="integer"),
            ToolParameter(name="cwd", description="Working directory relative to repo root", required=False),
        ]

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        command = str(arguments.get("command", "")).strip()
        timeout_seconds = int(arguments.get("timeout_seconds", 180) or 180)
        cwd_arg = str(arguments.get("cwd", "")).strip()
        if not command:
            return {"ok": False, "error": "command is required"}
        if self._looks_like_install(command) and not bool(context.metadata.get("allow_install_dependency", False)):
            return {"ok": False, "error": "dependency installation blocked by constraints"}

        repo_root = _resolve_repo_root(context, self.repo_root)
        if cwd_arg:
            workdir = _resolve_path(repo_root, cwd_arg)
            if not workdir.exists():
                return {"ok": False, "error": f"cwd not found: {cwd_arg}"}
        else:
            workdir = repo_root

        started = time.perf_counter()
        completed = subprocess.run(  # noqa: S603
            command,
            shell=True,  # noqa: S602
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        duration = time.perf_counter() - started
        return {
            "ok": completed.returncode == 0,
            "command": command,
            "cwd": str(workdir),
            "exit_code": completed.returncode,
            "duration_seconds": round(duration, 4),
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }

    @staticmethod
    def _looks_like_install(command: str) -> bool:
        lowered = command.strip().lower()
        return lowered.startswith("pip install") or " pip install " in lowered or lowered.startswith("python -m pip install")


class DependencyTool(BaseTool):
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    @property
    def name(self) -> str:
        return "dependency_tool"

    @property
    def description(self) -> str:
        return "Install dependency package when allowed by runtime constraints."

    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="package", description="Package spec (e.g. fastapi==0.114.0)", required=True),
        ]

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        if not bool(context.metadata.get("allow_install_dependency", False)):
            return {"ok": False, "error": "dependency installation blocked by constraints"}
        if not bool(context.metadata.get("allow_network", False)):
            return {"ok": False, "error": "network operations blocked by constraints"}
        package = str(arguments.get("package", "")).strip()
        if not package:
            return {"ok": False, "error": "package is required"}

        repo_root = _resolve_repo_root(context, self.repo_root)
        command = f'python -m pip install "{package}"'
        started = time.perf_counter()
        completed = subprocess.run(  # noqa: S603
            command,
            shell=True,  # noqa: S602
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        duration = time.perf_counter() - started
        return {
            "ok": completed.returncode == 0,
            "command": command,
            "exit_code": completed.returncode,
            "duration_seconds": round(duration, 4),
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
            "installed": package if completed.returncode == 0 else "",
        }


def build_software_engineering_tools(repo_root: Path) -> list[BaseTool]:
    return [
        RepoSearchTool(repo_root),
        FileReadTool(repo_root),
        PatchWriteTool(repo_root),
        CommandRunTool(repo_root),
        DependencyTool(repo_root),
    ]


def parse_json_payload(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    candidates: list[str] = [raw]
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL):
        block = str(match.group(1) or "").strip()
        if block:
            candidates.append(block)
    candidates.extend(_iter_json_object_candidates(raw))
    for candidate in candidates:
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            return loaded
    return {}


def _iter_json_object_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    start = -1
    depth = 0
    in_string = False
    escaped = False
    for idx, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = idx
            depth += 1
            continue
        if char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start != -1:
                snippet = text[start : idx + 1].strip()
                if snippet:
                    candidates.append(snippet)
                start = -1
    return candidates
