# Mindmap Generation SSE Progress — Design Spec

2026-06-17 | Status: Draft

## Overview

Add SSE (Server-Sent Events) progress reporting to single-video and series mindmap generation, reusing the existing `InMemoryProgressTracker` / `TaskProgressReporter` / `stream_progress_events` infrastructure already used by summary generation.

## Current State

Mindmap generation is a blocking POST request — the client waits for the full LLM response before seeing any result. During generation (typically 5–30 seconds), the frontend shows only a spinner/shimmer with no progress indicator.

Summary generation already solves this: the backend pushes `stage`/`progress`/`detail` events through an SSE endpoint, and the frontend renders a progress overlay with percentage and stage description.

## Design

### Progress Model

Mindmap generation has fewer stages than summary generation (no ASR/audio processing). The stages are:

| Stage | Progress | Detail |
|-------|----------|--------|
| `generate` | 0% → 80% | "正在生成思维导图" |
| `save` | 80% → 100% | "正在保存思维导图" |
| `completed` | 100% | "思维导图已生成" |
| `failed` | — | error message |

Since the LLM call is a single blocking call without intermediate progress callbacks, the initial report sets `stage="generate", progress=0`, and the final report jumps to `completed` with `progress=100`. The SSE stream updates at 250ms intervals (existing `stream_progress_events` behavior), so the client sees at minimum the starting and ending states.

### Backend Changes

**New files:** none — pure additions within existing files.

**Modified files (10):**

| # | File | Change |
|---|------|--------|
| 1 | `api/bootstrap.py` | Add `mindmap_progress_tracker: InMemoryProgressTracker` to `ApiContainer` |
| 2 | `generation/usecases/generate_mindmap.py` | `GenerateMindmap.run()` accepts optional `progress_reporter`, reports stage transitions before/after `generator.generate()` |
| 3 | `generation/usecases/generate_series_mindmap.py` | Same for series: `GenerateSeriesMindmap.run()` reports stages |
| 4 | `library/usecases/mindmap_generation.py` | `GenerateVideoMindmapFromLibrary.run()` accepts and passes `progress_reporter` |
| 5 | `library/usecases/series_mindmap_generation.py` | Same for series use-case |
| 6 | `library/ports.py` | `VideoMindmapGenerator.run()` and `SeriesMindmapGenerator.run()` add `progress_reporter` param |
| 7 | `infrastructure/library_generation_adapters.py` | Pass `progress_reporter` through both adapters |
| 8 | `infrastructure/mindmap_workflow.py` | `ConfiguredMindmapWorkflow.run()` accepts and passes `progress_reporter` |
| 9 | `infrastructure/series_mindmap_workflow.py` | Same for series workflow |
| 10 | `api/routes/videos.py` | Inject `TaskProgressReporter` into generate call; add `GET .../mindmap/generate/progress` SSE endpoint |
| 11 | `api/routes/series.py` | Same for series: inject reporter + SSE progress endpoint |

Note: `generation/ports.py` NOT modified — `MindmapGenerator.generate()` and `SeriesMindmapGenerator.generate()` ports unchanged (same pattern as `Summarizer.summarize()` which also has no `progress_reporter`). Progress reporting happens in the use-case layer wrapping port calls.

**New API endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/videos/{sid}/{vid}/mindmap/generate/progress` | SSE progress for single-video mindmap |
| GET | `/api/series/{sid}/mindmap/generate/progress` | SSE progress for series mindmap |

**Generate endpoint behavior change:**

The existing `POST .../mindmap/generate` endpoint stays synchronous (returns mindmap JSON on completion). The flow becomes:

```python
# In generate_video_mindmap endpoint:
task_id = _build_mindmap_task_id(series_id, video_id)
reporter = container.mindmap_progress_tracker.create_reporter(task_id)
try:
    reporter.update("generate", 0.0, "正在生成思维导图")
    mindmap = await container.generate_video_mindmap.run(series_id, video_id, progress_reporter=reporter)
except Exception as e:
    reporter.failed(str(e))
    raise
```

And in `GenerateMindmap.run()`:
```python
async def run(self, ..., progress_reporter=None):
    if progress_reporter:
        progress_reporter.update("generate", 10.0, "正在生成思维导图")
    mindmap = await self._generator.generate(...)
    if progress_reporter:
        progress_reporter.update("save", 80.0, "正在保存思维导图")
    await self._artifact_store.save_mindmap(mindmap=..., output_dir=...)
    if progress_reporter:
        progress_reporter.completed("思维导图已生成")
    return mindmap
