from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TEST_GROUPS: dict[str, list[str]] = {
    "agent": [
        "tests.test_agent_context_loader",
        "tests.test_agent_direct_action_response",
        "tests.test_agent_evidence_cache",
        "tests.test_agent_evidence_policy",
        "tests.test_agent_routed_answerer",
        "tests.test_agent_runtime_batching",
        "tests.test_agent_save_note_route",
        "tests.test_agent_series_locate_route",
        "tests.test_agent_stream_behavior",
        "tests.test_agent_scaffold",
        "tests.test_agent_prompt_contract",
        "tests.test_prompt_projection",
        "tests.test_request_router",
        "tests.test_series_locator",
        "tests.test_agent_tool_catalog",
        "tests.test_agent_video_transcript",
        "tests.test_series_evidence_selector",
        "tests.test_video_evidence_selector",
        "tests.test_agent_validation",
        "tests.test_litellm_chat_gateway",
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
        "tests.test_video_summary_workflow",
    ],
    "fast": [
        "tests.test_agent_context_loader",
        "tests.test_agent_direct_action_response",
        "tests.test_agent_evidence_cache",
        "tests.test_agent_evidence_policy",
        "tests.test_agent_routed_answerer",
        "tests.test_agent_runtime_batching",
        "tests.test_agent_save_note_route",
        "tests.test_agent_series_locate_route",
        "tests.test_agent_stream_behavior",
        "tests.test_agent_scaffold",
        "tests.test_agent_prompt_contract",
        "tests.test_prompt_projection",
        "tests.test_request_router",
        "tests.test_series_locator",
        "tests.test_agent_tool_catalog",
        "tests.test_agent_video_transcript",
        "tests.test_series_evidence_selector",
        "tests.test_video_evidence_selector",
        "tests.test_agent_validation",
        "tests.test_litellm_chat_gateway",
        "tests.test_filesystem_video_workspace",
        "tests.test_progress_tracker",
    ],
    "all": [
        "tests.test_agent_context_loader",
        "tests.test_agent_direct_action_response",
        "tests.test_agent_evidence_cache",
        "tests.test_agent_evidence_policy",
        "tests.test_agent_routed_answerer",
        "tests.test_agent_runtime_batching",
        "tests.test_agent_save_note_route",
        "tests.test_agent_series_locate_route",
        "tests.test_agent_stream_behavior",
        "tests.test_agent_scaffold",
        "tests.test_agent_prompt_contract",
        "tests.test_prompt_projection",
        "tests.test_request_router",
        "tests.test_series_locator",
        "tests.test_agent_tool_catalog",
        "tests.test_agent_video_transcript",
        "tests.test_series_evidence_selector",
        "tests.test_video_evidence_selector",
        "tests.test_agent_validation",
        "tests.test_litellm_chat_gateway",
        "tests.test_api",
        "tests.test_filesystem_video_workspace",
        "tests.test_generate_summary",
        "tests.test_progress_tracker",
        "tests.test_video_summary_workflow",
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


def main() -> int:
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
