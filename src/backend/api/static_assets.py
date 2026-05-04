from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_frontend_dist(app: FastAPI, root_dir: Path) -> None:
    dist_dir = root_dir / "src" / "frontend" / "dist"
    index_path = dist_dir / "index.html"
    assets_dir = dist_dir / "assets"

    if not dist_dir.is_dir() or not index_path.is_file():
        return

    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(assets_dir)),
            name="frontend-assets",
        )

    @app.get("/", include_in_schema=False)
    def serve_frontend_index() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend_path(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = dist_dir / full_path
        try:
            candidate.relative_to(dist_dir)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="Not Found") from error

        if candidate.is_file():
            return FileResponse(candidate)

        return FileResponse(index_path)
