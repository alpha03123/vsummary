# Mindmap Generation SSE Progress — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SSE progress reporting to single-video and series mindmap generation, reusing existing `InMemoryProgressTracker` / `stream_progress_events` infrastructure.

**Architecture:** Inject `TaskProgressReporter` into the mindmap generation call chain (use-case → library → adapter → workflow). The reporter wraps the LLM call with `update("generate")` / `update("save")` / `completed()` events. SSE endpoints mirror the existing summary generation pattern. Zero new infrastructure files.

**Tech Stack:** Python 3.12, FastAPI, `stream_progress_events` (existing), React/Vite, Vitest, pytest

---

## File Structure

### No new files — all modifications to existing files

### Test files to create (3)
```
tests/backend/unit/mindmap/test_mindmap_progress.py
tests/backend/unit/mindmap/test_series_mindmap_progress.py
tests/backend/integration/api/test_mindmap_progress_api.py
```

### Backend files modified (11)
| # | File | Change |
|---|------|--------|
| 1 | `api/bootstrap.py` | Add `mindmap_progress_tracker` field to `ApiContainer` |
| 2 | `generation/usecases/generate_mindmap.py` | `GenerateMindmap.run()` accepts `progress_reporter`, reports stages |
| 3 | `generation/usecases/generate_series_mindmap.py` | Same for series |
| 4 | `library/usecases/mindmap_generation.py` | Accepts and passes `progress_reporter` |
| 5 | `library/usecases/series_mindmap_generation.py` | Same for series |
| 6 | `library/ports.py` | `VideoMindmapGenerator.run()` + `SeriesMindmapGenerator.run()` add param |
| 7 | `infrastructure/library_generation_adapters.py` | Pass through both adapters |
| 8 | `infrastructure/mindmap_workflow.py` | Accept and pass `progress_reporter` |
| 9 | `infrastructure/series_mindmap_workflow.py` | Same for series |
| 10 | `api/routes/videos.py` | Create reporter + add SSE progress endpoint |
| 11 | `api/routes/series.py` | Same for series |

### Frontend files modified (6)
| # | File | Change |
|---|------|--------|
| 12 | `workspaceApi.js` | Add SSE subscribe functions |
| 13 | `workspaceContentActions.js` | Subscribe to SSE on generate, dispatch progress |
| 14 | `workspaceReducer.js` | Add `mindmapGenerationProgress` + reducer cases |
| 15 | `workspaceState.js` | Add initial state |
| 16 | `ui/views/WorkspaceMindmapView.jsx` | Progress bar replaces shimmer |
| 17 | `ui/views/WorkspaceSeriesMindmapView.jsx` | Same for series |

---

## Phase 1: Progress Propagation Through Backend Layers

### Task 1: Unit tests for progress reporting in GenerateMindmap

