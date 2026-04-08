from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.platform.runtime.orchestrator import get_orchestrator

from .baseline import run_single_loop_case
from .cases import SETaskEvalCase, load_eval_cases


@dataclass(slots=True)
class VerifyResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


def main() -> None:
    parser = argparse.ArgumentParser(description="Mini eval harness for Software Engineering Agent.")
    parser.add_argument("--mode", choices=["single_loop", "multi_agent_dynamic", "both"], default="both")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of cases for quick debug.")
    parser.add_argument("--keep-workspace", action="store_true", help="Keep temporary copied fixtures.")
    parser.add_argument("--output", type=str, default="", help="Optional output JSON file.")
    args = parser.parse_args()

    orchestrator = get_orchestrator()
    cases = load_eval_cases()
    if args.limit > 0:
        cases = cases[: args.limit]

    selected_modes = ["single_loop", "multi_agent_dynamic"] if args.mode == "both" else [args.mode]
    all_results: list[dict[str, Any]] = []

    for mode in selected_modes:
        for case in cases:
            result = run_case(
                orchestrator=orchestrator,
                case=case,
                mode=mode,
                keep_workspace=args.keep_workspace,
            )
            all_results.append(result)
            print(
                f"[{mode}] {case.case_id} -> {'PASS' if result['passed'] else 'FAIL'} "
                f"(duration={result['duration_seconds']:.2f}s, iterations={result['iteration_count']}, "
                f"tool_calls={result['tool_call_count']})"
            )

    summary = build_summary(all_results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def run_case(
    *,
    orchestrator,
    case: SETaskEvalCase,
    mode: str,
    keep_workspace: bool,
) -> dict[str, Any]:
    fixtures_root = Path(__file__).resolve().parent / "fixtures"
    workspace = _prepare_workspace(case=case, fixtures_root=fixtures_root)
    started = time.perf_counter()
    run_data: dict[str, Any]
    try:
        if mode == "multi_agent_dynamic":
            run_data = _run_harness_case(orchestrator=orchestrator, case=case, workspace=workspace)
        else:
            run_data = _run_single_loop_case(orchestrator=orchestrator, case=case, workspace=workspace)
        verify = _run_verify(command=case.verify_command, cwd=workspace)
        duration_seconds = time.perf_counter() - started
        passed = verify.exit_code == 0
        return {
            "mode": mode,
            "case_id": case.case_id,
            "title": case.title,
            "task_type": case.task_type,
            "passed": passed,
            "duration_seconds": round(duration_seconds, 4),
            "iteration_count": int(run_data.get("iteration_count", 0)),
            "tool_call_count": int(run_data.get("tool_call_count", 0)),
            "patch_count": int(run_data.get("patch_count", 0)),
            "run_status": str(run_data.get("status", "failed")),
            "verify_exit_code": verify.exit_code,
            "verify_stdout_tail": verify.stdout[-1200:],
            "verify_stderr_tail": verify.stderr[-1200:],
            "workspace": str(workspace),
            "session_id": str(run_data.get("session_id", "")),
            "raw": run_data,
        }
    finally:
        if not keep_workspace:
            shutil.rmtree(workspace, ignore_errors=True)


def _run_harness_case(*, orchestrator, case: SETaskEvalCase, workspace: Path) -> dict[str, Any]:
    session_id = f"se-eval-{case.case_id}-{int(time.time() * 1000)}"
    payload = {
        "task": case.user_task,
        "mode": case.mode,
        "verify_command": case.verify_command,
        "working_directory": str(workspace),
        "allow_modify_tests": bool(case.constraints.get("allow_modify_tests", False)),
        "allow_install_dependency": bool(case.constraints.get("allow_install_dependency", False)),
        "allow_network": bool(case.constraints.get("allow_network", False)),
        "max_iterations": int(case.constraints.get("max_iterations", 4)),
    }
    run_result = orchestrator.run_app(
        app_id="software_engineering",
        session_id=session_id,
        user_input=json.dumps(payload, ensure_ascii=False),
        user_id="se-eval",
    )
    record = orchestrator.se_run_store.get_run(session_id) or {}
    events = record.get("events", [])
    tool_call_count = sum(1 for event in events if isinstance(event, dict) and event.get("type") == "tool_call")
    return {
        "session_id": session_id,
        "status": str(run_result.get("status", record.get("status", "failed"))),
        "iteration_count": int(record.get("iteration_count", 0)),
        "tool_call_count": int(tool_call_count),
        "patch_count": len(record.get("patches", [])) if isinstance(record.get("patches"), list) else 0,
    }


def _run_single_loop_case(*, orchestrator, case: SETaskEvalCase, workspace: Path) -> dict[str, Any]:
    session_id = f"se-eval-baseline-{case.case_id}-{int(time.time() * 1000)}"
    result = run_single_loop_case(
        orchestrator=orchestrator,
        case=case,
        workspace=workspace,
        session_id=session_id,
    )
    result["session_id"] = session_id
    return result


def _run_verify(*, command: str, cwd: Path) -> VerifyResult:
    started = time.perf_counter()
    completed = subprocess.run(  # noqa: S603
        command,
        shell=True,  # noqa: S602
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=300,
    )
    duration_seconds = time.perf_counter() - started
    return VerifyResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_seconds=round(duration_seconds, 4),
    )


def _prepare_workspace(*, case: SETaskEvalCase, fixtures_root: Path) -> Path:
    source = case.fixture_path(fixtures_root)
    if not source.exists():
        raise FileNotFoundError(f"Fixture not found: {source}")
    target = Path(tempfile.mkdtemp(prefix=f"se_eval_{case.case_id}_"))
    shutil.copytree(source, target, dirs_exist_ok=True)
    return target


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        by_mode.setdefault(str(item.get("mode", "unknown")), []).append(item)

    summary_by_mode: dict[str, Any] = {}
    for mode, rows in by_mode.items():
        summary_by_mode[mode] = _aggregate_mode(rows)

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_runs": len(results),
        "modes": summary_by_mode,
        "results": results,
    }


def _aggregate_mode(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "success_rate": 0.0,
            "average_iterations": 0.0,
            "average_duration_seconds": 0.0,
            "average_tool_calls": 0.0,
            "task_type_success": {},
        }
    success_rate = sum(1 for row in rows if bool(row.get("passed"))) / len(rows)
    average_iterations = statistics.mean(float(row.get("iteration_count", 0)) for row in rows)
    average_duration_seconds = statistics.mean(float(row.get("duration_seconds", 0)) for row in rows)
    average_tool_calls = statistics.mean(float(row.get("tool_call_count", 0)) for row in rows)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_type.setdefault(str(row.get("task_type", "unknown")), []).append(row)
    task_type_success = {
        task_type: sum(1 for row in items if bool(row.get("passed"))) / max(1, len(items))
        for task_type, items in by_type.items()
    }
    return {
        "count": len(rows),
        "success_rate": round(success_rate, 4),
        "average_iterations": round(average_iterations, 4),
        "average_duration_seconds": round(average_duration_seconds, 4),
        "average_tool_calls": round(average_tool_calls, 4),
        "task_type_success": task_type_success,
    }


if __name__ == "__main__":
    main()

