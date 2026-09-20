"""受管 MySQL + SQL 制品发布的本机端到端冒烟测试。

运行示例：
  E:\\conda-envs\\vsummary\\python.exe tools\\mysql_e2e_smoke.py \
    --mysql-home "C:\\Program Files\\MySQL\\MySQL Server 8.4"

该脚本不读取或改写用户的 %LOCALAPPDATA%\\VSummary。它在临时目录启动完整的
受管 MySQL，导入合成媒体，并通过生产 SQL 发布适配器写入概括、知识卡和导图。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
import wave
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.video_summary.infrastructure.persistence.blob_store import FileBlobStore
from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.database import create_session_factory
from backend.video_summary.infrastructure.persistence.managed_local_mysql import ManagedLocalMySql
from backend.video_summary.infrastructure.persistence.sql_generation_adapters import (
    SqlBackedVideoMindmapGenerator,
    SqlBackedVideoSummaryGenerator,
)
from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace
from backend.api.di.bootstrap import build_api_container
from backend.api.http.app import create_app
from backend.agent.schemas.action_plan import AgentActionPlan, AgentTurnResult, ScopeType
from backend.video_summary.library.models import AiSummaryVisualEvidenceDTO
from backend.video_summary.library.models import KnowledgeCardDTO


class FixtureSummaryWorkflow:
    """确定性生成器，模拟 ASR/LLM 的临时制品输出，不依赖外部模型。"""

    async def run(self, _source_path: Path, output_dir: Path, **_kwargs: object) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            output_dir / "transcript.cleaned.json",
            {
                "language": "zh",
                "duration_seconds": 1.0,
                "segments": [{"start_seconds": 0.0, "end_seconds": 1.0, "text": "这是一段用于 SQL 端到端验证的合成音频。"}],
            },
        )
        _write_json(
            output_dir / "summary.json",
            {
                "title": "SQL E2E 概括",
                "one_sentence_summary": "验证导入、概括、卡片、导图和 RAG 均由 MySQL 承担。",
                "core_problem": "验证受管 MySQL 替代本地 JSON 制品存储后，用户流程仍可完整运行。",
                "chapters": [
                    {
                        "id": "fixture-chapter-1",
                        "title": "验证",
                        "start_seconds": 0.0,
                        "end_seconds": 1.0,
                        "summary": "合成媒体已被导入并概括。",
                        "key_points": ["媒体已进入 BlobStore", "结构化内容已发布到 MySQL"],
                    }
                ],
                "key_takeaways": ["SQL 是当前内容与 RAG 的权威来源。"],
            },
        )
        (output_dir / "summary.md").write_text("# SQL E2E 概括\n\n合成媒体已被导入并概括。\n", encoding="utf-8")


class FixtureMindmapWorkflow:
    """确定性导图工作流，覆盖临时 JSON 到 SQL 的发布路径。"""

    async def run(self, _source_path: Path, output_dir: Path, _summary: dict[str, object], **_kwargs: object) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            output_dir / "mindmap.json",
            {"name": "SQL E2E 概括", "children": [{"name": "导入媒体"}, {"name": "发布制品"}, {"name": "RAG"}]},
        )


class FixtureKnowledgeCardGenerator:
    """确定性知识卡生成器，覆盖 API 到 SQL 的完整发布路径。"""

    def run(self, *, title: str, **_kwargs: object) -> list[KnowledgeCardDTO]:
        return [
            KnowledgeCardDTO(
                id="fixture-card",
                title=f"{title}：SQL 是权威存储",
                kind="concept",
                summary="概括和衍生制品均已写入 SQL。",
                details="RAG 从当前 SQL 制品读取。",
                tags=["e2e"],
                keywords=["mysql", "rag"],
                related_card_ids=[],
            )
        ]


class FixtureRagModelManager:
    """使对话 API 进入实际 Agent 调用分支，而非模型下载提示分支。"""

    def has_active_download(self) -> bool:
        return False

    def is_downloaded(self, _key: str) -> bool:
        return True


class FixtureAgentGraph:
    """确定性 Agent，验证 SQL 制品已可进入对话 API。"""

    def run_turn(self, *, session_id: str, user_message: str, context_override) -> AgentTurnResult:
        if not context_override or not context_override.video_id:
            raise ValueError("E2E agent requires a video scope.")
        return AgentTurnResult(
            assistant_message=f"已读取视频制品：{user_message}",
            plan=AgentActionPlan(
                scope_type=ScopeType.VIDEO,
                reason="fixture_e2e",
                tool_calls=[],
                use_answerer=True,
            ),
            tool_results=[],
            citations=[],
        )


class FixtureIndexRefresher:
    """E2E 已直接校验 SQL RAG 文档，不在测试中下载 embedding 模型。"""

    def refresh(self, *_args: object, **_kwargs: object) -> None:
        return None

    def upsert_video(self, *_args: object, **_kwargs: object) -> None:
        return None


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\x00\x00" * 16_000)


async def run(mysql_home: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="vsummary-mysql-e2e-") as temp_dir:
        root = Path(temp_dir)
        runtime = ManagedLocalMySql(mysql_home=mysql_home, data_root=root / "data")
        try:
            options = runtime.start_and_migrate()
            sessions = create_session_factory(options)
            workspace = SqlVideoWorkspace(
                session_factory=sessions,
                blob_store=FileBlobStore(root / "data" / "blobs"),
                cache_root=root / "data" / "cache",
            )
            SqlControlPlaneRepository(sessions).create_workspace(
                owner_scope_id="mysql-e2e",
                title="SQL E2E 工作区",
            )
            media_path = root / "fixture.wav"
            _write_wav(media_path)
            summary_generator = SqlBackedVideoSummaryGenerator(
                workspace=workspace,
                workflow=FixtureSummaryWorkflow(),
                temp_root=workspace.cache_root,
            )
            mindmap_generator = SqlBackedVideoMindmapGenerator(
                workspace=workspace,
                workflow=FixtureMindmapWorkflow(),
                temp_root=workspace.cache_root,
            )
            container = build_api_container(
                REPOSITORY_ROOT,
                generator=summary_generator,
                mindmap_generator=mindmap_generator,
                knowledge_card_generator=FixtureKnowledgeCardGenerator(),
                workspace_override=workspace,
            )
            container = replace(
                container,
                rag_model_manager=FixtureRagModelManager(),
                get_agent_graph_service=lambda: FixtureAgentGraph(),
            )
            fixture_index_refresher = FixtureIndexRefresher()
            container.generate_video_summary._series_memory_refresher = fixture_index_refresher
            container.generate_video_cards._index_refresher = fixture_index_refresher
            with TestClient(create_app(container=container)) as client:
                worker_thread = container.job_worker._thread
                if worker_thread is None or not worker_thread.is_alive():
                    raise RuntimeError("Job worker did not start with the API lifespan.")
                _require_ok(client.get("/api/health"), "health")
                imported = _require_ok(
                    client.post(
                        "/api/import/local/series/from-paths",
                        json={
                            "series_title": "SQL E2E 系列",
                            "source_paths": [str(media_path)],
                            "storage_mode": "copy",
                        },
                    ),
                    "import local series",
                ).json()
                series_id = imported["id"]
                video_id = imported["videos"][0]["id"]

                request_headers = {"Idempotency-Key": "mysql-e2e-summary"}
                submitted = _require_ok(
                    client.post(f"/api/videos/{series_id}/{video_id}/generate", json={}, headers=request_headers),
                    "submit summary job",
                )
                if submitted.status_code != 202:
                    raise RuntimeError(f"Expected 202 when submitting summary job, got {submitted.status_code}.")
                repeated = _require_ok(
                    client.post(f"/api/videos/{series_id}/{video_id}/generate", json={}, headers=request_headers),
                    "repeat idempotent summary job submission",
                )
                if repeated.status_code != 202 or repeated.json()["job_id"] != submitted.json()["job_id"]:
                    raise RuntimeError("Idempotent job submission did not return the original job.")
                job_id = submitted.json()["job_id"]
                job = _wait_for_job(client, job_id)
                if job["status"] != "succeeded":
                    raise RuntimeError(f"Summary job did not succeed: {job}")
                events = _require_ok(client.get(f"/api/jobs/{job_id}/events"), "read job events").text
                if '"stage": "claimed"' not in events or '"stage": "succeeded"' not in events:
                    raise RuntimeError(f"Job event stream is incomplete: {events}")
                workspace.save_video_ai_summary(series_id, video_id, title="SQL E2E 概括", content="为卡片和导图提供画面证据。")
                workspace.save_video_ai_summary_visual_evidence(
                    series_id,
                    video_id,
                    frames=[AiSummaryVisualEvidenceDTO(timestamp_seconds=0.0, text="合成媒体的验证画面。")],
                )
                summary = _require_ok(client.get(f"/api/videos/{series_id}/{video_id}/summary"), "read summary").json()
                chapter_segments = summary.get("chapters", [{}])[0].get("transcript_segments", [])
                if len(chapter_segments) != 1 or chapter_segments[0].get("text") != "这是一段用于 SQL 端到端验证的合成音频。":
                    raise RuntimeError(f"Summary did not restore expandable transcript segments: {summary}")
                cards = _require_ok(client.post(f"/api/videos/{series_id}/{video_id}/knowledge-cards/generate"), "generate knowledge cards").json()
                mindmap = _require_ok(
                    client.post(f"/api/videos/{series_id}/{video_id}/mindmap/generate", json={"max_depth": 3}),
                    "generate mindmap",
                ).json()
                tools = _require_ok(client.get(f"/api/videos/{series_id}/{video_id}/tools"), "read workspace tools").json()
                subtitle = _require_ok(client.get(f"/api/videos/{series_id}/{video_id}/subtitles.vtt"), "read subtitles")
                exported = _require_ok(client.get(f"/api/videos/{series_id}/{video_id}/exports/summary.md"), "export summary")
                chat = _require_ok(
                    client.post(
                        "/api/agent/chat",
                        json={
                            "session_id": "mysql-e2e-session",
                            "message": "这段视频验证了什么？",
                            "context": {
                                "scope_type": "video",
                                "series_id": series_id,
                                "series_title": imported["title"],
                                "video_id": video_id,
                                "video_title": imported["videos"][0]["title"],
                            },
                        },
                    ),
                    "agent chat",
                ).json()

            rag_documents = workspace.get_rag_documents(series_id, video_id)
            if not (
                summary.get("title") == "SQL E2E 概括"
                and len(cards.get("cards", [])) == 1
                and mindmap.get("name") == "SQL E2E 概括"
                and tools["overview"]["generated"]
                and tools["knowledge_cards"]["generated"]
                and tools["mindmap"]["generated"]
                and "WEBVTT" in subtitle.text
                and "SQL E2E 概括" in exported.text
                and chat.get("assistant_message", "").startswith("已读取视频制品")
                and rag_documents
            ):
                raise RuntimeError("The HTTP E2E did not produce readable SQL-backed artifacts.")
            return {
                "series_id": series_id,
                "video_id": video_id,
                "summary_title": summary["title"],
                "knowledge_card_count": len(cards["cards"]),
                "mindmap_root": mindmap["name"],
                "rag_document_count": len(rag_documents),
                "summary_job_id": job_id,
                "agent_chat": chat["assistant_message"],
            }
        finally:
            runtime.stop()


def _require_ok(response, action: str):
    if response.is_success:
        return response
    raise RuntimeError(f"E2E {action} failed with HTTP {response.status_code}: {response.text}")


def _wait_for_job(client, job_id: str, timeout_seconds: float = 20.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    payload = None
    while time.monotonic() < deadline:
        response = _require_ok(client.get(f"/api/jobs/{job_id}"), "read job")
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for job {job_id}: {payload}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mysql-home", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.mysql_home)), ensure_ascii=False))


if __name__ == "__main__":
    main()
