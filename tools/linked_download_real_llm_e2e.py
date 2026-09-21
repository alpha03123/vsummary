"""Validate a real linked-video download, regeneration, and cited Agent chat."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.e2e_support.api_client import CoreApiClient
from tools.e2e_support.assertions import require_generated_tools
from tools.e2e_support.jobs import wait_for_job, wait_for_video_source


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "temp" / "linked-download-real-llm-e2e.json")
    args = parser.parse_args()
    result = run(args.base_url, args.series_id, args.video_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run(base_url: str, series_id: str, video_id: str) -> dict[str, Any]:
    client = CoreApiClient(base_url)
    try:
        client.health()
        series, video = _find_video(client.library(), series_id, video_id)
        if not video["is_linked"] or video["status"] != "linked":
            raise RuntimeError("E2E input must be an unresolved linked video; refusing to skip the download stage.")

        download = client.start_linked_download(series_id, video_id)
        download_job = wait_for_job(client, str(download["job_id"]), action="linked video download")
        wait_for_video_source(client, series_id, video_id)

        first_generation = client.submit_video_generation(series_id, video_id)
        wait_for_job(client, str(first_generation["job_id"]), action="first generated summary")
        first_summary = client.get_summary(series_id, video_id)
        regenerated = client.submit_video_generation(series_id, video_id)
        wait_for_job(client, str(regenerated["job_id"]), action="regenerated summary")
        regenerated_summary = client.get_summary(series_id, video_id)
        preview = client.get_preview(series_id, video_id)
        video_chat = client.chat(
            {
                "session_id": f"video|{series_id}|{video_id}::linked-download-real-e2e",
                "message": "What can be confirmed from the current video's generated transcript and summary?",
                "context": {"scope_type": "video", "series_id": series_id, "series_title": series["title"], "video_id": video_id, "video_title": video["title"]},
            }
        )
        series_chat = client.chat(
            {
                "session_id": f"series|{series_id}::linked-download-real-e2e",
                "message": "Which videos in this series have generated summaries, and what shared themes can be inferred?",
                "context": {"scope_type": "series", "series_id": series_id, "series_title": series["title"]},
            }
        )
        tools = client.get_tools(series_id, video_id)
    finally:
        client.close()

    if not first_summary.get("chapters") or not regenerated_summary.get("chapters"):
        raise RuntimeError("First generation or regeneration produced no chapters.")
    if not preview.headers.get("content-type", "").startswith("video/"):
        raise RuntimeError("Downloaded media preview is not a usable video response.")
    if not video_chat.get("assistant_message") or not video_chat.get("citations"):
        raise RuntimeError("Video scoped chat did not return a cited answer.")
    if not series_chat.get("assistant_message") or not series_chat.get("citations"):
        raise RuntimeError("Series scoped chat did not return a cited answer.")
    require_generated_tools(tools, "overview")
    return {
        "series_id": series_id,
        "video_id": video_id,
        "download_job_id": download_job["job_id"],
        "first_summary_job_id": first_generation["job_id"],
        "regenerated_summary_job_id": regenerated["job_id"],
        "first_summary_chapter_count": len(first_summary["chapters"]),
        "regenerated_summary_chapter_count": len(regenerated_summary["chapters"]),
        "video_chat_citation_count": len(video_chat["citations"]),
        "series_chat_citation_count": len(series_chat["citations"]),
        "preview_content_type": preview.headers.get("content-type"),
        "tool_status": tools,
    }


def _find_video(library: dict[str, Any], series_id: str, video_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    series = next((item for item in library["series"] if item["id"] == series_id), None)
    if series is None:
        raise RuntimeError(f"Series does not exist: {series_id}")
    video = next((item for item in series["videos"] if item["id"] == video_id), None)
    if video is None:
        raise RuntimeError(f"Video does not exist: {series_id}/{video_id}")
    return series, video


if __name__ == "__main__":
    main()