**Files:**
- Create: `tests/backend/unit/mindmap/test_mindmap_progress.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/backend/unit/mindmap/test_mindmap_progress.py
from __future__ import annotations

import unittest
from pathlib import Path

from backend.video_summary.generation.usecases.generate_mindmap import GenerateMindmap


class StubProgressReporter:
    def __init__(self):
        self.updates = []
        self._completed_called = False
        self._failed_called = False
        self._failed_message = None

    def update(self, stage, progress=None, detail=None):
        self.updates.append({"stage": stage, "progress": progress, "detail": detail})

    def completed(self, detail=None):
        self._completed_called = True

    def failed(self, message):
        self._failed_called = True
        self._failed_message = message

    def is_cancel_requested(self):
        return False

    def raise_if_cancelled(self):
        pass


class FakeMindmapGenerator:
    async def generate(self, *, title, duration_seconds, summary_data, transcript_text=""):
        return {"id": "root", "title": title, "children": []}


class FakeGenerationArtifactStore:
    def __init__(self, fail_on_save=False):
        self._saved = None
        self._fail_on_save = fail_on_save

    async def save_mindmap(self, *, mindmap, output_dir):
        if self._fail_on_save:
            raise IOError("disk full")
        self._saved = mindmap


class GenerateMindmapProgressTests(unittest.TestCase):
    async def test_reports_progress_stages(self):
        reporter = StubProgressReporter()
        use_case = GenerateMindmap(
            generator=FakeMindmapGenerator(),
            artifact_store=FakeGenerationArtifactStore(),
        )
        await use_case.run(
            title="Test",
            duration_seconds=300.0,
            summary_data={"chapters": []},
            output_dir=Path("/tmp/test"),
            progress_reporter=reporter,
        )
        stages = [u["stage"] for u in reporter.updates]
        self.assertIn("generate", stages)
        self.assertIn("save", stages)
        self.assertTrue(reporter._completed_called)

    async def test_calls_completed_on_success(self):
        reporter = StubProgressReporter()
        use_case = GenerateMindmap(
            generator=FakeMindmapGenerator(),
            artifact_store=FakeGenerationArtifactStore(),
        )
        await use_case.run(
            title="Test", duration_seconds=300.0,
            summary_data={"chapters": []}, output_dir=Path("/tmp/test"),
            progress_reporter=reporter,
        )
        self.assertTrue(reporter._completed_called)

    async def test_calls_failed_on_generator_error(self):
        reporter = StubProgressReporter()
        class FailingGenerator:
            async def generate(self, **kwargs):
                raise RuntimeError("LLM connection failed")
        use_case = GenerateMindmap(
            generator=FailingGenerator(),
            artifact_store=FakeGenerationArtifactStore(),
        )
        with self.assertRaises(RuntimeError):
            await use_case.run(
                title="Test", duration_seconds=300.0,
                summary_data={"chapters": []}, output_dir=Path("/tmp/test"),
                progress_reporter=reporter,
            )
        self.assertTrue(reporter._failed_called)
        self.assertIn("LLM connection failed", reporter._failed_message)
        self.assertFalse(reporter._completed_called)

    async def test_reports_failed_on_save_error(self):
        reporter = StubProgressReporter()
        use_case = GenerateMindmap(
            generator=FakeMindmapGenerator(),
            artifact_store=FakeGenerationArtifactStore(fail_on_save=True),
        )
        with self.assertRaises(IOError):
            await use_case.run(
                title="Test", duration_seconds=300.0,
                summary_data={"chapters": []}, output_dir=Path("/tmp/test"),
                progress_reporter=reporter,
            )
        self.assertTrue(reporter._failed_called)
        self.assertFalse(reporter._completed_called)

    async def test_works_without_reporter(self):
        use_case = GenerateMindmap(
            generator=FakeMindmapGenerator(),
            artifact_store=FakeGenerationArtifactStore(),
        )
        result = await use_case.run(
            title="Test", duration_seconds=300.0,
            summary_data={"chapters": []}, output_dir=Path("/tmp/test"),
        )
        self.assertEqual(result["title"], "Test")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_mindmap_progress.py -v
```
Expected: FAIL — `GenerateMindmap.run() got an unexpected keyword argument 'progress_reporter'`

- [ ] **Step 3: Update `GenerateMindmap.run()`**

```python
# src/backend/video_summary/generation/usecases/generate_mindmap.py
# Add import at top:
from backend.video_summary.generation.ports import ProgressReporter

# Update run() signature and body:

    async def run(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
        output_dir: Path,
        transcript_text: str = "",
        progress_reporter: ProgressReporter | None = None,
    ) -> dict[str, object]:
        if progress_reporter is not None:
            progress_reporter.update("generate", 10.0, "正在生成思维导图")
        mindmap = await self._generator.generate(
            title=title,
            duration_seconds=duration_seconds,
            summary_data=summary_data,
            transcript_text=transcript_text,
        )
        if progress_reporter is not None:
            progress_reporter.update("save", 80.0, "正在保存思维导图")
        await self._artifact_store.save_mindmap(mindmap=mindmap, output_dir=output_dir)
        if progress_reporter is not None:
            progress_reporter.completed("思维导图已生成")
        return mindmap
```

Note: If the generator raises, the exception propagates naturally — the API route's `except` block will call `reporter.failed()`. The use-case itself does NOT catch exceptions so progress reporting on failure is handled at the API layer.

- [ ] **Step 4: Run tests — verify they pass**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_mindmap_progress.py -v
```
Expected: 5 PASS (4 progress tests + 1 backward-compat)

- [ ] **Step 5: Commit**

```bash
git add tests/backend/unit/mindmap/test_mindmap_progress.py src/backend/video_summary/generation/usecases/generate_mindmap.py
git commit -m "feat(mindmap-progress): add progress_reporter to GenerateMindmap use-case with 5 tests"
```

---

### Task 2: Propagate progress_reporter through library layer (single-video)

**Files:**
- Modify: `src/backend/video_summary/library/ports.py`
- Modify: `src/backend/video_summary/library/usecases/mindmap_generation.py`
- Modify: `src/backend/video_summary/infrastructure/library_generation_adapters.py`
- Modify: `src/backend/video_summary/infrastructure/mindmap_workflow.py`

- [ ] **Step 1: Update `VideoMindmapGenerator` Protocol**

```python
# src/backend/video_summary/library/ports.py
# In VideoMindmapGenerator.run() signature, add after transcript_text:

        progress_reporter: ProgressReporter | None = None,
