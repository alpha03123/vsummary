"""Run the CI-safe full workflow against a local OpenAI-compatible mock.

The application, its HTTP API, durable jobs, media storage, subtitle extraction,
and Agent graph are real.  Only its outgoing LLM provider is replaced.

Usage: python tools/mock_llm_e2e.py --mysql-home <MySQL installation>
Configuration and data live in a fresh test directory; the installation's
.env and config/settings.toml are never modified.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from tools.e2e_support.api_client import LocalApiClient
from tools.e2e_support.assertions import require_generated_tools
from tools.e2e_support.jobs import wait_for_job, wait_for_video_processed
from tools.e2e_support.resources import E2EResourceScope


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mysql-home", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, help="Dedicated test directory; existing configuration or database is rejected.")
    parser.add_argument("--model-cache", type=Path, help="Embedding cache to copy into the test runtime.")
    parser.add_argument("--report", type=Path, default=ROOT / "temp" / "mock-llm-e2e" / "latest.json")
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    runtime_root = args.runtime_root.resolve() if args.runtime_root else Path(tempfile.mkdtemp(prefix="run-", dir=args.report.parent))
    print(f"Mock E2E runtime: {runtime_root}", flush=True)
    try:
        result = run_isolated(args.mysql_home, runtime_root, args.model_cache)
    except Exception as error:
        args.report.write_text(json.dumps({
            "status": "failed", "runtime_root": str(runtime_root), "error": str(error),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    result["status"] = "passed"
    result["runtime_root"] = str(runtime_root)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_isolated(mysql_home: Path, runtime_root: Path, model_cache: Path | None = None) -> dict[str, Any]:
    from backend.local.http.server import configure_event_loop_policy, local_server
    from tools.mock_openai_provider import Handler

    configure_event_loop_policy()
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as provider:
        provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
        provider_thread.start()
        try:
            _prepare_runtime(runtime_root, provider.server_port, model_cache)
            media = runtime_root / "fixture.mp4"
            with (runtime_root / "media.log").open("w", encoding="utf-8") as log:
                subprocess.run([
                    "pwsh", "-NoLogo", "-NoProfile", "-File", str(ROOT / "tools/create_mock_llm_e2e_media.ps1"),
                    "-OutputPath", str(media),
                ], check=True, stdout=log, stderr=subprocess.STDOUT)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
                print("Starting the Local backend with an isolated database", flush=True)
                with local_server(mysql_home=mysql_home, runtime_root=runtime_root, port=port) as server:
                    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
                    thread.start()
                    try:
                        base_url = f"http://127.0.0.1:{port}"
                        _wait_for_backend(base_url, thread)
                        return run(base_url, media)
                    finally:
                        server.should_exit = True
                        thread.join(timeout=30)
                        if thread.is_alive():
                            raise RuntimeError("Local E2E backend did not shut down within 30 seconds.")
        finally:
            provider.shutdown()
            provider_thread.join(timeout=10)


def _prepare_runtime(runtime_root: Path, provider_port: int, model_cache: Path | None) -> None:
    from backend.video_summary.infrastructure.config.settings import load_settings, save_settings
    from tools.mock_openai_provider import EXPECTED_API_KEY, EXPECTED_MODEL

    if any((runtime_root / path).exists() for path in (".env", "config", "data/local")):
        raise FileExistsError(f"Mock E2E requires a fresh runtime configuration and database: {runtime_root}")
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / ".env").write_text(
        f"OPENAI_API_KEY={EXPECTED_API_KEY}\nOPENAI_PROVIDER=openai_compatible\n"
        f"OPENAI_BASE_URL=http://127.0.0.1:{provider_port}\nOPENAI_MODEL={EXPECTED_MODEL}\n",
        encoding="utf-8",
    )
    config = runtime_root / "config/settings.toml"
    shutil.copyfile(ROOT / "config/settings.toml.example", config)
    settings = load_settings(config, runtime_root)
    settings = replace(
        settings,
        asr=replace(settings.asr, faster_whisper=replace(settings.asr.faster_whisper, device="cpu")),
        agent_retrieval=replace(settings.agent_retrieval, embedding_device="cpu"),
        generation=replace(settings.generation, chapter_visual_mode="off", note_visual_mode="off"),
    )
    save_settings(config, settings)
    cache = model_cache if model_cache is not None else ROOT / "data/models/fastembed"
    target = runtime_root / "data/models/fastembed"
    if model_cache is not None and not cache.is_dir():
        raise FileNotFoundError(f"Embedding cache does not exist: {cache}")
    if cache.is_dir() and not target.exists():
        shutil.copytree(cache, target)


def _wait_for_backend(base_url: str, thread: threading.Thread) -> None:
    import httpx

    health_url = httpx.URL(base_url).join("/api/health")
    assert health_url.host == "127.0.0.1" and health_url.path == "/api/health"
    deadline = time.monotonic() + 180
    with httpx.Client(timeout=2) as client:
        while time.monotonic() < deadline:
            if not thread.is_alive():
                raise RuntimeError("Local backend exited before becoming healthy.")
            try:
                response = client.get(health_url)
                if response.status_code == 200 and isinstance(response.json(), dict):
                    return
            except httpx.ConnectError:
                pass
            time.sleep(0.5)
    raise TimeoutError("Local backend did not become healthy within 180 seconds.")


def run(base_url: str, source_path: Path) -> dict[str, Any]:
    source_path = source_path.resolve()
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise ValueError(f"CI E2E source media is missing or empty: {source_path}")
    client = LocalApiClient(base_url)
    try:
        client.health()
        provider = client.provider_settings()
        if not provider.get("has_openai_api_key"):
            raise RuntimeError("CI E2E requires the non-secret mock provider key to be configured.")
        client.probe_provider(provider)
        rag_job = client.submit_rag_model_download("embedding")
        wait_for_job(client, str(rag_job["job_id"]), action="CI RAG embedding preparation", timeout_seconds=600)
        with E2EResourceScope(client) as resources:
            imported = client.import_local_series(title="CI Mock LLM E2E", source_paths=[source_path])
            series_id = str(imported["id"])
            video = imported["videos"][0]
            video_id = str(video["id"])
            resources.track_series(series_id, video_id)

            generation_job = resources.track_job(client.submit_series_generation(series_id))
            wait_for_job(client, generation_job, action="CI summary generation")
            wait_for_video_processed(client, series_id, video_id)

            summary = client.get_summary(series_id, video_id)
            transcript = client.get_transcript(series_id, video_id)
            subtitles = client.get_subtitles(series_id, video_id)
            preview = client.get_preview(series_id, video_id, byte_range="bytes=0-0")
            exported = client.get_export(series_id, video_id, "summary.md")

            ai_summary_job = resources.track_job(client.submit_ai_summary(series_id, video_id, template="tutorial"))
            wait_for_job(client, ai_summary_job, action="CI AI summary")
            ai_summary = client.get_ai_summary(series_id, video_id)

            cards_job = resources.track_job(client.submit_knowledge_cards(series_id, video_id))
            wait_for_job(client, cards_job, action="CI knowledge cards")
            cards = client.get_knowledge_cards(series_id, video_id)

            mindmap_job = resources.track_job(client.submit_mindmap(series_id, video_id, max_depth=3))
            wait_for_job(client, mindmap_job, action="CI mindmap")
            mindmap = client.get_mindmap(series_id, video_id)

            video_chat = client.chat(_chat_payload("video", series_id, imported["title"], video_id, video["title"]))
            series_chat = client.chat(_chat_payload("series", series_id, imported["title"]))
            tools = client.get_tools(series_id, video_id)
            _assert_workflow(
                summary=summary,
                transcript=transcript,
                subtitles_content_type=subtitles.headers.get("content-type", ""),
                preview_content_type=preview.headers.get("content-type", ""),
                exported=exported,
                ai_summary=ai_summary,
                cards=cards,
                mindmap=mindmap,
                tools=tools,
                video_chat=video_chat,
                series_chat=series_chat,
                series_id=series_id,
                video_id=video_id,
            )
            return {
                "provider": provider["llm_provider"],
                "model": provider["openai_model"],
                "test_series_id": series_id,
                "test_video_id": video_id,
                "generation_job_id": generation_job,
                "rag_embedding_job_id": rag_job["job_id"],
                "ai_summary_job_id": ai_summary_job,
                "knowledge_cards_job_id": cards_job,
                "mindmap_job_id": mindmap_job,
                "summary_chapter_count": len(summary["chapters"]),
                "knowledge_card_count": len(cards["cards"]),
                "video_talk_citation_count": len(video_chat["citations"]),
                "series_talk_citation_count": len(series_chat["citations"]),
                "cleanup": "deleted",
            }
    finally:
        client.close()


def _chat_payload(scope_type: str, series_id: str, series_title: str, video_id: str | None = None, video_title: str | None = None) -> dict[str, object]:
    context: dict[str, object] = {"scope_type": scope_type, "series_id": series_id, "series_title": series_title}
    if video_id is not None:
        context.update({"video_id": video_id, "video_title": video_title})
    return {
        "session_id": f"{scope_type}|{series_id}|{video_id or 'all'}::mock-llm-e2e",
        "message": "What can be confirmed from the generated transcript and summary?",
        "context": context,
    }


def _assert_workflow(*, summary: dict[str, Any], transcript: dict[str, Any], subtitles_content_type: str, preview_content_type: str, exported: str, ai_summary: dict[str, Any], cards: dict[str, Any], mindmap: dict[str, Any], tools: dict[str, Any], video_chat: dict[str, Any], series_chat: dict[str, Any], series_id: str, video_id: str) -> None:
    if not summary.get("chapters") or not transcript.get("segments") or not exported.strip():
        raise RuntimeError("Summary, transcript, or export artifact is incomplete.")
    if "text/vtt" not in subtitles_content_type or not preview_content_type.startswith("video/"):
        raise RuntimeError("Subtitle or media preview endpoint did not return a usable response.")
    if not ai_summary.get("content") or not ai_summary.get("citations"):
        raise RuntimeError("AI summary artifact is incomplete.")
    if not cards.get("cards") or not mindmap.get("title") or not mindmap.get("children"):
        raise RuntimeError("Knowledge cards or mindmap artifact is incomplete.")
    require_generated_tools(tools, "overview", "ai_summary", "knowledge_cards", "mindmap")
    _assert_talk_scope(video_chat, expected_series_id=series_id, expected_video_id=video_id, label="video")
    _assert_talk_scope(series_chat, expected_series_id=series_id, expected_video_id=video_id, label="series")


def _assert_talk_scope(chat: dict[str, Any], *, expected_series_id: str, expected_video_id: str, label: str) -> None:
    if not chat.get("assistant_message") or not chat.get("citations"):
        raise RuntimeError(f"{label} Talk did not return an answer with citations.")
    citations = chat["citations"]
    if not isinstance(citations, list):
        raise RuntimeError(f"{label} Talk citations are not a list.")
    for citation in citations:
        slots = citation.get("slots")
        if not isinstance(slots, list) or not slots:
            raise RuntimeError(f"{label} Talk returned a citation without source slots.")
        for slot in slots:
            # Citation slots identify local media by video ID.  The CI workspace has
            # only this temporary series, so this also proves series-scope isolation.
            if slot.get("video_id") != expected_video_id:
                raise RuntimeError(f"{label} Talk cited content outside the temporary series/video.")


if __name__ == "__main__":
    main()
