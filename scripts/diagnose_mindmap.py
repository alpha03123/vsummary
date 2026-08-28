"""Reproduce and time one mindmap request against an OpenAI-compatible server."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from backend.video_summary.generation import FlatMindmapPayload
from backend.video_summary.infrastructure.llm.litellm_mindmap_generator import build_mindmap_prompt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--model", default="vsummary-qwen35-4b")
    parser.add_argument("--timeout", type=float, default=360)
    parser.add_argument("--max-tokens", type=int, default=2048)
    return parser.parse_args()


def load_request_input(series_id: str, video_id: str) -> tuple[str, float, dict[str, Any], str]:
    output_dir = ROOT_DIR / "workspace" / series_id / video_id
    summary_path = output_dir / "summary.json"
    transcript_path = output_dir / "transcript.cleaned.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"Missing summary: {summary_path}")
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    transcript_data = json.loads(transcript_path.read_text(encoding="utf-8")) if transcript_path.is_file() else {}
    segments = transcript_data.get("segments", [])
    transcript_text = "\n".join(
        str(segment.get("text", "")) for segment in segments if isinstance(segment, dict)
    )
    chapters = summary_data.get("chapters", [])
    duration_seconds = float(chapters[-1].get("end_seconds", 0) or 0) if chapters else 0.0
    return video_id, duration_seconds, summary_data, transcript_text


def sse_events(response: httpx.Response) -> Iterator[dict[str, Any]]:
    for line in response.iter_lines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            return
        yield json.loads(payload)


def main() -> int:
    args = parse_args()
    title, duration_seconds, summary_data, transcript_text = load_request_input(args.series, args.video)
    prompt = build_mindmap_prompt(
        title=title,
        duration_seconds=duration_seconds,
        summary_data=summary_data,
        transcript_text=transcript_text,
        output_encoding="flat",
    )
    schema = FlatMindmapPayload.model_json_schema()
    request = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": args.max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "reasoning_effort": "none",
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "mindmap", "strict": True, "schema": schema},
        },
    }
    report = {
        "model": args.model,
        "prompt_characters": len(prompt),
        "summary_json_characters": len(json.dumps(summary_data, ensure_ascii=False)),
        "transcript_characters_in_prompt": len(transcript_text[:3000]),
        "first_event_seconds": None,
        "first_reasoning_seconds": None,
        "first_content_seconds": None,
        "reasoning": "",
        "content": "",
        "finish_reason": None,
        "usage": None,
        "error": None,
    }
    started = time.monotonic()
    endpoint = f"{args.base_url.rstrip('/')}/chat/completions"
    try:
        with httpx.Client(timeout=httpx.Timeout(args.timeout, connect=10)) as client:
            with client.stream("POST", endpoint, json=request) as response:
                response.raise_for_status()
                for event in sse_events(response):
                    elapsed = round(time.monotonic() - started, 3)
                    if report["first_event_seconds"] is None:
                        report["first_event_seconds"] = elapsed
                    for choice in event.get("choices", []):
                        delta = choice.get("delta", {})
                        reasoning = delta.get("reasoning_content") or ""
                        content = delta.get("content") or ""
                        if reasoning:
                            if report["first_reasoning_seconds"] is None:
                                report["first_reasoning_seconds"] = elapsed
                            report["reasoning"] += reasoning
                        if content:
                            if report["first_content_seconds"] is None:
                                report["first_content_seconds"] = elapsed
                            report["content"] += content
                        report["finish_reason"] = choice.get("finish_reason") or report["finish_reason"]
                    if event.get("usage"):
                        report["usage"] = event["usage"]
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        report["total_seconds"] = round(time.monotonic() - started, 3)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