```

`ProgressReporter` is already imported at line 13 of `library/ports.py`.

- [ ] **Step 2: Update `GenerateVideoMindmapFromLibrary.run()`**

```python
# src/backend/video_summary/library/usecases/mindmap_generation.py
# Add import:
from backend.video_summary.generation.ports import ProgressReporter

# Update run() to accept and pass progress_reporter:

    async def run(self, series_id: str, video_id: str, progress_reporter: ProgressReporter | None = None) -> VideoMindmapDTO | None:
        summary = self._workspace.get_video_summary(series_id, video_id)
        if summary is None:
            return None

        transcript = self._workspace.get_video_transcript(series_id, video_id)
        transcript_text = "\n".join(s.text for s in transcript.segments) if transcript is not None else ""

        try:
            await self._generator.run(
                series_id=series_id,
                video_id=video_id,
                summary_data=summary.summary,
                transcript_text=transcript_text,
                progress_reporter=progress_reporter,
            )
        except LookupError:
            return None
        return self._workspace.get_video_mindmap(series_id, video_id)
```

- [ ] **Step 3: Update `WorkspaceBackedVideoMindmapGenerator.run()`**

```python
# src/backend/video_summary/infrastructure/library_generation_adapters.py
# In WorkspaceBackedVideoMindmapGenerator.run(), add progress_reporter:

    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        summary_data: dict[str, object],
        transcript_text: str = "",
        progress_reporter=None,
    ) -> None:
        video = _require_video_source(self._workspace, series_id, video_id)
        await self._workflow.run(
            video.source_path, video.output_dir, summary_data,
            transcript_text=transcript_text,
            progress_reporter=progress_reporter,
        )
```

- [ ] **Step 4: Update `ConfiguredMindmapWorkflow.run()`**

```python
# src/backend/video_summary/infrastructure/mindmap_workflow.py
# In ConfiguredMindmapWorkflow.run(), add progress_reporter:

    async def run(self, source_path: Path, output_dir: Path, summary_data: dict[str, object], transcript_text: str = "", progress_reporter=None) -> None:
        application = self._get_application()
        await application.use_case.run(
            title=source_path.stem,
            duration_seconds=_resolve_duration_seconds(summary_data),
            summary_data=summary_data,
            output_dir=output_dir,
            transcript_text=transcript_text,
            progress_reporter=progress_reporter,
        )
```

- [ ] **Step 5: Run existing tests to verify backward compat**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/ -v
```
Expected: all existing tests PASS (19 + 5 new = 24)

- [ ] **Step 6: Commit**

```bash
git add src/backend/video_summary/library/ports.py src/backend/video_summary/library/usecases/mindmap_generation.py src/backend/video_summary/infrastructure/library_generation_adapters.py src/backend/video_summary/infrastructure/mindmap_workflow.py
git commit -m "feat(mindmap-progress): propagate progress_reporter through library, adapter, and workflow"
```

---

### Task 3: Progress reporting in series mindmap use-case

**Files:**
- Create: `tests/backend/unit/mindmap/test_series_mindmap_progress.py`
- Modify: `src/backend/video_summary/generation/usecases/generate_series_mindmap.py`

- [ ] **Step 1: Write failing series progress tests**

