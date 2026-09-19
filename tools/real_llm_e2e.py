"""Run a persistent VSummary E2E against the configured real LLM provider.

Unlike ``mysql_e2e_smoke.py``, this script never injects fake generators or an
Agent substitute. It creates a new series in the running application, imports a
synthetic MP4, uploads a human-authored SRT, and calls the production HTTP API
for summary, AI summary, knowledge cards, mindmap, and video-scoped Agent chat.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORK_DIR = ROOT / "temp" / "real-llm-e2e"
SRT = """1
00:00:00,000 --> 00:00:03,000
This video verifies VSummary with a real LLM. Stage one stores transcripts, summaries, cards, and mindmaps in MySQL.

2
00:00:03,000 --> 00:00:06,000
Stage two reads current SQL artifacts through RAG so users can ask questions within the current video.

3
00:00:06,000 --> 00:00:09,000
Stage three requires a real LLM to generate the summary, AI note, cards, mindmap, and cited answer without mocked responses.
"""

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    args = parser.parse_args()
    print(json.dumps(run(args.base_url.rstrip("/"), args.work_dir, args.ffmpeg), ensure_ascii=False, indent=2))


def run(base_url: str, work_dir: Path, ffmpeg: str) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    media_path = work_dir / "real-llm-e2e.mp4"
    srt_path = work_dir / "real-llm-e2e.srt"
    _make_video(ffmpeg, media_path)
    srt_path.write_text(SRT, encoding="utf-8")

    with httpx.Client(base_url=base_url, timeout=httpx.Timeout(240.0)) as client:
        _ok(client.get("/api/health"), "health")
        provider = _ok(client.get("/api/provider-settings"), "provider settings").json()
        if not provider.get("has_openai_api_key"):
            raise RuntimeError("Configured real LLM API key is required.")
        _ok(
            client.post(
                "/api/provider-settings/test",
                json={
                    "llm_provider": provider["llm_provider"],
                    "openai_base_url": provider["openai_base_url"],
                    "openai_model": provider["openai_model"],
                    "openai_api_key": None,
                    "hf_endpoint": provider["hf_endpoint"],
                },
            ),
            "real provider probe",
        )
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        imported = _ok(
            client.post(
                "/api/import/local/series/from-paths",
                json={
                    "series_title": f"E2E Real LLM {stamp}",
                    "source_paths": [str(media_path.resolve())],
                    "storage_mode": "copy",
                },
            ),
            "media import",
        ).json()
        series_id, video = imported["id"], imported["videos"][0]
        video_id = video["id"]
        with srt_path.open("rb") as source:
            summary = _ok(
                client.post(
                    f"/api/videos/{series_id}/{video_id}/transcript/srt-and-generate",
                    files={"file": (srt_path.name, source, "application/x-subrip")},
                ),
                "real summary",
            ).json()
        ai_summary = _ok(
            client.post(f"/api/videos/{series_id}/{video_id}/ai-summary/generate", json={"template": "tutorial"}),
            "real AI summary",
        ).json()
        cards = _ok(
            client.post(f"/api/videos/{series_id}/{video_id}/knowledge-cards/generate"),
            "real knowledge cards",
        ).json()
        mindmap = _ok(
            client.post(f"/api/videos/{series_id}/{video_id}/mindmap/generate", json={"max_depth": 3}),
            "real mindmap",
        ).json()
        tools = _ok(client.get(f"/api/videos/{series_id}/{video_id}/tools"), "tool status").json()
        transcript = _ok(client.get(f"/api/videos/{series_id}/{video_id}/transcript"), "transcript read").json()
        exported = _ok(client.get(f"/api/videos/{series_id}/{video_id}/exports/summary.md"), "summary export").text
        chat = _ok(
            client.post(
                "/api/agent/chat",
                json={
                    "session_id": f"video|{series_id}|{video_id}::real-llm-e2e",
                    "message": "How does this video prove the real end-to-end pipeline, and what is the relationship between MySQL and RAG?",
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
        ).json()

    _assert_artifacts(summary, ai_summary, cards, mindmap, tools, transcript, exported, chat)
    result = {
        "series_id": series_id,
        "series_title": imported["title"],
        "video_id": video_id,
        "video_title": video["title"],
        "provider": provider["llm_provider"],
        "model": provider["openai_model"],
        "summary_chapter_count": len(summary["chapters"]),
        "ai_summary_citation_count": len(ai_summary["citations"]),
        "knowledge_card_count": len(cards["cards"]),
        "mindmap_root": mindmap["title"],
        "agent_answer": chat["assistant_message"],
        "artifact_endpoints": {
            "summary": f"/api/videos/{series_id}/{video_id}/summary",
            "transcript": f"/api/videos/{series_id}/{video_id}/transcript",
            "ai_summary": f"/api/videos/{series_id}/{video_id}/ai-summary",
            "cards": f"/api/videos/{series_id}/{video_id}/knowledge-cards",
            "mindmap": f"/api/videos/{series_id}/{video_id}/mindmap",
            "tools": f"/api/videos/{series_id}/{video_id}/tools",
            "summary_export": f"/api/videos/{series_id}/{video_id}/exports/summary.md",
        },
    }
    (work_dir / "real-llm-e2e-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _make_video(ffmpeg: str, target: Path) -> None:
    graph = (
        "[0:v]drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':text='STAGE 1 MYSQL SOURCE OF TRUTH':fontcolor=white:fontsize=52:x=(w-text_w)/2:y=(h-text_h)/2[a];"
        "[1:v]drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':text='STAGE 2 SQL RAG VIDEO CHAT':fontcolor=white:fontsize=52:x=(w-text_w)/2:y=(h-text_h)/2[b];"
        "[2:v]drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':text='STAGE 3 REAL LLM GENERATION':fontcolor=white:fontsize=52:x=(w-text_w)/2:y=(h-text_h)/2[c];"
        "[a][b][c]concat=n=3:v=1:a=0"
    )
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=navy:s=1280x720:r=24:d=3", "-f", "lavfi", "-i", "color=c=teal:s=1280x720:r=24:d=3", "-f", "lavfi", "-i", "color=c=maroon:s=1280x720:r=24:d=3", "-filter_complex", graph, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target)],
        check=True,
        capture_output=True,
        text=True,
    )


def _assert_artifacts(summary, ai_summary, cards, mindmap, tools, transcript, exported, chat) -> None:
    if not summary.get("chapters") or not ai_summary.get("content") or not ai_summary.get("citations"):
        raise RuntimeError("Real LLM summary artifacts are incomplete.")
    if not cards.get("cards") or not mindmap.get("title") or not mindmap.get("children"):
        raise RuntimeError("Real LLM cards or mindmap are incomplete.")
    if not transcript.get("segments") or not exported.strip() or not chat.get("assistant_message") or not chat.get("citations"):
        raise RuntimeError("Transcript, export, or real Agent answer is incomplete.")
    for name in ("overview", "ai_summary", "knowledge_cards", "mindmap"):
        if not tools.get(name, {}).get("generated"):
            raise RuntimeError(f"Tool state is not ready: {name}")


def _ok(response: httpx.Response, action: str) -> httpx.Response:
    if response.is_success:
        return response
    raise RuntimeError(f"{action} failed with HTTP {response.status_code}: {response.text}")


if __name__ == "__main__":
    main()
