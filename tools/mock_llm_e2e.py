"""Run the CI-safe full workflow against a local OpenAI-compatible mock.

The application, its HTTP API, durable jobs, media storage, subtitle extraction,
and Agent graph are real.  Only its outgoing LLM provider is replaced.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.e2e_support.api_client import LocalApiClient
from tools.e2e_support.assertions import require_generated_tools
from tools.e2e_support.jobs import wait_for_job, wait_for_video_processed
from tools.e2e_support.resources import E2EResourceScope


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--source-path", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=ROOT / "temp" / "mock-llm-e2e" / "latest.json")
    args = parser.parse_args()
    result = run(args.base_url, args.source_path)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run(base_url: str, source_path: Path) -> dict[str, Any]:
    source_path = source_path.resolve()
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise ValueError(f"CI E2E source media is missing or empty: {source_path}")
    client = LocalApiClient(base_url)
    try:
        client.health()
        provider = client.provider_settings()
        if not provider.get("has_openai_api_key"):
            raise RuntimeError("CI E2E requires the non-secret mock provider key to be configured.")
        client.probe_provider(provider)
        rag_job = client.submit_rag_model_download("embedding")
        wait_for_job(client, str(rag_job["job_id"]), action="CI RAG embedding preparation", timeout_seconds=600)
        with E2EResourceScope(client) as resources:
            imported = client.import_local_series(title="CI Mock LLM E2E", source_paths=[source_path])
            series_id = str(imported["id"])
            video = imported["videos"][0]
            video_id = str(video["id"])
            resources.track_series(series_id, video_id)

            generation_job = resources.track_job(client.submit_series_generation(series_id))
            wait_for_job(client, generation_job, action="CI summary generation")
            wait_for_video_processed(client, series_id, video_id)

            summary = client.get_summary(series_id, video_id)
            transcript = client.get_transcript(series_id, video_id)
            subtitles = client.get_subtitles(series_id, video_id)
            preview = client.get_preview(series_id, video_id, byte_range="bytes=0-0")
            exported = client.get_export(series_id, video_id, "summary.md")

            ai_summary_job = resources.track_job(client.submit_ai_summary(series_id, video_id, template="tutorial"))
            wait_for_job(client, ai_summary_job, action="CI AI summary")
            ai_summary = client.get_ai_summary(series_id, video_id)

            cards_job = resources.track_job(client.submit_knowledge_cards(series_id, video_id))
            wait_for_job(client, cards_job, action="CI knowledge cards")
            cards = client.get_knowledge_cards(series_id, video_id)

            mindmap_job = resources.track_job(client.submit_mindmap(series_id, video_id, max_depth=3))
            wait_for_job(client, mindmap_job, action="CI mindmap")
            mindmap = client.get_mindmap(series_id, video_id)

            video_chat = client.chat(_chat_payload("video", series_id, imported["title"], video_id, video["title"]))
            series_chat = client.chat(_chat_payload("series", series_id, imported["title"]))
            tools = client.get_tools(series_id, video_id)
            _assert_workflow(
                summary=summary,
                transcript=transcript,
                subtitles_content_type=subtitles.headers.get("content-type", ""),
                preview_content_type=preview.headers.get("content-type", ""),
                exported=exported,
                ai_summary=ai_summary,
                cards=cards,
                mindmap=mindmap,
                tools=tools,
                video_chat=video_chat,
                series_chat=series_chat,
                series_id=series_id,
                video_id=video_id,
            )
            return {
                "provider": provider["llm_provider"],
                "model": provider["openai_model"],
                "test_series_id": series_id,
                "test_video_id": video_id,
                "generation_job_id": generation_job,
                "rag_embedding_job_id": rag_job["job_id"],
                "ai_summary_job_id": ai_summary_job,
                "knowledge_cards_job_id": cards_job,
                "mindmap_job_id": mindmap_job,
                "summary_chapter_count": len(summary["chapters"]),
                "knowledge_card_count": len(cards["cards"]),
                "video_talk_citation_count": len(video_chat["citations"]),
                "series_talk_citation_count": len(series_chat["citations"]),
                "cleanup": "deleted",
            }
    finally:
        client.close()


def _chat_payload(scope_type: str, series_id: str, series_title: str, video_id: str | None = None, video_title: str | None = None) -> dict[str, object]:
    context: dict[str, object] = {"scope_type": scope_type, "series_id": series_id, "series_title": series_title}
    if video_id is not None:
        context.update({"video_id": video_id, "video_title": video_title})
    return {
        "session_id": f"{scope_type}|{series_id}|{video_id or 'all'}::mock-llm-e2e",
        "message": "What can be confirmed from the generated transcript and summary?",
        "context": context,
    }


def _assert_workflow(*, summary: dict[str, Any], transcript: dict[str, Any], subtitles_content_type: str, preview_content_type: str, exported: str, ai_summary: dict[str, Any], cards: dict[str, Any], mindmap: dict[str, Any], tools: dict[str, Any], video_chat: dict[str, Any], series_chat: dict[str, Any], series_id: str, video_id: str) -> None:
    if not summary.get("chapters") or not transcript.get("segments") or not exported.strip():
        raise RuntimeError("Summary, transcript, or export artifact is incomplete.")
    if "text/vtt" not in subtitles_content_type or not preview_content_type.startswith("video/"):
        raise RuntimeError("Subtitle or media preview endpoint did not return a usable response.")
    if not ai_summary.get("content") or not ai_summary.get("citations"):
        raise RuntimeError("AI summary artifact is incomplete.")
    if not cards.get("cards") or not mindmap.get("title") or not mindmap.get("children"):
        raise RuntimeError("Knowledge cards or mindmap artifact is incomplete.")
    require_generated_tools(tools, "overview", "ai_summary", "knowledge_cards", "mindmap")
    _assert_talk_scope(video_chat, expected_series_id=series_id, expected_video_id=video_id, label="video")
    _assert_talk_scope(series_chat, expected_series_id=series_id, expected_video_id=video_id, label="series")


def _assert_talk_scope(chat: dict[str, Any], *, expected_series_id: str, expected_video_id: str, label: str) -> None:
    if not chat.get("assistant_message") or not chat.get("citations"):
        raise RuntimeError(f"{label} Talk did not return an answer with citations.")
    citations = chat["citations"]
    if not isinstance(citations, list):
        raise RuntimeError(f"{label} Talk citations are not a list.")
    for citation in citations:
        slots = citation.get("slots")
        if not isinstance(slots, list) or not slots:
            raise RuntimeError(f"{label} Talk returned a citation without source slots.")
        for slot in slots:
            # Citation slots identify local media by video ID.  The CI workspace has
            # only this temporary series, so this also proves series-scope isolation.
            if slot.get("video_id") != expected_video_id:
                raise RuntimeError(f"{label} Talk cited content outside the temporary series/video.")


if __name__ == "__main__":
    main()
