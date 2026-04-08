from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.apps.software_engineering.tools import parse_json_payload
from app.platform.core.message import Message, MessageRole
from app.platform.models.base import ModelRequest
from app.platform.tools.base import ToolContext
from app.platform.tools.executor import ToolExecutor

from .cases import SETaskEvalCase


BASELINE_PROMPT = """You are a coding assistant.
Given a software task and related repository snippets, return STRICT JSON with this schema:
{
  "summary": "...",
  "verify_command": "...",
  "edits": [
    {"path": "relative/path.py", "mode": "replace", "content": "full file content", "summary": "..."}
  ]
}
Rules:
- Edit only required files.
- Do not modify tests unless explicitly allowed.
- Always return valid JSON without markdown fences.
"""


def run_single_loop_case(*, orchestrator, case: SETaskEvalCase, workspace: Path, session_id: str) -> dict[str, Any]:
    tool_registry = orchestrator.build_tool_registry("software_engineering")
    tool_executor = ToolExecutor(tool_registry, trace_service=orchestrator.trace_service)
    context = ToolContext(
        app_id="software_engineering",
        session_id=session_id,
        user_id="se-eval",
        trace_id=orchestrator.trace_service.new_trace_id(),
        metadata={
            "repo_root": str(workspace),
            "allow_modify_tests": bool(case.constraints.get("allow_modify_tests", False)),
            "allow_install_dependency": bool(case.constraints.get("allow_install_dependency", False)),
            "allow_network": bool(case.constraints.get("allow_network", False)),
        },
    )

    tool_call_count = 0
    snippets = _collect_repo_context(case=case, tool_executor=tool_executor, context=context)
    tool_call_count += snippets["tool_calls"]

    prompt = _build_baseline_prompt(case=case, snippets=snippets["snippets"])
    payload = _call_model(orchestrator=orchestrator, prompt=prompt)
    edits = payload.get("edits", [])
    if not isinstance(edits, list):
        edits = []

    patch_count = 0
    if edits:
        patch_result = tool_executor.safe_execute_tool("patch_write_tool", {"files": edits}, context)
        tool_call_count += 1
        patch_count = len(patch_result.get("applied", [])) if isinstance(patch_result, dict) else 0

    verify_command = str(payload.get("verify_command", case.verify_command)).strip() or case.verify_command
    run_result = tool_executor.safe_execute_tool(
        "command_run_tool",
        {"command": verify_command, "timeout_seconds": 240},
        context,
    )
    tool_call_count += 1
    exit_code = int(run_result.get("exit_code", 1)) if isinstance(run_result, dict) else 1

    return {
        "status": "success" if exit_code == 0 else "failed",
        "mode": "single_loop",
        "iteration_count": 1,
        "tool_call_count": tool_call_count,
        "patch_count": patch_count,
        "verify_command": verify_command,
        "exit_code": exit_code,
        "stdout": str(run_result.get("stdout", "")) if isinstance(run_result, dict) else "",
        "stderr": str(run_result.get("stderr", "")) if isinstance(run_result, dict) else "",
        "raw_payload": payload,
    }


def _collect_repo_context(*, case: SETaskEvalCase, tool_executor: ToolExecutor, context: ToolContext) -> dict[str, Any]:
    tool_calls = 0
    snippets: list[str] = []
    search_result = tool_executor.safe_execute_tool("repo_search_tool", {"query": case.user_task, "limit": 5}, context)
    tool_calls += 1
    candidates = search_result.get("results", []) if isinstance(search_result, dict) else []
    for item in candidates[:3] if isinstance(candidates, list) else []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        read_result = tool_executor.safe_execute_tool("file_read_tool", {"path": path, "max_chars": 1800}, context)
        tool_calls += 1
        content = str(read_result.get("content", "")) if isinstance(read_result, dict) else ""
        if not content.strip():
            continue
        snippets.append(f"[{path}]\n{content[:1200]}")
    return {"tool_calls": tool_calls, "snippets": snippets}


def _build_baseline_prompt(*, case: SETaskEvalCase, snippets: list[str]) -> str:
    constraints = json.dumps(case.constraints, ensure_ascii=False)
    context_block = "\n\n".join(snippets[:3]) if snippets else "(no retrieved snippets)"
    return (
        f"{BASELINE_PROMPT}\n\n"
        f"Task type: {case.task_type}\n"
        f"Task: {case.user_task}\n"
        f"Verify command: {case.verify_command}\n"
        f"Constraints: {constraints}\n\n"
        f"Repository snippets:\n{context_block}"
    )


def _call_model(*, orchestrator, prompt: str) -> dict[str, Any]:
    request = ModelRequest(
        model=orchestrator.settings.llm_model,
        messages=[
            Message(role=MessageRole.SYSTEM, content="You are a precise coding assistant.").to_openai_dict(),
            Message(role=MessageRole.USER, content=prompt).to_openai_dict(),
        ],
        temperature=0.1,
        max_tokens=1800,
    )
    try:
        response = orchestrator.model_client.generate(request)
        payload = parse_json_payload(response.text)
        if payload:
            return payload
        start = response.text.find("{")
        end = response.text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return parse_json_payload(response.text[start : end + 1])
    except Exception:
        return {}
    return {}

