# Mindmap Progress — Elapsed Time Only

2026-06-18 | Status: Design

## Overview

Replace the misleading mindmap generation progress bar (which stays at 10% for 5-30s then jumps to 100%) with a spinner + elapsed time display. Backend infrastructure is unchanged.

## Current Problem

`GenerateMindmap.run()` reports 3 progress events: `update("generate", 10)` → LLM call (5-30s, no updates) → `update("save", 80)` → `completed(100)`. SSE polls every 250ms; the snapshot stays identical during the LLM call, so the user sees a stuck-at-10% bar that suddenly jumps to 100%.

## Design

**Backend changes:** None. `ProgressSnapshot.elapsed_seconds` is already populated by `InMemoryProgressTracker._write()`.

**Frontend changes (2 files):**

Replace the progress-bar JSX in `WorkspaceMindmapView.jsx` and `WorkspaceSeriesMindmapView.jsx` with a spinner + elapsed text.

```jsx
{isGeneratingMindmapSelectedVideo && mindmapGenerationProgress && (
  <div className="mt-6 w-full max-w-2xl">
    <div className="workspace-elevated-panel rounded-3xl border p-5 flex items-center gap-3">
      <LoaderCircle size={18} className="animate-spin text-accent" />
      <p className="text-sm text-stone-600 dark:text-zinc-400">
        {mindmapGenerationProgress.detail || "正在生成思维导图"}
        {" · "}
        <span className="font-medium text-stone-700 dark:text-zinc-200">
          已用 {Math.round(mindmapGenerationProgress.elapsed_seconds ?? 0)} 秒
        </span>
      </p>
    </div>
  </div>
)}
```

**UX flow:**

1. Generation starts → spinner + "正在生成思维导图 · 已用 0 秒"
2. Each SSE poll → "已用 1 秒", "已用 2 秒", ... (updates every 250ms via re-render)
3. Generation completes → progress cleared → mindmap canvas shown

No percentage, no historical estimate, no post-completion toast. Just honest "in progress, X seconds elapsed".

## Acceptance Criteria

| AC# | Condition |
|-----|-----------|
| F1.1 | During mindmap generation, view shows spinner + detail text + "已用 X 秒" |
| F1.2 | Elapsed seconds updates as generation progresses (verifiable by changing snapshot over time) |
| F1.3 | No percentage / progress bar displayed |
| F1.4 | On completion, spinner disappears, mindmap canvas visible |
| F1.5 | Same behavior for series mindmap view |
| F1.6 | Existing regenerate/export buttons unchanged |

## Test Cases

```
tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
  - (modify existing progress tests)
  - test_shows_elapsed_time_during_generation
    mindmapGenerationProgress with elapsed_seconds=5 → finds "已用 5 秒"
  - test_no_percentage_bar_during_generation
    → queryByText("%") returns null
  - test_hides_progress_on_completion
    isGenerating=false → elapsed text not visible

tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
  - (same 3 tests for series)
```

## Scope

- 2 frontend files modified
- 2 test files extended
- 0 backend files
- 0 new files
