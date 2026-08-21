"""对比递归树与扁平节点表两种思维导图输出协议。

此脚本只读取既有的 summary/transcript 制品，不触发转写、不会覆盖 mindmap.json。
结果写入指定目录，便于人工检查导图质量和记录耗时。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal

from backend.shared.llm.litellm_gateway import clear_structured_mode_cache
from backend.video_summary.generation import MindmapNodePayload
from backend.video_summary.infrastructure.config.settings import load_settings
from backend.video_summary.infrastructure.llm.litellm_mindmap_generator import LiteLLMMindmapGenerator
from backend.video_summary.infrastructure.video_summary_runtime import build_litellm_completion_gateway


@dataclass(frozen=True)
class ProtocolResult:
    encoding: str
    elapsed_seconds: float
    node_count: int
    max_depth: int
    root_title: str
    output_path: str


async def run_protocol(
    *,
    encoding: Literal["tree", "flat"],
    title: str,
    duration_seconds: float,
    summary_data: dict[str, object],
    transcript_text: str,
    root_dir: Path,
    output_dir: Path,
) -> ProtocolResult:
    settings = load_settings(root_dir / "config" / "settings.toml", root_dir)
    gateway = build_litellm_completion_gateway(settings)
    generator = LiteLLMMindmapGenerator(gateway, output_encoding=encoding)

    started_at = perf_counter()
    output = await generator.generate(
        title=title,
        duration_seconds=duration_seconds,
        summary_data=summary_data,
        transcript_text=transcript_text,
    )
    elapsed_seconds = perf_counter() - started_at
    tree = MindmapNodePayload.model_validate(output)
    output_path = output_dir / f"{encoding}.mindmap.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    node_count, max_depth = tree_metrics(tree)
    return ProtocolResult(
        encoding=encoding,
        elapsed_seconds=round(elapsed_seconds, 3),
        node_count=node_count,
        max_depth=max_depth,
        root_title=tree.title,
        output_path=str(output_path),
    )


def tree_metrics(node: MindmapNodePayload, depth: int = 1) -> tuple[int, int]:
    node_count = 1
    max_depth = depth
    for child in node.children:
        child_count, child_max_depth = tree_metrics(child, depth + 1)
        node_count += child_count
        max_depth = max(max_depth, child_max_depth)
    return node_count, max_depth


def load_transcript(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    payload = json.loads(path.read_text(encoding="utf-8"))
    segments = payload.get("segments", []) if isinstance(payload, dict) else []
    return "\n".join(
        segment.get("text", "")
        for segment in segments
        if isinstance(segment, dict) and isinstance(segment.get("text"), str)
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[1]
    summary_data = json.loads(args.summary.read_text(encoding="utf-8"))
    if not isinstance(summary_data, dict):
        raise ValueError("summary.json 必须是 JSON 对象。")
    title = str(summary_data.get("title") or args.summary.parent.name)
    duration_seconds = max(
        (
            float(chapter.get("end_seconds", 0))
            for chapter in summary_data.get("chapters", [])
            if isinstance(chapter, dict)
        ),
        default=0.0,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    transcript_text = load_transcript(args.transcript)

    results: list[ProtocolResult] = []
    for encoding in ("tree", "flat"):
        clear_structured_mode_cache()
        results.append(
            await run_protocol(
                encoding=encoding,
                title=title,
                duration_seconds=duration_seconds,
                summary_data=summary_data,
                transcript_text=transcript_text,
                root_dir=root_dir,
                output_dir=args.output_dir,
            )
        )

    report_path = args.output_dir / "report.json"
    report_path.write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(report_path)
    for result in results:
        print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