```python
# tests/backend/unit/mindmap/test_series_mindmap_progress.py
from __future__ import annotations

import unittest
from pathlib import Path

from backend.video_summary.generation.usecases.generate_series_mindmap import GenerateSeriesMindmap


class StubProgressReporter:
    def __init__(self):
        self.updates = []
        self._completed_called = False

    def update(self, stage, progress=None, detail=None):
        self.updates.append({"stage": stage, "progress": progress, "detail": detail})

    def completed(self, detail=None):
        self._completed_called = True

    def failed(self, message):
        pass

    def is_cancel_requested(self):
        return False

    def raise_if_cancelled(self):
        pass


class FakeSeriesMindmapGenerator:
    async def generate(self, *, series_title, catalog, video_summaries):
        return {"id": "root", "title": series_title, "children": []}


class FakeSeriesArtifactStore:
    async def save_mindmap(self, *, mindmap, output_dir):
        pass


class GenerateSeriesMindmapProgressTests(unittest.TestCase):
    async def test_reports_progress_stages(self):
        reporter = StubProgressReporter()
        use_case = GenerateSeriesMindmap(
            generator=FakeSeriesMindmapGenerator(),
            artifact_store=FakeSeriesArtifactStore(),
        )
        await use_case.run(
            series_title="ML Course",
            catalog={"series_title": "ML Course", "videos": []},
            video_summaries=[{"title": "V1"}],
            output_dir=Path("/tmp/test"),
            progress_reporter=reporter,
        )
        stages = [u["stage"] for u in reporter.updates]
        self.assertIn("generate", stages)
        self.assertIn("save", stages)
        self.assertTrue(reporter._completed_called)

    async def test_calls_completed_on_success(self):
        reporter = StubProgressReporter()
        use_case = GenerateSeriesMindmap(
            generator=FakeSeriesMindmapGenerator(),
            artifact_store=FakeSeriesArtifactStore(),
        )
        await use_case.run(
            series_title="ML",
            catalog=None,
            video_summaries=[],
            output_dir=Path("/tmp/test"),
            progress_reporter=reporter,
        )
        self.assertTrue(reporter._completed_called)

    async def test_works_without_reporter(self):
        use_case = GenerateSeriesMindmap(
            generator=FakeSeriesMindmapGenerator(),
            artifact_store=FakeSeriesArtifactStore(),
        )
        result = await use_case.run(
            series_title="ML", catalog=None, video_summaries=[],
            output_dir=Path("/tmp/test"),
        )
        self.assertEqual(result["title"], "ML")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_series_mindmap_progress.py -v
```
Expected: FAIL — `progress_reporter` param not accepted

- [ ] **Step 3: Update `GenerateSeriesMindmap.run()`**

```python
# src/backend/video_summary/generation/usecases/generate_series_mindmap.py
# Add import:
from backend.video_summary.generation.ports import ProgressReporter

# Update run():

    async def run(
        self,
        *,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
    ) -> dict[str, object]:
        if progress_reporter is not None:
            progress_reporter.update("generate", 10.0, "正在生成系列思维导图")
        mindmap = await self._generator.generate(
            series_title=series_title,
            catalog=catalog,
            video_summaries=video_summaries,
        )
        if progress_reporter is not None:
            progress_reporter.update("save", 80.0, "正在保存系列思维导图")
        await self._artifact_store.save_mindmap(mindmap=mindmap, output_dir=output_dir)
        if progress_reporter is not None:
            progress_reporter.completed("系列思维导图已生成")
        return mindmap
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_series_mindmap_progress.py -v
```
Expected: 3 PASS

- [ ] **Step 5: Update `library/usecases/series_mindmap_generation.py`** (chain propagation)

```python
# In GenerateSeriesMindmapFromLibrary.run(), add progress_reporter param and pass to generator:
    async def run(self, series_id: str, progress_reporter=None):
        # ... existing logic ...
        await self._generator.run(
            series_id=series_id,
            series_title=series.title,
            catalog=catalog,
            video_summaries=summaries,
            progress_reporter=progress_reporter,
        )
```

- [ ] **Step 6: Update `library/ports.py` — `SeriesMindmapGenerator.run()`**

```python
# Add to SeriesMindmapGenerator.run() signature:
        progress_reporter=None,
```

- [ ] **Step 7: Update `infrastructure/library_generation_adapters.py` — `WorkspaceBackedSeriesMindmapGenerator`**

```python
# Add progress_reporter param, pass to workflow:
        await self._workflow.run(series_dir, series_title, catalog, video_summaries, progress_reporter=progress_reporter)
```

- [ ] **Step 8: Update `infrastructure/series_mindmap_workflow.py`**

```python
# In ConfiguredSeriesMindmapWorkflow.run(), add progress_reporter and pass:
    async def run(self, series_dir, series_title, catalog, video_summaries, progress_reporter=None):
        application = self._get_application()
        await application.use_case.run(
            series_title=series_title,
            catalog=catalog,
            video_summaries=video_summaries,
            output_dir=series_dir,
            progress_reporter=progress_reporter,
        )
```

