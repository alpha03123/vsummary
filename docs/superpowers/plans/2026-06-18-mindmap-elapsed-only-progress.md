# Mindmap Progress — Elapsed Time Only — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the misleading mindmap progress bar (stuck at 10% then jumps to 100%) with a spinner + "已用 X 秒" display.

**Architecture:** Frontend-only change. Backend infrastructure untouched — `ProgressSnapshot.elapsed_seconds` is already populated by `InMemoryProgressTracker._write()`. View renders the existing snapshot field instead of a fake progress bar.

**Tech Stack:** React 19, Vite, Vitest, lucide-react

---

## File Structure

### No new files

### Modified files (4)
| # | File | Change |
|---|------|--------|
| 1 | `src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx` | Replace progress bar JSX with spinner + elapsed text |
| 2 | `src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx` | Same for series |
| 3 | `tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx` | Modify existing progress tests; add F1.2 rerender test |
| 4 | `tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx` | Same for series (note: file is at `ui/`, not `ui/views/`) |

---

## Task 1: Update WorkspaceMindmapView + tests (single-video)

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx`
- Modify: `tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx`

- [ ] **Step 1: Read the existing progress-bar JSX in WorkspaceMindmapView.jsx**

Read the file. Find the existing block that renders the progress bar — it's guarded by `isGeneratingMindmapSelectedVideo && mindmapGenerationProgress && (...)` and contains the percentage text and the accent-colored bar.

- [ ] **Step 2: Replace the progress-bar JSX with spinner + elapsed text**

Find the progress-bar block. Replace the inner contents (the `<div className="mt-3 h-2 ...">` progress bar AND the percentage text) with this single-line spinner + text layout. Keep the outer wrapper and the conditional guard.

```jsx
<div className="workspace-elevated-panel rounded-3xl border p-5 flex items-center gap-3">
  <LoaderCircle size={18} strokeWidth={2.2} className="animate-spin text-accent" />
  <p className="text-sm text-stone-600 dark:text-zinc-400">
    {mindmapGenerationProgress.detail || "正在生成思维导图"}
    <span className="mx-2 text-stone-300 dark:text-zinc-600">·</span>
    <span className="font-medium text-stone-700 dark:text-zinc-200">
      已用 {Math.round(mindmapGenerationProgress.elapsed_seconds ?? 0)} 秒
    </span>
  </p>
</div>
```

NOTE: `LoaderCircle` is already imported in this file (used for the existing "Generating Mindmap..." button). Do NOT add new imports.

- [ ] **Step 3: Read the existing tests file**

Read `tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx`. Find the `describe("WorkspaceMindmapView — progress bar", ...)` block. It has 3 tests that check for the percentage text "45%".

- [ ] **Step 4: Update the 3 existing progress tests + add 1 rerender test**

Replace the entire `describe("WorkspaceMindmapView — progress bar", ...)` block with:

```jsx
describe("WorkspaceMindmapView — elapsed time progress", () => {
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

  it("shows elapsed time during generation", () => {
    render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={true}
        mindmapGenerationProgress={{
          status: "running",
          stage: "generate",
          progress: 45,
          detail: "正在生成思维导图",
          elapsed_seconds: 5,
        }}
      />
    );
    expect(screen.getByText("正在生成思维导图")).toBeTruthy();
    expect(screen.getByText("已用 5 秒")).toBeTruthy();
  });

  it("shows updated elapsed time on rerender", () => {
    const { rerender } = render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 45,
          detail: "正在生成思维导图", elapsed_seconds: 5,
        }}
      />
    );
    expect(screen.getByText("已用 5 秒")).toBeTruthy();

    rerender(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 45,
          detail: "正在生成思维导图", elapsed_seconds: 8,
        }}
      />
    );
    expect(screen.getByText("已用 8 秒")).toBeTruthy();
  });

  it("does not show percentage during generation", () => {
    render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 45,
          detail: "正在生成思维导图", elapsed_seconds: 5,
        }}
      />
    );
    expect(screen.queryByText("45%")).toBeNull();
  });

  it("hides progress on completion", () => {
    render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={false}
        mindmap={{ id: "root", title: "Test", children: [] }}
        mindmapGenerationProgress={null}
      />
    );
    expect(screen.queryByText(/已用.*秒/)).toBeNull();
  });
});
```

- [ ] **Step 5: Run frontend tests**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx
```
Expected: 4 tests in the new describe block PASS, plus all existing tests still PASS (no regression).

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx
git commit -m "feat(mindmap-progress): replace progress bar with elapsed-time spinner"
```

---

## Task 2: Update WorkspaceSeriesMindmapView + tests (series)

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx`
- Modify: `tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx`

