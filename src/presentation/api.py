from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_OUTPUT_DIR = ROOT / "sample" / "output"

app = FastAPI(title="video_include api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/videos")
def list_videos() -> dict[str, object]:
    videos = [
        {"id": directory.name, "title": directory.name}
        for directory in sorted(SAMPLE_OUTPUT_DIR.iterdir())
        if directory.is_dir() and (directory / "summary.json").exists()
    ]
    series_id = SAMPLE_OUTPUT_DIR.name
    series_title = SAMPLE_OUTPUT_DIR.name.replace("_", " ").replace("-", " ").title()
    workspace_id = ROOT.name
    workspace_title = ROOT.name.replace("_", " ").replace("-", " ").title()
    return {
        "workspace": {"id": workspace_id, "title": workspace_title},
        "series": [{"id": series_id, "title": series_title, "videos": videos}],
        "videos": videos,
    }


@app.get("/api/videos/{video_id}/summary")
def get_video_summary(video_id: str) -> dict[str, object]:
    summary_path = SAMPLE_OUTPUT_DIR / video_id / "summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail=f"summary not found for video '{video_id}'")

    return json.loads(summary_path.read_text(encoding="utf-8"))