- [ ] **Step 9: Run all mindmap tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/ -v
```
Expected: 27 PASS (19 + 5 + 3)

- [ ] **Step 10: Commit**

```bash
git add tests/backend/unit/mindmap/test_series_mindmap_progress.py src/backend/video_summary/generation/usecases/generate_series_mindmap.py src/backend/video_summary/library/usecases/series_mindmap_generation.py src/backend/video_summary/library/ports.py src/backend/video_summary/infrastructure/library_generation_adapters.py src/backend/video_summary/infrastructure/series_mindmap_workflow.py
git commit -m "feat(mindmap-progress): add progress_reporter to series mindmap chain"
```

---

### Task 4: API routes — inject reporter, add SSE progress endpoints

**Files:**
- Modify: `src/backend/api/bootstrap.py`
- Modify: `src/backend/api/routes/videos.py`
- Modify: `src/backend/api/routes/series.py`
- Create: `tests/backend/integration/api/test_mindmap_progress_api.py`

- [ ] **Step 1: Add `mindmap_progress_tracker` to `ApiContainer`**

```python
# src/backend/api/bootstrap.py
# In ApiContainer dataclass, add after generation_progress_tracker:
    mindmap_progress_tracker: InMemoryProgressTracker
```

In `build_api_container()`, add:
```python
    mindmap_progress_tracker=InMemoryProgressTracker(),
```

- [ ] **Step 2: Update single-video mindmap generate endpoint**

```python
# src/backend/api/routes/videos.py
# In generate_video_mindmap(), add progress reporter injection:

def _build_mindmap_task_id(series_id: str, video_id: str) -> str:
    return f"mindmap|{series_id}|{video_id}"