- [ ] **Step 1: Replace the series progress-bar JSX**

Read `src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx`. Find the progress-bar block (added in Task 7 of the SSE progress work). Replace the inner contents with the same spinner + elapsed text pattern:

```jsx
<div className="workspace-elevated-panel rounded-3xl border p-5 flex items-center gap-3">
  <LoaderCircle size={18} strokeWidth={2.2} className="animate-spin text-accent" />
  <p className="text-sm text-stone-600 dark:text-zinc-400">
    {mindmapGenerationProgress.detail || "正在生成系列思维导图"}
    <span className="mx-2 text-stone-300 dark:text-zinc-600">·</span>
    <span className="font-medium text-stone-700 dark:text-zinc-200">
      已用 {Math.round(mindmapGenerationProgress.elapsed_seconds ?? 0)} 秒
    </span>
  </p>
</div>
```

NOTE: `LoaderCircle` is already imported in this file. No new imports.

- [ ] **Step 2: Update the series progress tests**

Read `tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx`. Find the `describe("WorkspaceSeriesMindmapView — progress bar", ...)` block. Replace it with:

```jsx
describe("WorkspaceSeriesMindmapView — elapsed time progress", () => {
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

  it("shows elapsed time during generation", () => {
    render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 30,
          detail: "正在生成系列思维导图", elapsed_seconds: 12,
        }}
      />
    );
    expect(screen.getByText("正在生成系列思维导图")).toBeTruthy();
    expect(screen.getByText("已用 12 秒")).toBeTruthy();
  });

  it("shows updated elapsed time on rerender", () => {
    const { rerender } = render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 30,
          detail: "正在生成系列思维导图", elapsed_seconds: 12,
        }}
      />
    );
    expect(screen.getByText("已用 12 秒")).toBeTruthy();

    rerender(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 30,
          detail: "正在生成系列思维导图", elapsed_seconds: 18,
        }}
      />
    );
    expect(screen.getByText("已用 18 秒")).toBeTruthy();
  });

  it("does not show percentage during generation", () => {
    render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 30,
          detail: "正在生成系列思维导图", elapsed_seconds: 12,
        }}
      />
    );
    expect(screen.queryByText("30%")).toBeNull();
  });

  it("hides progress on completion", () => {
    render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={false}
        seriesMindmap={{ id: "root", title: "Test", children: [] }}
        mindmapGenerationProgress={null}
      />
    );
    expect(screen.queryByText(/已用.*秒/)).toBeNull();
  });
});
```

- [ ] **Step 3: Run all frontend tests**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/
```
Expected: all existing tests PASS + 4 new series tests PASS = around 120 tests total

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
git commit -m "feat(mindmap-progress): replace series progress bar with elapsed-time spinner"
```

---

## Task 3: Final verification

- [ ] **Step 1: Run all frontend tests**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/
```
Expected: 119/119 tests PASS (116 existing + 3 new from this change since the original 5 progress tests were replaced: 3 single + 2 series → 4 + 4 = 8 new total)

- [ ] **Step 2: Verify backend is untouched**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/ -q
```
Expected: 27/27 tests PASS (no backend changes)

- [ ] **Step 3: Commit (if any final tweaks)**

```bash
git add -A
git commit -m "chore(mindmap-progress): final verification — frontend tests + backend regression"
```
