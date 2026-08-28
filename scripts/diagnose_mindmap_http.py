"""Capture an end-to-end mindmap generation request and its runtime evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--timeout", type=float, default=120)
    return parser.parse_args()


async def read_lmstudio_events(process: asyncio.subprocess.Process, started: float, events: list[dict[str, Any]]) -> None:
    if process.stdout is None:
        return
    while line := await process.stdout.readline():
        text = line.decode("utf-8", errors="replace").strip()
        if not text or text == "Streaming logs from LM Studio":
            continue
        try:
            payload: Any = json.loads(text)
        except json.JSONDecodeError:
            payload = {"raw": text}
        events.append({"at_seconds": round(time.monotonic() - started, 3), "event": payload})


async def capture_progress(client: httpx.AsyncClient, url: str, started: float, events: list[dict[str, Any]]) -> None:
    async with client.stream("GET", url, timeout=None) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            events.append({"at_seconds": round(time.monotonic() - started, 3), "progress": payload})
            if payload.get("status") in {"completed", "failed", "cancelled", "idle"}:
                return


async def capture_lmstudio_state(started: float, snapshots: list[dict[str, Any]], stop: asyncio.Event) -> None:
    while not stop.is_set():
        result = await asyncio.to_thread(
            subprocess.run,
            ["lms", "ps"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        snapshots.append(
            {
                "at_seconds": round(time.monotonic() - started, 3),
                "exit_code": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        )
        try:
            await asyncio.wait_for(stop.wait(), timeout=1)
        except TimeoutError:
            pass


async def main() -> int:
    args = parse_args()
    started = time.monotonic()
    suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = ROOT_DIR / "temp" / f"mindmap-http-diagnose-{suffix}.json"
    route = f"{args.base_url.rstrip('/')}/api/videos/{args.series}/{args.video}/mindmap/generate"
    progress_url = f"{route}/progress"
    report: dict[str, Any] = {
        "route": route,
        "started_at": datetime.now().astimezone().isoformat(),
        "timeout_seconds": args.timeout,
        "http_response": None,
        "progress_events": [],
        "lmstudio_events": [],
        "lmstudio_state": [],
        "error": None,
    }
    log_process = await asyncio.create_subprocess_exec(
        "lms",
        "log",
        "stream",
        "--source",
        "model",
        "--stats",
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stop = asyncio.Event()
    event_task = asyncio.create_task(read_lmstudio_events(log_process, started, report["lmstudio_events"]))
    state_task = asyncio.create_task(capture_lmstudio_state(started, report["lmstudio_state"], stop))
    try:
        async with httpx.AsyncClient() as client:
            request_task = asyncio.create_task(client.post(route, json={"max_depth": None}, timeout=None))
            await asyncio.sleep(0.2)
            progress_task = asyncio.create_task(capture_progress(client, progress_url, started, report["progress_events"]))
            try:
                async with asyncio.timeout(args.timeout):
                    response = await request_task
                report["http_response"] = {
                    "at_seconds": round(time.monotonic() - started, 3),
                    "status_code": response.status_code,
                    "body": response.text,
                }
            except TimeoutError:
                report["error"] = f"HTTP route exceeded {args.timeout}s; backend request may still be running."
            except Exception as error:
                report["error"] = f"{type(error).__name__}: {error}"
            finally:
                if not request_task.done():
                    request_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await request_task
                await asyncio.sleep(1)
                progress_task.cancel()
                with suppress(asyncio.CancelledError):
                    await progress_task
    finally:
        stop.set()
        await state_task
        log_process.terminate()
        with suppress(ProcessLookupError):
            await log_process.wait()
        event_task.cancel()
        with suppress(asyncio.CancelledError):
            await event_task
        report["total_seconds"] = round(time.monotonic() - started, 3)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(report_path)
    return 1 if report["error"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