```

### Frontend Changes

**Modified files (6):**

| # | File | Change |
|---|------|--------|
| 1 | `workspaceApi.js` | Add `subscribeMindmapGenerationProgress(seriesId, videoId, listener)` and `subscribeSeriesMindmapGenerationProgress(seriesId, listener)` |
| 2 | `workspaceContentActions.js` | `onGenerateMindmap()` and `onGenerateSeriesMindmap()` subscribe to SSE progress, dispatch progress updates |
| 3 | `workspaceReducer.js` | Add `mindmap_generation_progress` state + reducer cases |
| 4 | `workspaceState.js` | Add initial state: `mindmapGenerationProgress: null` |
| 5 | `ui/views/WorkspaceMindmapView.jsx` | Replace shimmer with progress bar + percentage + stage text |
| 6 | `ui/views/WorkspaceSeriesMindmapView.jsx` | Same for series view |

Progress display (replaces the shimmer animation during generation):

```jsx
{isGeneratingMindmapSelectedVideo && mindmapGenerationProgress && (
  <div className="mt-6 w-full max-w-2xl">
    <div className="workspace-elevated-panel rounded-3xl border p-5">
      <p className="text-sm font-medium text-stone-700">{mindmapGenerationProgress.detail}</p>
      <div className="mt-3 h-2 w-full rounded-full bg-stone-100">
        <div
          className="h-2 rounded-full bg-accent transition-all duration-500"
          style={{ width: `${mindmapGenerationProgress.progress ?? 0}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-stone-400">{Math.round(mindmapGenerationProgress.progress ?? 0)}%</p>
    </div>
  </div>
)}
```

## Acceptance Criteria

### Backend

| AC# | Condition |
|-----|-----------|
| B1.1 | `ApiContainer` has `mindmap_progress_tracker: InMemoryProgressTracker` |
| B1.2 | `POST .../mindmap/generate` creates a `TaskProgressReporter`, updates progress during generation |
| B1.3 | `GET .../mindmap/generate/progress` streams SSE events with status/stage/progress/detail |
| B1.4 | SSE stream terminates on `completed` / `failed` / `cancelled` |
| B1.5 | Series mindmap endpoints mirror single-video: progress SSE + reporter injection |
| B1.6 | Failed generation reports `failed` status with error detail |

### Frontend

| AC# | Condition |
|-----|-----------|
| F1.1 | During single-video mindmap generation, shows progress bar with percentage |
| F1.2 | During series mindmap generation, shows progress bar with percentage |
| F1.3 | Progress bar replaced by mindmap canvas on completion |
| F1.4 | On generation failure, progress bar removed, error message shown |
| F1.5 | Existing regenerate/export buttons still work correctly after progress is added |

## Test Cases

```
tests/backend/unit/mindmap/test_mindmap_progress.py
  ├── test_generate_mindmap_reports_progress_stages
  │     FakeMindmapGenerator + StubProgressReporter → verify update() called with "generate", "save"
  ├── test_generate_mindmap_calls_completed_on_success
  │     Verify reporter.completed() called
  ├── test_generate_mindmap_calls_failed_on_error
  │     FakeMindmapGenerator raises → verify reporter.failed() called
  ├── test_generate_mindmap_works_without_reporter
  │     progress_reporter=None → no crash (backward compat)

tests/backend/integration/api/test_mindmap_progress_api.py
  ├── test_progress_endpoint_streams_sse
  ├── test_progress_endpoint_terminates_on_completed
  ├── test_progress_returns_404_when_no_task

tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
  └── (extend existing tests)
       test_shows_progress_bar_while_generating
       test_hides_progress_bar_when_generation_completes

tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
  └── (extend existing tests)
       test_shows_progress_bar_while_generating
```

## Scope & Dependencies

- Reuses existing `InMemoryProgressTracker`, `TaskProgressReporter`, `ProgressReporter` Protocol, `stream_progress_events()` — no new infrastructure
- `ProgressReporter` Protocol already exists at `generation/ports.py:110` — reused as-is
- Mindmap generation remains synchronous request-response; SSE subscription is a separate endpoint (same pattern as summary generation)
- No changes to `agent_graph` or `domain` layers

## Exclusions

- No cancel support for mindmap generation (can be added later if needed)
- No estimated time remaining (single LLM call, progress jumps from 0→80→100)
