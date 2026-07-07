from __future__ import annotations

import asyncio
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO, VideoLibraryDTO, WorkspaceDTO


class AgentSeriesApiTests(unittest.TestCase):
    def test_create_agent_series_creates_empty_linked_series_with_agent_id(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/agent/series", json={"title": "  Deep Learning 101  "})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], "agent-deep-learning-101")
        self.assertEqual(payload["title"], "Deep Learning 101")
        self.assertEqual(payload["videos"], [])
        self.assertTrue(payload["is_linked"])
        self.assertEqual(container.workspace.get_linked_series("agent-deep-learning-101").videos, [])
        self.assertEqual(container.invalidator.invalidate_count, 1)

    def test_create_agent_series_rejects_blank_titles(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/agent/series", json={"title": "   "})

        self.assertEqual(response.status_code, 422)

    def test_create_agent_series_reuses_existing_same_title_without_clearing_videos(self) -> None:
        container = _build_container()
        existing_video = LinkedVideo(
            bvid="BVexisting",
            page=1,
            title="Existing Video",
            cover_url="",
            duration_seconds=0,
            source_url="https://www.bilibili.com/video/BVexisting",
        )
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-deep-learning-101",
                title="Deep Learning 101",
                cover_url="",
                source_url="agent://agent",
                videos=[existing_video],
            )
        )
        client = TestClient(create_app(container))

        response = client.post("/api/agent/series", json={"title": "Deep Learning 101"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "agent-deep-learning-101")
        self.assertEqual([item["id"] for item in response.json()["videos"]], ["BVexisting"])
        saved = container.workspace.get_linked_series("agent-deep-learning-101")
        self.assertEqual([item.video_id for item in saved.videos], ["BVexisting"])

    def test_create_agent_series_slug_collision_uses_unique_id_without_overwriting_existing_series(self) -> None:
        container = _build_container()
        existing_video = LinkedVideo(
            bvid="BVexisting",
            page=1,
            title="Existing Video",
            cover_url="",
            duration_seconds=0,
            source_url="https://www.bilibili.com/video/BVexisting",
        )
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-series",
                title="Existing Series",
                cover_url="",
                source_url="agent://agent",
                videos=[existing_video],
            )
        )
        client = TestClient(create_app(container))

        response = client.post("/api/agent/series", json={"title": "中文标题"})

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()["id"], "agent-series")
        self.assertEqual(response.json()["title"], "中文标题")
        original = container.workspace.get_linked_series("agent-series")
        self.assertEqual(original.title, "Existing Series")
        self.assertEqual([item.video_id for item in original.videos], ["BVexisting"])

    def test_create_agent_series_rejects_overlong_title(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/agent/series", json={"title": "x" * 201})

        self.assertEqual(response.status_code, 422)

    def test_add_agent_series_videos_resolves_unique_bilibili_urls_and_appends_in_order(self) -> None:
        container = _build_container()
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-course",
                title="Course",
                cover_url="",
                source_url="agent://agent",
                videos=[],
            )
        )
        client = TestClient(create_app(container))

        response = client.post(
            "/api/agent/series/agent-course/videos",
            json={
                "videos": [
                    {"url": "https://www.bilibili.com/video/BVfirst"},
                    {"url": "https://www.bilibili.com/video/BVfirst"},
                    {"url": "https://www.bilibili.com/video/BVsecond"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload], ["BVfirst", "BVsecond"])
        saved = container.workspace.get_linked_series("agent-course")
        self.assertEqual([item.video_id for item in saved.videos], ["BVfirst", "BVsecond"])
        self.assertEqual(container.resolver.resolved_urls, [
            "https://www.bilibili.com/video/BVfirst",
            "https://www.bilibili.com/video/BVsecond",
        ])
        self.assertEqual(container.invalidator.invalidate_count, 1)

    def test_add_agent_series_videos_rejects_empty_batches(self) -> None:
        container = _build_container()
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-course",
                title="Course",
                cover_url="",
                source_url="agent://agent",
                videos=[],
            )
        )
        client = TestClient(create_app(container))

        response = client.post("/api/agent/series/agent-course/videos", json={"videos": []})

        self.assertEqual(response.status_code, 422)

    def test_add_agent_series_videos_appends_only_one_video_when_different_urls_resolve_to_same_id(self) -> None:
        container = _build_container()
        container.resolver.aliases = {
            "https://www.bilibili.com/video/BVsame-a": "BVsame",
            "https://www.bilibili.com/video/BVsame-b": "BVsame",
        }
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-course",
                title="Course",
                cover_url="",
                source_url="agent://agent",
                videos=[],
            )
        )
        client = TestClient(create_app(container))

        response = client.post(
            "/api/agent/series/agent-course/videos",
            json={
                "videos": [
                    {"url": "https://www.bilibili.com/video/BVsame-a"},
                    {"url": "https://www.bilibili.com/video/BVsame-b"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        saved = container.workspace.get_linked_series("agent-course")
        self.assertEqual([item.video_id for item in saved.videos], ["BVsame"])

    def test_add_agent_series_videos_preserves_non_blank_agent_title(self) -> None:
        container = _build_container()
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-course",
                title="Course",
                cover_url="",
                source_url="agent://agent",
                videos=[],
            )
        )
        client = TestClient(create_app(container))

        response = client.post(
            "/api/agent/series/agent-course/videos",
            json={"videos": [{"url": "https://www.bilibili.com/video/BVfirst", "title": "  Agent Picked Title  "}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["title"], "Agent Picked Title")
        saved = container.workspace.get_linked_series("agent-course")
        self.assertEqual(saved.videos[0].title, "Agent Picked Title")
        self.assertEqual(saved.videos[0].bvid, "BVfirst")

    def test_add_agent_series_videos_rejects_invalid_url_scheme(self) -> None:
        container = _build_container()
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-course",
                title="Course",
                cover_url="",
                source_url="agent://agent",
                videos=[],
            )
        )
        client = TestClient(create_app(container))

        response = client.post(
            "/api/agent/series/agent-course/videos",
            json={"videos": [{"url": "ftp://www.bilibili.com/video/BVfirst"}]},
        )

        self.assertEqual(response.status_code, 422)

    def test_add_agent_series_videos_rejects_non_bilibili_http_url(self) -> None:
        container = _build_container()
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-course",
                title="Course",
                cover_url="",
                source_url="agent://agent",
                videos=[],
            )
        )
        client = TestClient(create_app(container))

        response = client.post(
            "/api/agent/series/agent-course/videos",
            json={"videos": [{"url": "https://example.com/video/BVfirst"}]},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(container.resolver.resolved_urls, [])

    def test_add_agent_series_videos_rejects_overlong_url(self) -> None:
        container = _build_container()
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-course",
                title="Course",
                cover_url="",
                source_url="agent://agent",
                videos=[],
            )
        )
        client = TestClient(create_app(container))

        response = client.post(
            "/api/agent/series/agent-course/videos",
            json={"videos": [{"url": f"https://www.bilibili.com/video/{'x' * 2050}"}]},
        )

        self.assertEqual(response.status_code, 422)

    def test_add_agent_series_videos_rejects_unsupported_source(self) -> None:
        container = _build_container()
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-course",
                title="Course",
                cover_url="",
                source_url="agent://agent",
                videos=[],
            )
        )
        client = TestClient(create_app(container))

        response = client.post(
            "/api/agent/series/agent-course/videos",
            json={"videos": [{"url": "https://www.bilibili.com/video/BVfirst", "source": "youtube"}]},
        )

        self.assertEqual(response.status_code, 422)

    def test_add_agent_series_videos_returns_not_found_for_missing_series(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post(
            "/api/agent/series/missing-series/videos",
            json={"videos": [{"url": "https://www.bilibili.com/video/BVfirst"}]},
        )

        self.assertEqual(response.status_code, 404)

    def test_process_agent_series_schedules_generation_without_waiting_for_completion(self) -> None:
        container = _build_container()
        container.workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-course",
                title="Course",
                cover_url="",
                source_url="agent://agent",
                videos=[],
            )
        )
        client = TestClient(create_app(container))

        started_at = time.perf_counter()
        response = client.post("/api/agent/series/agent-course/process", json={"run_id": "run-1"})
        elapsed = time.perf_counter() - started_at

        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 0.2)
        self.assertEqual(
            {"series_id": "agent-course", "run_id": "run-1", "status": "scheduled"},
            response.json(),
        )

    def test_process_agent_series_returns_not_found_for_missing_series(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/agent/series/missing-series/process", json={"run_id": "run-1"})

        self.assertEqual(response.status_code, 404)

    def test_get_agent_series_status_returns_video_state_artifacts_and_failure_reason(self) -> None:
        with TemporaryDirectory() as root_dir:
            container = _build_container(root_dir=Path(root_dir))
            container.workspace.save_linked_series(
                LinkedSeries(
                    series_id="agent-course",
                    title="Course",
                    cover_url="",
                    source_url="agent://agent",
                    videos=[],
                )
            )
            container.workspace.video_overrides["agent-course"] = [
                SimpleNamespace(
                    id="BVdone",
                    title="Done",
                    processed=True,
                    status="ready",
                    is_linked=True,
                    source_url="https://www.bilibili.com/video/BVdone",
                    error="",
                ),
                SimpleNamespace(
                    id="BVfail",
                    title="Failed",
                    processed=False,
                    status="failed",
                    is_linked=True,
                    source_url="https://www.bilibili.com/video/BVfail",
                    detail="download failed",
                ),
            ]
            done_dir = Path(root_dir) / "workspace" / "agent-course" / "BVdone"
            done_dir.mkdir(parents=True)
            (done_dir / "summary.json").write_text("{}", encoding="utf-8")
            (done_dir / "transcript.cleaned.json").write_text("[]", encoding="utf-8")
            client = TestClient(create_app(container))

            response = client.get("/api/agent/series/agent-course/status")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                {
                    "id": "agent-course",
                    "title": "Course",
                    "videos": [
                        {
                            "id": "BVdone",
                            "title": "Done",
                            "status": "ready",
                            "processed": True,
                            "is_linked": True,
                            "source_url": "https://www.bilibili.com/video/BVdone",
                            "artifacts": {"summary": True, "transcript": True},
                            "failure_reason": "",
                        },
                        {
                            "id": "BVfail",
                            "title": "Failed",
                            "status": "failed",
                            "processed": False,
                            "is_linked": True,
                            "source_url": "https://www.bilibili.com/video/BVfail",
                            "artifacts": {"summary": False, "transcript": False},
                            "failure_reason": "download failed",
                        },
                    ],
                },
                response.json(),
            )

    def test_get_agent_series_status_returns_not_found_for_missing_series(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.get("/api/agent/series/missing-series/status")

        self.assertEqual(response.status_code, 404)


def _build_container(root_dir: Path | None = None):
    workspace = _FakeWorkspace()
    resolver = _FakeBilibiliResolver()
    invalidator = _FakeWorkspaceIndexInvalidator()
    create_agent_series, add_agent_series_videos = _build_agent_series_usecases(workspace, resolver, invalidator)
    return SimpleNamespace(
        root_dir=root_dir,
        workspace=workspace,
        resolver=resolver,
        invalidator=invalidator,
        list_video_library=_FakeListVideoLibrary(workspace),
        generate_series_summaries=_FakeGenerateSeriesSummaries(),
        create_agent_series=create_agent_series,
        add_agent_series_videos=add_agent_series_videos,
    )


def _build_agent_series_usecases(workspace, resolver, invalidator):
    try:
        from backend.video_summary.library.usecases.agent_series import AddAgentSeriesVideos, CreateAgentSeries
    except ModuleNotFoundError:
        return _MissingRouteFallbackUseCase(), _MissingRouteFallbackUseCase()
    return CreateAgentSeries(workspace, invalidator), AddAgentSeriesVideos(workspace, resolver, invalidator)


class _MissingRouteFallbackUseCase:
    async def run(self, **kwargs):
        del kwargs
        return LibrarySeriesDTO(id="unused", title="unused", videos=[], is_linked=True)


class _FakeWorkspace:
    def __init__(self) -> None:
        self.linked_series: dict[str, LinkedSeries] = {}
        self.video_overrides: dict[str, list[object]] = {}

    def save_linked_series(self, series: LinkedSeries) -> None:
        self.linked_series[series.series_id] = series

    def get_linked_series(self, series_id: str) -> LinkedSeries | None:
        return self.linked_series.get(series_id)

    def list_series(self) -> list[LibrarySeriesDTO]:
        return [
            LibrarySeriesDTO(
                id=series.series_id,
                title=series.title,
                videos=self._videos_for_series(series),
                is_linked=True,
                source_url=series.source_url,
            )
            for series in self.linked_series.values()
        ]

    def get_workspace(self) -> WorkspaceDTO:
        return WorkspaceDTO(id="workspace", title="Workspace")

    def _videos_for_series(self, series: LinkedSeries) -> list[object]:
        if series.series_id in self.video_overrides:
            return self.video_overrides[series.series_id]
        return [
            LibraryVideoCardDTO(
                id=video.video_id,
                title=video.title,
                source_name=f"{video.video_id}.mp4",
                processed=False,
                status="linked",
                is_linked=True,
                bilibili_bvid=video.bvid,
                bilibili_page=video.page,
                source_url=video.source_url,
                provider=video.provider,
            )
            for video in series.videos
        ]


class _FakeListVideoLibrary:
    def __init__(self, workspace: _FakeWorkspace) -> None:
        self.workspace = workspace

    def run(self) -> VideoLibraryDTO:
        return VideoLibraryDTO(workspace=self.workspace.get_workspace(), series=self.workspace.list_series())


class _FakeGenerateSeriesSummaries:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def run(self, series_id: str, *, transcript_enhancement_enabled=None, run_id: str | None = None):
        del transcript_enhancement_enabled
        self.calls.append((series_id, run_id))
        await asyncio.sleep(1)


class _FakeBilibiliResolver:
    def __init__(self) -> None:
        self.resolved_urls: list[str] = []
        self.aliases: dict[str, str] = {}

    async def resolve_single_video(self, url_info) -> LinkedVideo:
        url = url_info.url
        self.resolved_urls.append(url)
        bvid = self.aliases.get(url, url.rstrip("/").split("/")[-1])
        return LinkedVideo(
            bvid=bvid,
            page=1,
            title=f"Video {bvid}",
            cover_url="",
            duration_seconds=0,
            source_url=url,
        )


class _FakeWorkspaceIndexInvalidator:
    def __init__(self) -> None:
        self.invalidate_count = 0

    def invalidate(self) -> None:
        self.invalidate_count += 1



if __name__ == "__main__":
    unittest.main()
