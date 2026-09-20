"""Audit every locally available library video through its user-facing HTTP endpoints.

This check is intentionally read-only. It verifies that every non-linked video visible in
the library can load its media, workspace tools and notes; processed videos must also
load each artifact the tool state exposes. It never imports, generates, updates or deletes
user content.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "temp" / "library-media-e2e.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--max-videos", type=int, default=0, help="0 checks every local video.")
    args = parser.parse_args()
    result = run(args.base_url.rstrip("/"), max_videos=args.max_videos)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["failures"]:
        raise SystemExit(1)


def run(base_url: str, *, max_videos: int = 0) -> dict[str, Any]:
    if max_videos < 0:
        raise ValueError("max_videos cannot be negative.")

    with httpx.Client(base_url=base_url, timeout=httpx.Timeout(90.0)) as client:
        _require_success(client.get("/api/health"), "health")
        library = _require_success(client.get("/api/videos"), "library").json()
        candidates = [
            (series, video)
            for series in library.get("series", [])
            for video in series.get("videos", [])
            if video.get("is_linked") is not True
        ]
        if max_videos:
            candidates = candidates[:max_videos]

        failures: list[dict[str, str]] = []
        checked: list[dict[str, object]] = []
        for series, video in candidates:
            series_id = str(series["id"])
            video_id = str(video["id"])
            label = f"{series_id}/{video_id}"
            endpoints: list[str] = []
            try:
                tools = _json_success(client.get(f"/api/videos/{series_id}/{video_id}/tools"), f"{label} tools")
                endpoints.append("tools")
                _json_success(client.get(f"/api/videos/{series_id}/{video_id}/notes"), f"{label} notes")
                endpoints.append("notes")
                preview = client.get(
                    f"/api/videos/{series_id}/{video_id}/preview",
                    headers={"Range": "bytes=0-0"},
                )
                if preview.status_code not in {200, 206}:
                    raise RuntimeError(f"{label} preview returned HTTP {preview.status_code}: {preview.text}")
                if not preview.headers.get("content-type", "").startswith(("video/", "audio/", "application/octet-stream")):
                    raise RuntimeError(f"{label} preview has unexpected media type: {preview.headers.get('content-type')}")
                endpoints.append("preview")

                if video.get("processed") is True:
                    _json_success(client.get(f"/api/videos/{series_id}/{video_id}/summary"), f"{label} summary")
                    _json_success(client.get(f"/api/videos/{series_id}/{video_id}/transcript"), f"{label} transcript")
                    _require_success(client.get(f"/api/videos/{series_id}/{video_id}/subtitles.vtt"), f"{label} subtitles")
                    endpoints.extend(("summary", "transcript", "subtitles"))

                artifact_endpoints = (
                    ("ai_summary", "ai-summary"),
                    ("knowledge_cards", "knowledge-cards"),
                    ("mindmap", "mindmap"),
                )
                for tool_key, endpoint in artifact_endpoints:
                    if tools.get(tool_key, {}).get("generated") is True:
                        _json_success(
                            client.get(f"/api/videos/{series_id}/{video_id}/{endpoint}"),
                            f"{label} {endpoint}",
                        )
                        endpoints.append(endpoint)
                checked.append({"series_id": series_id, "video_id": video_id, "endpoints": endpoints})
            except Exception as error:
                failures.append(
                    {
                        "series_id": series_id,
                        "video_id": video_id,
                        "title": str(video.get("title") or video_id),
                        "error": str(error),
                    }
                )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checked_video_count": len(checked) + len(failures),
        "passed_video_count": len(checked),
        "failures": failures,
        "checked": checked,
    }


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
