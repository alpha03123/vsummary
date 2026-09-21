"""Run the Local real-LLM scenario against a disposable copied library video."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.e2e_support.api_client import LocalApiClient
from tools.e2e_support.assertions import require_generated_tools
from tools.e2e_support.jobs import wait_for_job, wait_for_video_processed
from tools.e2e_support.resources import E2EResourceScope


DEFAULT_WORK_DIR = ROOT / "temp" / "real-llm-e2e"
DEFAULT_REPORT = DEFAULT_WORK_DIR / "latest.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--source-series-id", default=None)
    parser.add_argument("--source-video-id", default=None)
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = run(args.base_url, args.work_dir, source_series_id=args.source_series_id, source_video_id=args.source_video_id)
    except Exception as error:
        failure = {
            "status": "failed",
            "base_url": args.base_url,
            "source_series_id": args.source_series_id,
            "source_video_id": args.source_video_id,
            "error": str(error),
        }
        args.report.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False, indent=2), file=sys.stderr)
        raise
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run(base_url: str, work_dir: Path, *, source_series_id: str | None = None, source_video_id: str | None = None) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    client = LocalApiClient(base_url)
    try:
        client.health()
        provider = client.provider_settings()
        if not provider.get("has_openai_api_key"):
            raise RuntimeError("Configured real LLM API key is required.")
        client.probe_provider(provider)
        source_series, source_video = _select_source_video(
            client.library(), source_series_id=source_series_id, source_video_id=source_video_id
        )
        with tempfile.TemporaryDirectory(prefix="library-media-", dir=work_dir) as temp_dir:
            media_path = Path(temp_dir) / "source.mp4"
            client.copy_preview_to(str(source_series["id"]), str(source_video["id"]), media_path)
            with E2EResourceScope(client) as resources:
                imported = client.import_local_series(
                    title=f"E2E Real LLM {datetime.now().strftime('%Y%m%d-%H%M%S')}", source_paths=[media_path]
                )
                series_id = str(imported["id"])
                video = imported["videos"][0]
                video_id = str(video["id"])
                resources.track_series(series_id, video_id)

                series_job_id = resources.track_job(client.submit_series_generation(series_id))
                wait_for_job(client, series_job_id, action="real series generation")
                wait_for_video_processed(client, series_id, video_id)

                summary = client.get_summary(series_id, video_id)
                ai_summary_job_id = resources.track_job(client.submit_ai_summary(series_id, video_id, template="tutorial"))
                wait_for_job(client, ai_summary_job_id, action="real AI summary")
                ai_summary = client.get_ai_summary(series_id, video_id)

                cards_job_id = resources.track_job(client.submit_knowledge_cards(series_id, video_id))
                wait_for_job(client, cards_job_id, action="real knowledge cards")
                cards = client.get_knowledge_cards(series_id, video_id)

                mindmap_job_id = resources.track_job(client.submit_mindmap(series_id, video_id, max_depth=3))
                wait_for_job(client, mindmap_job_id, action="real mindmap")
                mindmap = client.get_mindmap(series_id, video_id)

                tools = client.get_tools(series_id, video_id)
                transcript = client.get_transcript(series_id, video_id)
                preview = client.get_preview(series_id, video_id, byte_range="bytes=0-0")
                exported = client.get_export(series_id, video_id, "summary.md")
                chat = client.chat(
                    {
                        "session_id": f"video|{series_id}|{video_id}::real-llm-e2e",
                        "message": "What can be confirmed from this video's transcript and summary?",
                        "context": {
                            "scope_type": "video",
                            "series_id": series_id,
                            "series_title": imported["title"],
                            "video_id": video_id,
                            "video_title": video["title"],
                        },
                    }
                )
                _assert_artifacts(summary, ai_summary, cards, mindmap, tools, transcript, preview.headers.get("content-type", ""), exported, chat)
                return {
                    "source_series_id": source_series["id"],
                    "source_video_id": source_video["id"],
                    "test_series_id": series_id,
                    "test_video_id": video_id,
                    "provider": provider["llm_provider"],
                    "model": provider["openai_model"],
                    "series_generation_job_id": series_job_id,
                    "ai_summary_job_id": ai_summary_job_id,
                    "knowledge_cards_job_id": cards_job_id,
                    "mindmap_job_id": mindmap_job_id,
                    "summary_chapter_count": len(summary["chapters"]),
                    "ai_summary_citation_count": len(ai_summary["citations"]),
                    "knowledge_card_count": len(cards["cards"]),
                    "mindmap_root": mindmap["title"],
                    "agent_citation_count": len(chat["citations"]),
                    "cleanup": "deleted",
                }
    finally:
        client.close()


def _select_source_video(library: dict[str, Any], *, source_series_id: str | None, source_video_id: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    for series in library.get("series", []):
        if source_series_id is not None and series.get("id") != source_series_id:
            continue
        for video in series.get("videos", []):
            if source_video_id is not None and video.get("id") != source_video_id:
                continue
            if video.get("is_linked") is not True:
                return series, video
    raise RuntimeError("No locally available source video matched the requested E2E input.")


def _assert_artifacts(
    summary: dict[str, Any], ai_summary: dict[str, Any], cards: dict[str, Any], mindmap: dict[str, Any], tools: dict[str, Any],
    transcript: dict[str, Any], preview_content_type: str, exported: str, chat: dict[str, Any],
) -> None:
    if not summary.get("chapters") or not ai_summary.get("content") or not ai_summary.get("citations"):
        raise RuntimeError("Real LLM summary artifacts are incomplete.")
    if not cards.get("cards") or not mindmap.get("title") or not mindmap.get("children"):
        raise RuntimeError("Real LLM cards or mindmap are incomplete.")
    if not transcript.get("segments") or not exported.strip() or not chat.get("assistant_message") or not chat.get("citations"):
        raise RuntimeError("Transcript, export, or real Agent answer is incomplete.")
    if not preview_content_type.startswith("video/"):
        raise RuntimeError("Test video preview is not a usable video response.")
    require_generated_tools(tools, "overview", "ai_summary", "knowledge_cards", "mindmap")


if __name__ == "__main__":
    main()
