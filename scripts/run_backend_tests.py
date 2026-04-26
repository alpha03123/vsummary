from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = Path(__file__).resolve()
PROJECT_PYTHON_REEXEC_ENV = "VSUMMARY_PROJECT_PYTHON_REEXEC"

TEST_GROUPS: dict[str, list[str]] = {
    "agent": [
        "tests.test_agent_context_loader",
        "tests.test_agent_tool_catalog",
        "tests.test_agent_library_info_tools",
        "tests.test_litellm_chat_gateway",
        "tests.test_agent_graph_scaffold",
        "tests.test_agent_graph_programs",
        "tests.test_agent_graph_retrieval",
        "tests.test_agent_graph_series_flow",
        "tests.test_agent_graph_video_flow",
        "tests.test_agent_graph_service",
        "tests.test_agent_graph_turn_result",
        "tests.test_agent_graph_actions",
        "tests.test_agent_graph_dspy_opt",
        "tests.test_agent_graph_multitask_flow",
        "tests.test_agent_graph_memory",
        "tests.test_agent_graph_memory_flow",
        "tests.test_agent_graph_speed_profile",
        "tests.test_agent_regression_utils",
        "tests.test_run_new_arch_long_tests",
        "tests.test_agent_graph_dependency_execution",
        "tests.test_agent_graph_program_loader",
        "tests.test_agent_graph_program_loader",
    ],
    "api": [
        "tests.test_api",
    ],
    "workspace": [
        "tests.test_filesystem_video_workspace",
        "tests.test_progress_tracker",
    ],
    "summary": [
        "tests.test_generate_summary",
        "tests.test_litellm_video_summary_infrastructure",
        "tests.test_video_summary_workflow",
    ],
    "fast": [
        "tests.test_agent_context_loader",
        "tests.test_agent_tool_catalog",
        "tests.test_agent_library_info_tools",
        "tests.test_litellm_chat_gateway",
        "tests.test_litellm_video_summary_infrastructure",
        "tests.test_filesystem_video_workspace",
        "tests.test_progress_tracker",
        "tests.test_agent_graph_scaffold",
        "tests.test_agent_graph_programs",
        "tests.test_agent_graph_retrieval",
        "tests.test_agent_graph_series_flow",
        "tests.test_agent_graph_video_flow",
        "tests.test_agent_graph_service",
        "tests.test_agent_graph_turn_result",
        "tests.test_agent_graph_actions",
        "tests.test_agent_graph_dspy_opt",
        "tests.test_agent_graph_multitask_flow",
        "tests.test_agent_graph_memory",
        "tests.test_agent_graph_memory_flow",
        "tests.test_agent_graph_speed_profile",
        "tests.test_agent_regression_utils",
        "tests.test_run_new_arch_long_tests",
        "tests.test_agent_graph_dependency_execution",
        "tests.test_agent_graph_program_loader",
        "tests.test_agent_graph_program_loader",
    ],
    "all": [
        "tests.test_agent_context_loader",
        "tests.test_agent_tool_catalog",
        "tests.test_agent_library_info_tools",
        "tests.test_litellm_chat_gateway",
        "tests.test_litellm_video_summary_infrastructure",
        "tests.test_api",
        "tests.test_filesystem_video_workspace",
        "tests.test_generate_summary",
        "tests.test_progress_tracker",
        "tests.test_video_summary_workflow",
        "tests.test_agent_graph_scaffold",
        "tests.test_agent_graph_programs",
        "tests.test_agent_graph_retrieval",
        "tests.test_agent_graph_series_flow",
        "tests.test_agent_graph_video_flow",
        "tests.test_agent_graph_service",
        "tests.test_agent_graph_turn_result",
        "tests.test_agent_graph_actions",
        "tests.test_agent_graph_dspy_opt",
        "tests.test_agent_graph_multitask_flow",
        "tests.test_agent_graph_memory",
        "tests.test_agent_graph_memory_flow",
        "tests.test_agent_graph_speed_profile",
        "tests.test_agent_regression_utils",
        "tests.test_run_new_arch_long_tests",
        "tests.test_agent_graph_dependency_execution",
        "tests.test_agent_graph_program_loader",
        "tests.test_agent_graph_program_loader",
    ],
}


def _normalize_target(target: str) -> str:
    normalized = target.strip()
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    normalized = normalized.replace("\\", ".").replace("/", ".")
    return normalized


def _resolve_modules(targets: list[str]) -> list[str]:
    resolved: list[str] = []
    for target in targets:
        normalized = _normalize_target(target)
        modules = TEST_GROUPS.get(normalized, [normalized])
        for module in modules:
            if module not in resolved:
                resolved.append(module)
    return resolved


def resolve_project_python(
    *,
    root_dir: Path | None = None,
    current_executable: str | None = None,
) -> Path:
    resolved_root = root_dir or ROOT
    project_python = resolved_root / ".venv" / "Scripts" / "python.exe"
    if project_python.exists():
        return project_python
    return Path(current_executable or sys.executable).resolve()


def _should_reexec_with_project_python(*, project_python: Path) -> bool:
    if not project_python.exists():
        return False
    if os.environ.get(PROJECT_PYTHON_REEXEC_ENV) == "1":
        return False
    current_python = Path(sys.executable).resolve()
    return current_python != project_python.resolve()


def main() -> int:
    project_python = resolve_project_python()
    if _should_reexec_with_project_python(project_python=project_python):
        env = dict(os.environ)
        env[PROJECT_PYTHON_REEXEC_ENV] = "1"
        command = [str(project_python), str(SCRIPT_PATH), *sys.argv[1:]]
        print(f"Re-entering project Python: {project_python}")
        completed = subprocess.run(command, cwd=ROOT, env=env)
        return completed.returncode

    parser = argparse.ArgumentParser(
        description="按职责或指定模块运行后端 unittest，避免每次都跑整套测试。",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="测试组名称或 unittest 模块名，默认 fast。",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有测试组及其包含的测试模块。",
    )
    args = parser.parse_args()

    if args.list:
        for group_name, modules in TEST_GROUPS.items():
            print(f"[{group_name}]")
            for module in modules:
                print(f"  - {module}")
        return 0

    requested_targets = args.targets or ["fast"]
    modules = _resolve_modules(requested_targets)
    command = [sys.executable, "-m", "unittest", "-v", *modules]
    print(f"Running targets: {', '.join(requested_targets)}")
    print(" ".join(command))
    completed = subprocess.run(command, cwd=ROOT)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
