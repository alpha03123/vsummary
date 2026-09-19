"""真实验证链接视频的下载、概括重跑和 Agent 对话。

目标视频必须已存在于系列中且状态为 ``linked``，但尚未下载。本脚本使用运行中
服务的真实下载器、ASR、LLM 和 RAG，不注入模拟实现。运行会消耗网络与模型额度。

示例：
  E:\\conda-envs\\vsummary\\python.exe tools\\linked_download_real_llm_e2e.py \
    --series-id <series-id> --video-id <video-id>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "temp" / "linked-download-real-llm-e2e.json")
    args = parser.parse_args()
    result = run(args.base_url.rstrip("/"), args.series_id, args.video_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run(base_url: str, series_id: str, video_id: str) -> dict[str, Any]:
    with httpx.Client(base_url=base_url, timeout=httpx.Timeout(300.0)) as client:
        _ok(client.get("/api/health"), "health")
        library = _ok(client.get("/api/videos"), "library").json()
        series, video = _find_video(library, series_id, video_id)
        if not video["is_linked"] or video["status"] != "linked":
            raise RuntimeError("E2E input must be an unresolved linked video; refusing to skip the download stage.")

        started = _ok(
            client.post(f"/api/videos/{series_id}/{video_id}/download"),
            "linked video download start",
        ).json()
        download = _wait_download(client, series_id, video_id)
        if download["status"] != "completed":
            raise RuntimeError(f"Linked video download did not complete: {download}")

        first_job = _ok(
            client.post(f"/api/videos/{series_id}/{video_id}/generate", json={"processing_mode": "summary"}),
            "first generated summary",
        ).json()
        _wait_job(client, first_job["job_id"])
        first_summary = _ok(client.get(f"/api/videos/{series_id}/{video_id}/summary"), "first generated summary read").json()
        regenerated_job = _ok(
            client.post(f"/api/videos/{series_id}/{video_id}/generate", json={"processing_mode": "summary"}),
            "regenerated summary",
        ).json()
        _wait_job(client, regenerated_job["job_id"])
        regenerated_summary = _ok(client.get(f"/api/videos/{series_id}/{video_id}/summary"), "regenerated summary read").json()
        preview = _ok(client.get(f"/api/videos/{series_id}/{video_id}/preview"), "downloaded preview")
        video_chat = _ok(
            client.post(
                "/api/agent/chat",
                json={
                    "session_id": f"video|{series_id}|{video_id}::linked-download-real-e2e",
                    "message": "What can be confirmed from the current video's generated transcript and summary?",
                    "context": {
                        "scope_type": "video",
                        "series_id": series_id,
                        "series_title": series["title"],
                        "video_id": video_id,
                        "video_title": video["title"],
                    },
                },
            ),
            "video scoped agent chat",
        ).json()
        series_chat = _ok(
            client.post(
                "/api/agent/chat",
                json={
                    "session_id": f"series|{series_id}::linked-download-real-e2e",
                    "message": "Which videos in this series have generated summaries, and what shared themes can be inferred?",
                    "context": {"scope_type": "series", "series_id": series_id, "series_title": series["title"]},
                },
            ),
            "series scoped agent chat",
        ).json()
        tools = _ok(client.get(f"/api/videos/{series_id}/{video_id}/tools"), "downloaded tool status").json()

    if not first_summary.get("chapters") or not regenerated_summary.get("chapters"):
        raise RuntimeError("First generation or regeneration produced no chapters.")
    if preview.headers.get("content-type", "").split(";", 1)[0] != "video/mp4":
        raise RuntimeError("Downloaded media preview is not an MP4 response.")
    if not video_chat.get("assistant_message") or not video_chat.get("citations"):
        raise RuntimeError("Video scoped chat did not return a cited answer.")
    if not series_chat.get("assistant_message") or not series_chat.get("citations"):
        raise RuntimeError("Series scoped chat did not return a cited answer.")
    if not tools["overview"]["generated"]:
        raise RuntimeError("Downloaded video was not marked as summarized.")
    return {
        "series_id": series_id,
        "video_id": video_id,
        "download_task_id": started["task_id"],
        "download_status": download["status"],
        "first_summary_chapter_count": len(first_summary["chapters"]),
        "regenerated_summary_chapter_count": len(regenerated_summary["chapters"]),
        "video_chat_citation_count": len(video_chat["citations"]),
        "series_chat_citation_count": len(series_chat["citations"]),
        "preview_content_type": preview.headers.get("content-type"),
        "tool_status": tools,
    }


def _wait_download(client: httpx.Client, series_id: str, video_id: str) -> dict[str, Any]:
    with client.stream("GET", f"/api/videos/{series_id}/{video_id}/download/progress") as response:
        _ok(response, "linked video download progress")
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            snapshot = json.loads(line[6:])
            if snapshot.get("status") in {"completed", "failed", "cancelled"}:
                return snapshot
    raise RuntimeError("Linked video download progress stream ended without a terminal state.")


def _wait_job(client: httpx.Client, job_id: str, timeout_seconds: float = 300.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job = _ok(client.get(f"/api/jobs/{job_id}"), "summary job status").json()
        if job["status"] == "succeeded":
            return job
        if job["status"] in {"failed", "cancelled"}:
            raise RuntimeError(f"Summary job did not succeed: {job}")
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for summary job {job_id}.")


def _find_video(library: dict[str, Any], series_id: str, video_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    series = next((item for item in library["series"] if item["id"] == series_id), None)
    if series is None:
        raise RuntimeError(f"Series does not exist: {series_id}")
    video = next((item for item in series["videos"] if item["id"] == video_id), None)
    if video is None:
        raise RuntimeError(f"Video does not exist: {series_id}/{video_id}")
    return series, video


def _ok(response: httpx.Response, action: str) -> httpx.Response:
    if response.is_success:
        return response
    raise RuntimeError(f"{action} failed with HTTP {response.status_code}: {response.text}")


if __name__ == "__main__":
    main()