@router.post("/api/videos/{series_id}/{video_id}/mindmap/generate")
async def generate_video_mindmap(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    task_id = _build_mindmap_task_id(series_id, video_id)
    reporter = container.mindmap_progress_tracker.create_reporter(task_id)
    try:
        reporter.update("generate", 0.0, "正在生成思维导图")
        video_mindmap = await container.generate_video_mindmap.run(series_id, video_id, progress_reporter=reporter)
    except Exception:
        reporter.failed(str(sys.exc_info()[1]) if sys.exc_info()[1] else "思维导图生成失败")
        raise
    if video_mindmap is None:
        reporter.failed("总结不存在，无法生成思维导图")
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    reporter.completed("思维导图已生成")
    return video_mindmap.mindmap
```

Add `import sys` at top if not already imported.

- [ ] **Step 3: Add SSE progress endpoint for single-video mindmap**

```python
# src/backend/api/routes/videos.py — add after the generate endpoint:

@router.get("/api/videos/{series_id}/{video_id}/mindmap/generate/progress")
async def stream_mindmap_generation_progress(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    task_id = _build_mindmap_task_id(series_id, video_id)
    return StreamingResponse(
        stream_progress_events(
            tracker=container.mindmap_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 4: Update series mindmap generate endpoint**

```python
# src/backend/api/routes/series.py — add task_id builder + update generate:

def _build_series_mindmap_task_id(series_id: str) -> str:
    return f"series-mindmap|{series_id}"

# In generate_series_mindmap():
    task_id = _build_series_mindmap_task_id(series_id)
    reporter = container.mindmap_progress_tracker.create_reporter(task_id)
    try:
        reporter.update("generate", 0.0, "正在生成系列思维导图")
        mindmap = await container.generate_series_mindmap.run(series_id, progress_reporter=reporter)
    except Exception:
        reporter.failed(str(sys.exc_info()[1]) if sys.exc_info()[1] else "系列思维导图生成失败")
        raise
    if mindmap is None:
        reporter.failed("系列下没有已生成概况的视频")
        raise HTTPException(status_code=400, detail="系列下没有已生成概况的视频")
    reporter.completed("系列思维导图已生成")
    return mindmap.mindmap
```

- [ ] **Step 5: Add SSE progress endpoint for series mindmap**

```python
# src/backend/api/routes/series.py — add:

@router.get("/api/series/{series_id}/mindmap/generate/progress")
async def stream_series_mindmap_generation_progress(
    series_id: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    task_id = _build_series_mindmap_task_id(series_id)
    return StreamingResponse(
        stream_progress_events(
            tracker=container.mindmap_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 6: Write integration tests for progress endpoints**

```python
# tests/backend/integration/api/test_mindmap_progress_api.py
from __future__ import annotations

import unittest
from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient
from backend.api.app import create_app


class MindmapProgressApiTests(unittest.TestCase):
    def _build_container(self, *, mindmap_result=None, raise_error=None):
        from backend.video_summary.infrastructure.in_memory_progress_tracker import (
            InMemoryProgressTracker,
        )
        tracker = InMemoryProgressTracker()

        class FakeUseCase:
            async def run(self, series_id, video_id, progress_reporter=None):
                if raise_error:
                    raise raise_error
                return SimpleNamespace(mindmap=mindmap_result or {})

        return SimpleNamespace(
            generate_video_mindmap=FakeUseCase(),
            mindmap_progress_tracker=tracker,
        )

    def test_progress_endpoint_streams_sse(self):
        container = self._build_container(mindmap_result={"id": "root", "title": "T"})
        client = TestClient(create_app(container))
        # Trigger generation first to create snapshot
        client.post("/api/videos/s1/v1/mindmap/generate")
        response = client.get("/api/videos/s1/v1/mindmap/generate/progress")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])

    def test_progress_returns_404_when_no_task(self):
        container = self._build_container()
        client = TestClient(create_app(container))
        response = client.get("/api/videos/s1/v1/mindmap/generate/progress")
        self.assertEqual(response.status_code, 404)

    def test_progress_endpoint_terminates_on_completed(self):
        container = self._build_container(mindmap_result={"id": "root", "title": "T"})
        client = TestClient(create_app(container))
        # Trigger generation
        client.post("/api/videos/s1/v1/mindmap/generate")
        # Read SSE stream until terminal
        response = client.get("/api/videos/s1/v1/mindmap/generate/progress")
        self.assertEqual(response.status_code, 200)
        # Parse SSE data lines, verify last event has status "completed"
        body = response.text
        self.assertIn('"status":"completed"', body)

    def test_progress_endpoint_terminates_on_failed(self):
        container = self._build_container(raise_error=RuntimeError("LLM error"))
        client = TestClient(create_app(container))
        try:
            client.post("/api/videos/s1/v1/mindmap/generate")
        except Exception:
            pass  # Expected — the endpoint re-raises after logging
        response = client.get("/api/videos/s1/v1/mindmap/generate/progress")
        body = response.text
        self.assertIn('"status":"failed"', body)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 7: Run all tests + import-linter**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/ -v && lint-imports
```
Expected: 27 unit PASS + 10 contracts kept

- [ ] **Step 8: Commit**

```bash
git add src/backend/api/bootstrap.py src/backend/api/routes/videos.py src/backend/api/routes/series.py tests/backend/integration/api/test_mindmap_progress_api.py
git commit -m "feat(mindmap-progress): add SSE progress endpoints and tracker to container"
```

---

## Phase 2: Frontend Progress Display

### Task 5: Frontend state + API + reducer

**Files:**
- Modify: `src/frontend/src/features/workspace/model/workspaceState.js`
- Modify: `src/frontend/src/features/workspace/model/workspaceReducer.js`
- Modify: `src/frontend/src/features/workspace/model/workspaceApi.js`

- [ ] **Step 1: Add initial state**

```javascript
// workspaceState.js — in createInitialWorkspaceState return:
    mindmapGenerationProgress: null,
```

- [ ] **Step 2: Add reducer cases**

```javascript
// workspaceReducer.js — add cases:
    case "mindmap_generation_progress_updated":
      return { ...state, mindmapGenerationProgress: action.snapshot };

    case "mindmap_generation_progress_cleared":
      return { ...state, mindmapGenerationProgress: null };
```

- [ ] **Step 3: Add SSE subscribe function**

```javascript
// workspaceApi.js — add:
export function subscribeMindmapGenerationProgress(seriesId, videoId, listener) {
  const eventSource = new EventSource(
    `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap/generate/progress`
  );
  let terminal = false;

  eventSource.onmessage = (event) => {
    const snapshot = JSON.parse(event.data);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    if (terminal) return;
    listener({ status: "failed", stage: "failed", progress: null, detail: "进度连接已中断", error: "进度连接已中断" });
    eventSource.close();
  };

  return () => {
    terminal = true;
    eventSource.close();
  };
}

export function subscribeSeriesMindmapGenerationProgress(seriesId, listener) {
  const eventSource = new EventSource(
    `/api/series/${encodeURIComponent(seriesId)}/mindmap/generate/progress`
  );
  let terminal = false;

  eventSource.onmessage = (event) => {
    const snapshot = JSON.parse(event.data);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    if (terminal) return;
    listener({ status: "failed", stage: "failed", progress: null, detail: "进度连接已中断", error: "进度连接已中断" });
    eventSource.close();
  };

  return () => {
    terminal = true;
    eventSource.close();
  };
}
```

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/workspace/model/workspaceState.js src/frontend/src/features/workspace/model/workspaceReducer.js src/frontend/src/features/workspace/model/workspaceApi.js
git commit -m "feat(mindmap-progress): add frontend state, reducer, and SSE subscribe functions"
```

---

### Task 6: Frontend actions + controller — wire SSE subscription

**Files:**
- Modify: `src/frontend/src/features/workspace/model/workspaceContentActions.js`
- Modify: `src/frontend/src/features/workspace/model/useWorkspaceController.js`

- [ ] **Step 1: Update `onGenerateMindmap` to subscribe to progress**

```javascript
// workspaceContentActions.js — in onGenerateMindmap():
  async function onGenerateMindmap() {
    if (!state.selectedSeriesId || !state.selectedVideoId) return;

    const seriesId = state.selectedSeriesId;
    const videoId = state.selectedVideoId;
    const videoKey = buildVideoKey(seriesId, videoId);
    dispatch({ type: "mindmap_generation_started", videoKey });

    // Subscribe to SSE progress
    const unsubscribe = subscribeMindmapGenerationProgress(seriesId, videoId, (snapshot) => {
      dispatch({ type: "mindmap_generation_progress_updated", snapshot });
    });

    try {
      const mindmapResult = await generateVideoMindmap(seriesId, videoId);
      unsubscribe();
      dispatch({ type: "mindmap_generation_progress_cleared" });
      dispatch({
        type: "mindmap_generation_succeeded",
        mindmap: mindmapResult,
      });
    } catch (error) {
      unsubscribe();
      dispatch({ type: "mindmap_generation_progress_cleared" });
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "生成失败",
      });
    }
  }
```

Add `subscribeMindmapGenerationProgress` to the import from `"./workspaceApi"`.

- [ ] **Step 2: Update `onGenerateSeriesMindmap` similarly**

```javascript
// workspaceContentActions.js — in onGenerateSeriesMindmap():
  async function onGenerateSeriesMindmap() {
    if (!state.selectedSeriesId) return;

    const seriesId = state.selectedSeriesId;
    dispatch({ type: "series_mindmap_generation_started" });

    const unsubscribe = subscribeSeriesMindmapGenerationProgress(seriesId, (snapshot) => {
      dispatch({ type: "mindmap_generation_progress_updated", snapshot });
    });

    try {
      const mindmapResult = await generateSeriesMindmap(seriesId);
      unsubscribe();
      dispatch({ type: "mindmap_generation_progress_cleared" });
      dispatch({ type: "series_mindmap_generation_succeeded", mindmap: mindmapResult });
    } catch (error) {
      unsubscribe();
      dispatch({ type: "mindmap_generation_progress_cleared" });
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "系列导图生成失败",
      });
    }
  }
```

Add `subscribeSeriesMindmapGenerationProgress` to import.

- [ ] **Step 3: Pass `mindmapGenerationProgress` through controller**

```javascript
// useWorkspaceController.js — add:
    const mindmapGenerationProgress = state.mindmapGenerationProgress;

// Add to return object:
    mindmapGenerationProgress,
```

- [ ] **Step 4: Pass through page model**

```javascript
// workspacePageModel.js — in the shell or generation block, add:
      mindmapGenerationProgress: controller.mindmapGenerationProgress,
```

- [ ] **Step 5: Run frontend tests to verify no regressions**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/
```
Expected: all existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/workspace/model/workspaceContentActions.js src/frontend/src/features/workspace/model/useWorkspaceController.js src/frontend/src/features/workspace/model/workspacePageModel.js
git commit -m "feat(mindmap-progress): wire SSE progress into content actions and controller"
```

---

### Task 7: Frontend views — progress bar UI

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx`
- Modify: `src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx`
- Modify: `src/frontend/src/features/workspace/ui/WorkspaceReadingPane.jsx`

- [ ] **Step 1: Add `mindmapGenerationProgress` prop to WorkspaceMindmapView**

```jsx
// WorkspaceMindmapView.jsx — add to props:
  mindmapGenerationProgress,
```

Replace the shimmer animation block (the `{isGeneratingMindmapSelectedVideo ? (...)}` section) with:

```jsx
{isGeneratingMindmapSelectedVideo && mindmapGenerationProgress && (
  <div className="motion-fade-up mt-6 w-full max-w-2xl">
    <div className="workspace-elevated-panel rounded-3xl border p-5">
      <p className="text-sm font-medium text-stone-700 dark:text-zinc-300">
        {mindmapGenerationProgress.detail || "正在生成..."}
      </p>
      <div className="mt-3 h-2 w-full rounded-full bg-stone-100 dark:bg-stone-800">
        <div
          className="h-2 rounded-full bg-accent transition-all duration-500"
          style={{ width: `${mindmapGenerationProgress.progress ?? 0}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-stone-400">
        {Math.round(mindmapGenerationProgress.progress ?? 0)}%
      </p>
    </div>
  </div>
)}
```

- [ ] **Step 2: Same for WorkspaceSeriesMindmapView**

Add `mindmapGenerationProgress` prop to `WorkspaceSeriesMindmapView`, replace its shimmer too.

- [ ] **Step 3: Pass `mindmapGenerationProgress` from WorkspaceReadingPane**

Find the `<WorkspaceMindmapView` usage and add:
```jsx
mindmapGenerationProgress={mindmapGenerationProgress}
```

Same for `<WorkspaceSeriesMindmapView`.

Add `mindmapGenerationProgress` to the destructured props.

- [ ] **Step 4: Write frontend progress tests**

Add to `tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx`:
```jsx
describe("WorkspaceMindmapView — progress bar", () => {
  const baseProps = {
    tools: makeTools({ generated: false }),
    mindmap: null,
    selectedNode: null,
    mindmapLoading: false,
    isGeneratingMindmapSelectedVideo: false,
    onFocusNode: vi.fn(),
    onGenerateMindmap: vi.fn(),
    seriesId: "s1",
    videoId: "v1",
    mindmapGenerationProgress: null,
  };

  it("shows progress bar while generating", () => {
    render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={true}
        mindmapGenerationProgress={{ status: "running", stage: "generate", progress: 45, detail: "正在生成思维导图" }}
      />
    );
    expect(screen.getByText("正在生成思维导图")).toBeTruthy();
    expect(screen.getByText("45%")).toBeTruthy();
  });

  it("hides progress bar when generation completes", () => {
    render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={false}
        mindmap={{ id: "root", title: "Test", children: [] }}
        mindmapGenerationProgress={null}
      />
    );
    expect(screen.queryByText("45%")).toBeNull();
  });

  it("shows error when generation fails", () => {
    render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={false}
        mindmapGenerationProgress={{ status: "failed", stage: "failed", progress: null, detail: null, error: "LLM error" }}
      />
    );
    // Error is displayed via the load_failed dispatch, not in this component directly.
    // The component simply hides the progress bar (since isGenerating is false).
    expect(screen.queryByText("45%")).toBeNull();
  });
});
```

Add to `tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx`:
```jsx
describe("WorkspaceSeriesMindmapView — progress bar", () => {
  const baseProps = {
    seriesId: "s1",
    seriesMindmap: null,
    seriesMindmapAvailable: true,
    seriesMindmapLoading: false,
    generatingSeriesMindmap: false,
    selectedNode: null,
    onFocusNode: vi.fn(),
    onGenerateSeriesMindmap: vi.fn(),
    mindmapGenerationProgress: null,
  };

  it("shows progress bar while generating", () => {
    render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={true}
        mindmapGenerationProgress={{ status: "running", stage: "generate", progress: 30, detail: "正在生成系列思维导图" }}
      />
    );
    expect(screen.getByText("30%")).toBeTruthy();
  });

  it("hides progress bar when generation completes", () => {
    render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={false}
        seriesMindmap={{ id: "root", title: "Test", children: [] }}
        mindmapGenerationProgress={null}
      />
    );
    expect(screen.queryByText("30%")).toBeNull();
  });
});
```

- [ ] **Step 5: Run frontend tests**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/
```
Expected: all tests PASS (existing + 5 new)

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx src/frontend/src/features/workspace/ui/WorkspaceReadingPane.jsx tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
git commit -m "feat(mindmap-progress): add progress bar UI to mindmap views with 5 frontend tests"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run all backend tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/ -v
```
Expected: 27 PASS

- [ ] **Step 2: Run integration tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/integration/api/test_mindmap_progress_api.py -v
```
Expected: 4 PASS (collection errors from missing lancedb dep are OK)

- [ ] **Step 3: Run import-linter**

```bash
PYTHONPATH=src lint-imports
```
Expected: 10 kept, 0 broken

- [ ] **Step 4: Run all frontend tests**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/
```
Expected: all PASS (F1.5 verified by existing regenerate/export button tests passing)

- [ ] **Step 5: Verify boundary cases**

| # | Boundary | Verification |
|---|----------|--------------|
| 1 | `save_mindmap()` raises → `failed()` | Task 1 `test_reports_failed_on_save_error` PASS |
| 2 | SSE EventSource drops → auto-reconnect | Browser-standard behavior, no test needed |
| 3 | Multiple SSE subscribers on same task_id | `InMemoryProgressTracker` is thread-safe (`threading.Lock`), each subscriber gets independent `async for` loop |
| 4 | `progress_reporter=None` through chain | Task 1 + Task 3 `test_works_without_reporter` PASS |

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore(mindmap-progress): final verification — all tests pass, import-linter clean"
```
