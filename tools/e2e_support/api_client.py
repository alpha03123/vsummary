"""Stable Core and Local HTTP contracts used by E2E scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


class CoreApiClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 300.0) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=httpx.Timeout(timeout_seconds))

    def close(self) -> None:
        self._client.close()

    def health(self) -> dict[str, Any]:
        return self._json("GET", "/api/health", "health")

    def library(self) -> dict[str, Any]:
        return self._json("GET", "/api/videos", "library")

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/jobs/{job_id}", "job status")

    def get_generation_status(self, series_id: str, video_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/videos/{series_id}/{video_id}/generate/status", "video generation status")

    def submit_series_generation(self, series_id: str, *, processing_mode: str = "summary") -> dict[str, Any]:
        return self._json("POST", f"/api/series/{series_id}/generate", "series generation", json={"processing_mode": processing_mode})

    def submit_video_generation(self, series_id: str, video_id: str, *, processing_mode: str = "summary") -> dict[str, Any]:
        return self._json("POST", f"/api/videos/{series_id}/{video_id}/generate", "video generation", json={"processing_mode": processing_mode})

    def start_linked_download(self, series_id: str, video_id: str) -> dict[str, Any]:
        return self._json("POST", f"/api/videos/{series_id}/{video_id}/download", "linked video download")

    def submit_ai_summary(self, series_id: str, video_id: str, *, template: str) -> dict[str, Any]:
        return self._json("POST", f"/api/videos/{series_id}/{video_id}/ai-summary/generate", "AI summary generation", json={"template": template})

    def submit_knowledge_cards(self, series_id: str, video_id: str) -> dict[str, Any]:
        return self._json("POST", f"/api/videos/{series_id}/{video_id}/knowledge-cards/generate", "knowledge card generation")

    def submit_mindmap(self, series_id: str, video_id: str, *, max_depth: int) -> dict[str, Any]:
        return self._json("POST", f"/api/videos/{series_id}/{video_id}/mindmap/generate", "mindmap generation", json={"max_depth": max_depth})

    def get_summary(self, series_id: str, video_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/videos/{series_id}/{video_id}/summary", "summary")

    def get_ai_summary(self, series_id: str, video_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/videos/{series_id}/{video_id}/ai-summary", "AI summary")

    def get_knowledge_cards(self, series_id: str, video_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/videos/{series_id}/{video_id}/knowledge-cards", "knowledge cards")

    def get_mindmap(self, series_id: str, video_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/videos/{series_id}/{video_id}/mindmap", "mindmap")

    def get_tools(self, series_id: str, video_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/videos/{series_id}/{video_id}/tools", "workspace tools")

    def get_transcript(self, series_id: str, video_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/videos/{series_id}/{video_id}/transcript", "transcript")

    def get_notes(self, series_id: str, video_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/videos/{series_id}/{video_id}/notes", "notes")

    def get_export(self, series_id: str, video_id: str, name: str) -> str:
        return self._request("GET", f"/api/videos/{series_id}/{video_id}/exports/{name}", f"{name} export").text

    def get_subtitles(self, series_id: str, video_id: str) -> httpx.Response:
        return self._request("GET", f"/api/videos/{series_id}/{video_id}/subtitles.vtt", "subtitles")

    def get_preview(self, series_id: str, video_id: str, *, byte_range: str | None = None) -> httpx.Response:
        headers = {"Range": byte_range} if byte_range else None
        return self._request("GET", f"/api/videos/{series_id}/{video_id}/preview", "video preview", headers=headers)

    def copy_preview_to(self, series_id: str, video_id: str, target: Path) -> None:
        with self._client.stream("GET", f"/api/videos/{series_id}/{video_id}/preview") as response:
            if not response.is_success:
                response.read()
            _require_success(response, "source video preview")
            with target.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)
        if target.stat().st_size == 0:
            raise RuntimeError("Source video preview was empty.")

    def chat(self, payload: dict[str, object]) -> dict[str, Any]:
        return self._json("POST", "/api/agent/chat", "Agent chat", json=payload)

    def cancel_series_generation(self, series_id: str) -> int:
        return self._client.post(f"/api/series/{series_id}/generate/cancel").status_code

    def cancel_video_generation(self, series_id: str, video_id: str) -> int:
        return self._client.post(f"/api/videos/{series_id}/{video_id}/generate/cancel").status_code

    def delete_series(self, series_id: str) -> httpx.Response:
        return self._client.delete(f"/api/series/{series_id}")

    def _json(self, method: str, path: str, action: str, **kwargs: object) -> dict[str, Any]:
        payload = self._request(method, path, action, **kwargs).json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"{action} returned a non-object JSON payload.")
        return payload

    def _request(self, method: str, path: str, action: str, **kwargs: object) -> httpx.Response:
        response = self._client.request(method, path, **kwargs)
        return _require_success(response, action)


class LocalApiClient(CoreApiClient):
    def provider_settings(self) -> dict[str, Any]:
        return self._json("GET", "/api/provider-settings", "provider settings")

    def probe_provider(self, settings: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "llm_provider": settings["llm_provider"],
            "openai_base_url": settings["openai_base_url"],
            "openai_model": settings["openai_model"],
            "openai_api_key": None,
            "hf_endpoint": settings["hf_endpoint"],
        }
        return self._json("POST", "/api/provider-settings/test", "provider probe", json=payload)

    def import_local_series(self, *, title: str, source_paths: list[Path], storage_mode: str = "copy") -> dict[str, Any]:
        return self._json(
            "POST",
            "/api/import/local/series/from-paths",
            "local media import",
            json={"series_title": title, "source_paths": [str(path) for path in source_paths], "storage_mode": storage_mode},
        )


def _require_success(response: httpx.Response, action: str) -> httpx.Response:
    if response.is_success:
        return response
    raise RuntimeError(f"{action} failed with HTTP {response.status_code}: {response.text}")
