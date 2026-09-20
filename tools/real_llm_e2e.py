"""Run a cleanup-guaranteed real-LLM E2E using media from the current library.

The script copies one existing, locally available library video into an isolated series,
then uses production APIs for the series summary pipeline, AI summary, cards and mindmap.
It never injects fake generators, fake transcripts or fake LLM responses. The temporary
series is deleted in ``finally`` even if an assertion fails.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
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
    result = run(
        args.base_url.rstrip("/"),
        args.work_dir,
        source_series_id=args.source_series_id,
        source_video_id=args.source_video_id,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run(
    base_url: str,
    work_dir: Path,
    *,
    source_series_id: str | None = None,
    source_video_id: str | None = None,
) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    series_id: str | None = None
    result: dict[str, Any] | None = None
    cleanup_error: Exception | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="library-media-", dir=work_dir) as temp_dir:
            media_path = Path(temp_dir) / "source.mp4"
            with httpx.Client(base_url=base_url, timeout=httpx.Timeout(300.0)) as client:
                _require_success(client.get("/api/health"), "health")
                provider = _json_success(client.get("/api/provider-settings"), "provider settings")
                if not provider.get("has_openai_api_key"):
                    raise RuntimeError("Configured real LLM API key is required.")
                _probe_provider(
                    client,
                    {
                        "llm_provider": provider["llm_provider"],
                        "openai_base_url": provider["openai_base_url"],
                        "openai_model": provider["openai_model"],
                        "openai_api_key": None,
                        "hf_endpoint": provider["hf_endpoint"],
                    },
                )
                library = _json_success(client.get("/api/videos"), "library")
                source_series, source_video = _select_source_video(
                    library,
                    source_series_id=source_series_id,
                    source_video_id=source_video_id,
                )
                _copy_preview_to_file(client, source_series["id"], source_video["id"], media_path)

                imported = _json_success(
                    client.post(
                        "/api/import/local/series/from-paths",
                        json={
                            "series_title": f"E2E Real LLM {datetime.now().strftime('%Y%m%d-%H%M%S')}",
                            "source_paths": [str(media_path.resolve())],
                            "storage_mode": "copy",
                        },
                    ),
                    "import existing library media",
                )
                series_id = str(imported["id"])
                video = imported["videos"][0]
                video_id = str(video["id"])

                series_generation = _json_success(
                    client.post(f"/api/series/{series_id}/generate", json={"processing_mode": "summary"}),
                    "real series generation",
                )
                if video_id not in series_generation.get("completed_videos", []):
                    raise RuntimeError(f"Series generation did not complete the test video: {series_generation}")

                summary = _json_success(client.get(f"/api/videos/{series_id}/{video_id}/summary"), "real summary read")
                ai_summary = _json_success(
                    client.post(f"/api/videos/{series_id}/{video_id}/ai-summary/generate", json={"template": "tutorial"}),
                    "real AI summary",
                )
                cards = _json_success(
                    client.post(f"/api/videos/{series_id}/{video_id}/knowledge-cards/generate"),
                    "real knowledge cards",
                )
                mindmap = _json_success(
                    client.post(f"/api/videos/{series_id}/{video_id}/mindmap/generate", json={"max_depth": 3}),
                    "real mindmap",
                )
                tools = _json_success(client.get(f"/api/videos/{series_id}/{video_id}/tools"), "tool status")
                transcript = _json_success(client.get(f"/api/videos/{series_id}/{video_id}/transcript"), "transcript read")
                preview = client.get(
                    f"/api/videos/{series_id}/{video_id}/preview",
                    headers={"Range": "bytes=0-0"},
                )
                _require_success(preview, "test video preview")
                exported = _require_success(
                    client.get(f"/api/videos/{series_id}/{video_id}/exports/summary.md"),
                    "summary export",
                ).text
                chat = _json_success(
                    client.post(
                        "/api/agent/chat",
                        json={
                            "session_id": f"video|{series_id}|{video_id}::real-llm-e2e",
                            "message": "What can be confirmed from this video's transcript and summary?",
                            "context": {
                                "scope_type": "video",
                                "series_id": series_id,
                                "series_title": imported["title"],
                                "video_id": video_id,
                                "video_title": video["title"],
                            },
                        },
                    ),
                    "real Agent chat",
                )
                _assert_artifacts(summary, ai_summary, cards, mindmap, tools, transcript, preview, exported, chat)
                result = {
                    "source_series_id": source_series["id"],
                    "source_video_id": source_video["id"],
                    "test_series_id": series_id,
                    "test_video_id": video_id,
                    "provider": provider["llm_provider"],
                    "model": provider["openai_model"],
                    "series_completed_videos": series_generation["completed_videos"],
                    "summary_chapter_count": len(summary["chapters"]),
                    "ai_summary_citation_count": len(ai_summary["citations"]),
                    "knowledge_card_count": len(cards["cards"]),
                    "mindmap_root": mindmap["title"],
                    "agent_citation_count": len(chat["citations"]),
                }
    finally:
        if series_id is not None:
            try:
                with httpx.Client(base_url=base_url, timeout=httpx.Timeout(90.0)) as cleanup_client:
                    _require_success(cleanup_client.delete(f"/api/series/{series_id}"), "delete E2E series")
                    library = _json_success(cleanup_client.get("/api/videos"), "verify E2E cleanup")
                    if any(item.get("id") == series_id for item in library.get("series", [])):
                        raise RuntimeError(f"E2E series still exists after deletion: {series_id}")
            except Exception as error:
                cleanup_error = error

    if cleanup_error is not None:
        raise RuntimeError(f"Real LLM E2E cleanup failed: {cleanup_error}") from cleanup_error
    if result is None:
        raise RuntimeError("Real LLM E2E did not produce a result.")
    return {**result, "cleanup": "deleted"}


def _select_source_video(
    library: dict[str, Any],
    *,
    source_series_id: str | None,
    source_video_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    for series in library.get("series", []):
        if source_series_id is not None and series.get("id") != source_series_id:
            continue
        for video in series.get("videos", []):
            if source_video_id is not None and video.get("id") != source_video_id:
                continue
            if video.get("is_linked") is not True:
                return series, video
    raise RuntimeError("No locally available source video matched the requested E2E input.")


def _copy_preview_to_file(client: httpx.Client, series_id: str, video_id: str, target: Path) -> None:
    with client.stream("GET", f"/api/videos/{series_id}/{video_id}/preview") as response:
        _require_success(response, "source video preview")
        with target.open("wb") as output:
            for chunk in response.iter_bytes():
                output.write(chunk)
    if target.stat().st_size == 0:
        raise RuntimeError("Source video preview was empty.")


def _probe_provider(client: httpx.Client, payload: dict[str, object], attempts: int = 3) -> None:
    for attempt in range(1, attempts + 1):
        response = client.post("/api/provider-settings/test", json=payload)
        if response.is_success:
            return
        if response.status_code not in {502, 503, 504} or attempt == attempts:
            _require_success(response, "real provider probe")
        time.sleep(attempt * 2)


def _assert_artifacts(summary, ai_summary, cards, mindmap, tools, transcript, preview, exported, chat) -> None:
    if not summary.get("chapters") or not ai_summary.get("content") or not ai_summary.get("citations"):
        raise RuntimeError("Real LLM summary artifacts are incomplete.")
    if not cards.get("cards") or not mindmap.get("title") or not mindmap.get("children"):
        raise RuntimeError("Real LLM cards or mindmap are incomplete.")
    if not transcript.get("segments") or not exported.strip() or not chat.get("assistant_message") or not chat.get("citations"):
        raise RuntimeError("Transcript, export, or real Agent answer is incomplete.")
    if preview.status_code not in {200, 206} or not preview.headers.get("content-type", "").startswith("video/"):
        raise RuntimeError("Test video preview is not a usable video response.")
    for name in ("overview", "ai_summary", "knowledge_cards", "mindmap"):
        if not tools.get(name, {}).get("generated"):
            raise RuntimeError(f"Tool state is not ready: {name}")


def _json_success(response: httpx.Response, action: str) -> dict[str, Any]:
    _require_success(response, action)
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{action} returned a non-object JSON payload.")
    return payload


def _require_success(response: httpx.Response, action: str) -> httpx.Response:
    if response.is_success:
        return response
    raise RuntimeError(f"{action} failed with HTTP {response.status_code}: {response.text}")


if __name__ == "__main__":
    main()
