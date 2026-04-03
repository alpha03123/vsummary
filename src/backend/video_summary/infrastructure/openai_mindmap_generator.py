from __future__ import annotations

import json
from pathlib import Path

from backend.video_summary.generation.ports import MindmapGenerator
from backend.video_summary.infrastructure.openai_summary import OpenAIResponsesGateway, parse_mindmap_payload


class OpenAIMindmapGenerator(MindmapGenerator):
    def __init__(self, model: str, base_url: str, api_key: str) -> None:
        self._gateway = OpenAIResponsesGateway(model=model, base_url=base_url, api_key=api_key)

    def generate(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
        output_dir: Path,
    ) -> dict[str, object]:
        prompt = build_mindmap_prompt(title=title, duration_seconds=duration_seconds, summary_data=summary_data)
        mindmap = parse_mindmap_payload(self._gateway.create_text(prompt), title=title, duration_seconds=duration_seconds)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "mindmap.json").write_text(json.dumps(mindmap, ensure_ascii=False, indent=2), encoding="utf-8")
        return mindmap


def build_mindmap_prompt(*, title: str, duration_seconds: float, summary_data: dict[str, object]) -> str:
    return (
        "请基于以下视频概况信息，生成一个适合前端交互展示的思维导图 JSON。\n"
        "要求：\n"
        "1. 只输出 JSON，不要输出额外解释。\n"
        "2. 不要编造 summary 中不存在的信息。\n"
        "3. 导图节点必须是树结构，且每个节点都包含 id、title、summary、start_seconds、end_seconds、children。\n"
        "4. 一级节点尽量对应视频主章节，二三级节点用于展开要点。\n"
        "5. 时间范围必须落在视频时长内。\n\n"
        f"视频标题：{title}\n"
        f"视频时长秒数：{int(duration_seconds)}\n"
        "概况 JSON：\n"
        f"{json.dumps(summary_data, ensure_ascii=False, indent=2)}\n"
    )
