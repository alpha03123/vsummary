from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="统一运行 assistant 重构回归脚本。")
    parser.add_argument(
        "--fake",
        action="store_true",
        help="显式只跑本地单测与假数据脚本。",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="额外触发真实模型脚本。",
    )
    parser.add_argument(
        "--mode",
        choices=("fake", "live"),
        default=None,
        help="fake 只跑本地单测与假数据脚本；live 会额外触发真实模型脚本。",
    )
    parser.add_argument(
        "--providers",
        nargs="*",
        default=None,
        help="预留的 provider 过滤参数；当前仅支持 openai_compatible。",
    )
    parser.add_argument(
        "--cases",
        nargs="*",
        default=None,
        help="传给 live 脚本的 case 过滤列表。",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="跳过 unittest 测试组。",
    )
    parser.add_argument(
        "--skip-provider",
        action="store_true",
        help="跳过 provider probe。",
    )
    parser.add_argument(
        "--skip-tool-catalog",
        action="store_true",
        help="跳过工具目录导出。",
    )
    parser.add_argument(
        "--skip-prompt-report",
        action="store_true",
        help="跳过 prompt size report。",
    )
    parser.add_argument(
        "--skip-evidence-policy",
        action="store_true",
        help="跳过 evidence policy cases。",
    )
    parser.add_argument(
        "--skip-batch-probe",
        action="store_true",
        help="跳过 series batch probe。",
    )
    parser.add_argument(
        "--skip-video-evidence",
        action="store_true",
        help="跳过 video evidence selector cases。",
    )
    parser.add_argument(
        "--skip-series-evidence",
        action="store_true",
        help="跳过 series evidence selector cases。",
    )
    parser.add_argument(
        "--skip-request-router",
        action="store_true",
        help="跳过 request router cases。",
    )
    args = parser.parse_args()

    mode = _resolve_mode(args)
    _validate_providers(args.providers)

    steps: list[tuple[str, list[str]]] = []
    if not args.skip_tests:
        steps.append(("backend-tests(agent)", [sys.executable, ".\\scripts\\run_backend_tests.py", "agent"]))
        steps.append(("backend-tests(api)", [sys.executable, ".\\scripts\\run_backend_tests.py", "api"]))
    if not args.skip_provider:
        steps.append(("provider-probe", [sys.executable, ".\\scripts\\run_agent_provider_probe.py"]))
    if not args.skip_tool_catalog:
        steps.append(("tool-catalog-dump", [sys.executable, ".\\scripts\\run_tool_catalog_dump.py"]))
    if not args.skip_prompt_report:
        steps.append(("prompt-size-report", [sys.executable, ".\\scripts\\run_prompt_size_report.py"]))
    if not args.skip_evidence_policy:
        steps.append(("evidence-policy-cases", [sys.executable, ".\\scripts\\run_evidence_policy_cases.py"]))
    if not args.skip_batch_probe:
        steps.append(("series-batch-probe", [sys.executable, ".\\scripts\\run_series_batch_probe.py"]))
    if not args.skip_video_evidence:
        steps.append(("video-evidence-selector-cases", [sys.executable, ".\\scripts\\run_video_evidence_selector_cases.py"]))
    if not args.skip_series_evidence:
        steps.append(("series-evidence-selector-cases", [sys.executable, ".\\scripts\\run_series_evidence_selector_cases.py"]))
    if not args.skip_request_router:
        steps.append(("request-router-cases", [sys.executable, ".\\scripts\\run_request_router_cases.py"]))
    if mode == "live":
        live_command = [sys.executable, ".\\scripts\\run_agent_manual_cases.py", "--manual"]
        if args.cases:
            live_command.extend(["--cases", *args.cases])
        steps.append(("live-manual-cases", live_command))

    for label, command in steps:
        print(f"=== running: {label} ===")
        print(" ".join(command))
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if completed.stdout:
            print("--- stdout ---")
            print(completed.stdout.rstrip())
        if completed.stderr:
            print("--- stderr ---")
            print(completed.stderr.rstrip())
        if completed.returncode != 0:
            print(f"[failed] {label} exited with {completed.returncode}")
            return completed.returncode
        print(f"[ok] {label}")
        print()

    print("=== assistant-regressions ===")
    print(f"mode: {mode}")
    if args.providers:
        print(f"providers: {', '.join(args.providers)}")
    if args.cases:
        print(f"cases: {', '.join(args.cases)}")
    print("status: ok")
    return 0


def _resolve_mode(args) -> str:
    if args.fake and args.live:
        raise SystemExit("--fake 和 --live 不能同时使用。")
    if args.live:
        return "live"
    if args.fake:
        return "fake"
    if args.mode is not None:
        return args.mode
    return "fake"


def _validate_providers(providers: list[str] | None) -> None:
    if not providers:
        return
    unsupported = [
        provider
        for provider in providers
        if provider.strip() and provider.strip() != "openai_compatible"
    ]
    if unsupported:
        raise SystemExit(f"当前回归入口仅支持 openai_compatible，收到: {', '.join(unsupported)}")


if __name__ == "__main__":
    raise SystemExit(main())
