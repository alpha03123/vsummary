# markmap Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CSS-tree `MindmapCanvas` with markmap's SVG-based interactive mindmap (zoom/pan/collapse/toolbar).

**Architecture:** Frontend-only rewrite of 1 component. `MindmapCanvas.jsx` becomes a thin wrapper around `Markmap.create()`. Data adapter converts `MindmapNodePayload` → `markmap INode`. View components unchanged. 3 npm deps added.

**Tech Stack:** React 19, markmap-view 0.18, markmap-toolbar 0.18, d3 7.9, Vitest

---

## File Structure

### Created (1)
| File | Purpose |
|------|---------|
| `tests/frontend/features/workspace/ui/MindmapCanvas.test.jsx` | New unit tests for markmap integration |

### Modified (4)
| File | Change |
|------|--------|
| `src/frontend/src/features/workspace/ui/MindmapCanvas.jsx` | Full rewrite: CSS tree → markmap SVG |
| `src/frontend/src/styles.css` | Remove orphaned `.css-tree` CSS (lines 522-617) |
| `tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx` | Add `vi.mock('markmap-view')` |
| `tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx` | Add `vi.mock('markmap-view')` |

### Package dependency
```bash
npm install markmap-view markmap-toolbar d3
```

---

## Task 1: Install dependencies + create MindmapCanvas test

**Files:**
- Install: `markmap-view`, `markmap-toolbar`, `d3`
- Create: `tests/frontend/features/workspace/ui/MindmapCanvas.test.jsx`

- [ ] **Step 1: Install npm dependencies**

```bash
cd src/frontend && npm install markmap-view markmap-toolbar d3
```

- [ ] **Step 2: Create failing test file**

```jsx
// tests/frontend/features/workspace/ui/MindmapCanvas.test.jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock markmap before importing the component
vi.mock("markmap-view", () => ({
  Markmap: {
    create: vi.fn(() => ({
      destroy: vi.fn(),
      svg: { node: vi.fn(() => ({ classList: { add: vi.fn() } })) },
    })),
  },
}));
vi.mock("markmap-toolbar", () => ({
  Toolbar: {
    create: vi.fn(() => ({ el: document.createElement("div") })),
  },
}));
vi.mock("d3", () => ({
  default: {
    select: vi.fn(() => ({
      on: vi.fn(),
      datum: vi.fn(),
      node: vi.fn(() => ({ classList: { add: vi.fn(), remove: vi.fn() } })),
    })),
  },
}));

import { MindmapCanvas } from "@src/features/workspace/ui/MindmapCanvas";
import { Markmap } from "markmap-view";
import { Toolbar } from "markmap-toolbar";

const fakeRoot = {
  id: "root",
  title: "测试导图",
  summary: "",
  start_seconds: 0,
  end_seconds: 0,
  children: [
    {
      id: "c1",
      title: "子节点1",
      summary: "",
      start_seconds: 0,
      end_seconds: 0,
      children: [],
    },
  ],
};

describe("MindmapCanvas — markmap integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders SVG when root is provided", () => {
    const { container } = render(
      <MindmapCanvas root={fakeRoot} selectedNodeId={null} onSelectNode={vi.fn()} />
    );
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    expect(Markmap.create).toHaveBeenCalledTimes(1);
    expect(Toolbar.create).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when root is null", () => {
    const { container } = render(
      <MindmapCanvas root={null} selectedNodeId={null} onSelectNode={vi.fn()} />
    );
    expect(container.querySelector("svg")).toBeNull();
    expect(Markmap.create).not.toHaveBeenCalled();
  });

  it("destroys and recreates markmap when root changes", () => {
    const destroy = vi.fn();
    (Markmap.create as any).mockReturnValue({
      destroy,
      svg: { node: vi.fn(() => ({ classList: { add: vi.fn() } })) },
    });

    const { rerender } = render(
      <MindmapCanvas root={fakeRoot} selectedNodeId={null} onSelectNode={vi.fn()} />
    );
    expect(Markmap.create).toHaveBeenCalledTimes(1);

    rerender(
      <MindmapCanvas root={{ ...fakeRoot, title: "新导图" }} selectedNodeId={null} onSelectNode={vi.fn()} />
    );
    expect(destroy).toHaveBeenCalled();
    expect(Markmap.create).toHaveBeenCalledTimes(2);
  });

  it("attaches toolbar when root is provided", () => {
    const parentEl = document.createElement("div");
    const toolbarEl = document.createElement("div");
    toolbarEl.classList.add("markmap-toolbar");
    (Toolbar.create as any).mockReturnValue({ el: toolbarEl });

    render(
      <div>
        <MindmapCanvas root={fakeRoot} selectedNodeId={null} onSelectNode={vi.fn()} />
      </div>
    );
    expect(Toolbar.create).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/MindmapCanvas.test.jsx
```
Expected: FAIL — tests expect SVG but old `MindmapCanvas.jsx` renders div with CSS tree

- [ ] **Step 4: Commit**

```bash
git add src/frontend/package.json src/frontend/package-lock.json tests/frontend/features/workspace/ui/MindmapCanvas.test.jsx
git commit -m "chore(mindmap-markmap): install markmap-view/markmap-toolbar/d3, add failing tests"
```

---

## Task 2: Rewrite MindmapCanvas.jsx with markmap

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/MindmapCanvas.jsx`
- Modify: `src/frontend/src/styles.css`

- [ ] **Step 1: Rewrite MindmapCanvas.jsx**

Replace the entire file content:

```jsx
import { useEffect, useRef } from "react";
import { Markmap } from "markmap-view";
import { Toolbar } from "markmap-toolbar";
import * as d3 from "d3";

export function MindmapCanvas({ root, selectedNodeId, onSelectNode }) {
  const svgRef = useRef(null);
  const mmRef = useRef(null);
  const toolbarRef = useRef(null);

  useEffect(() => {
    if (!root || !svgRef.current) {
      // Cleanup when root becomes null
      mmRef.current?.destroy();
      mmRef.current = null;
      toolbarRef.current?.remove();
      toolbarRef.current = null;
      return;
    }

    // Destroy previous instance
    mmRef.current?.destroy();
    toolbarRef.current?.remove();

    const data = convertToMarkmapNode(root);
    const mm = Markmap.create(svgRef.current, null, data);
    mmRef.current = mm;

    // Attach toolbar
    const toolbar = Toolbar.create(mm);
    toolbar.el.setAttribute("style", "position:absolute;bottom:20px;right:20px");
    svgRef.current.parentElement?.appendChild(toolbar.el);
    toolbarRef.current = toolbar.el;

    // Wire onClick via d3 delegation
    d3.select(svgRef.current).on("click", (event) => {
      const target = event.target.closest(".markmap-node");
      if (!target || !onSelectNode) return;
      const nodeData = d3.select(target).datum();
      if (!nodeData) return;
      onSelectNode({
        id: nodeData.payload?.id,
        title: nodeData.content,
        summary: nodeData.payload?.summary,
        start_seconds: nodeData.payload?.startSeconds ?? 0,
        end_seconds: nodeData.payload?.endSeconds ?? 0,
        children: nodeData.children || [],
      });
    });

    return () => {
      toolbarRef.current?.remove();
      toolbarRef.current = null;
      mm.destroy();
      mmRef.current = null;
    };
  }, [root]);

  // Sync dark mode with app's html.dark class
  useEffect(() => {
    const svg = mmRef.current?.svg?.node();
    if (!svg || !root) return;
    if (document.documentElement.classList.contains("dark")) {
      svg.classList.add("markmap-dark");
    } else {
      svg.classList.remove("markmap-dark");
    }
  }, [root]);

  // Highlight selected node
  useEffect(() => {
    if (!svgRef.current || !selectedNodeId) return;
    const svg = svgRef.current;
    svg.querySelectorAll(".mindmap-selected").forEach((el) =>
      el.classList.remove("mindmap-selected")
    );
    svg.querySelectorAll("g.markmap-node").forEach((g) => {
      const data = g.__data__;
      if (data?.payload?.id === selectedNodeId) {
        g.classList.add("mindmap-selected");
      }
    });
  }, [selectedNodeId, root]);

  if (!root) {
    return (
      <div className="p-8 text-stone-500 text-sm text-center">
        当前没有导图数据。
      </div>
    );
  }

  return (
    <svg
      ref={svgRef}
      className="absolute inset-0 w-full h-full"
      style={{ background: "transparent" }}
    />
  );
}

/** Convert MindmapNodePayload tree → markmap INode tree */
function convertToMarkmapNode(node) {
  return {
    content: node.title,
    payload: {
      id: node.id,
      summary: node.summary,
      startSeconds: node.start_seconds,
      endSeconds: node.end_seconds,
    },
    children: (node.children || []).map(convertToMarkmapNode),
  };
}
```

- [ ] **Step 2: Clean up orphaned CSS**

Read `src/frontend/src/styles.css` around lines 522-617. Find and delete all `.css-tree` related CSS rules (the CSS tree connector line pseudo-elements, `.css-tree ul`, `.css-tree li`, and `.css-tree-node-wrapper` blocks).

Add the new `.mindmap-selected` highlight rule:

```css
.mindmap-selected > circle {
  stroke: var(--color-accent, #3b82f6);
  stroke-width: 3;
}
```

- [ ] **Step 3: Run tests — verify they pass**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/MindmapCanvas.test.jsx
```
Expected: 4 PASS (svg renders, null renders nothing, root changes destroy+recreate, toolbar attached)

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/workspace/ui/MindmapCanvas.jsx src/frontend/src/styles.css
git commit -m "feat(mindmap-markmap): rewrite MindmapCanvas with markmap SVG rendering"
```

---

## Task 3: Update existing view tests with markmap mocks

**Files:**
- Modify: `tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx`
- Modify: `tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx`

- [ ] **Step 1: Add mocks to WorkspaceMindmapView.test.jsx**

Read the file. Find the imports near the top (after the vitest imports). Add BEFORE the component import:

```jsx
vi.mock("markmap-view", () => ({
  Markmap: {
    create: vi.fn(() => ({
      destroy: vi.fn(),
      svg: { node: vi.fn(() => ({ classList: { add: vi.fn(), remove: vi.fn() } })) },
    })),
  },
}));
vi.mock("markmap-toolbar", () => ({
  Toolbar: {
    create: vi.fn(() => ({ el: document.createElement("div") })),
  },
}));
vi.mock("d3", () => ({
  default: {
    select: vi.fn(() => ({
      on: vi.fn(),
      datum: vi.fn(),
      node: vi.fn(() => ({ classList: { add: vi.fn(), remove: vi.fn() } })),
    })),
  },
}));
```

NOTE: These mocks MUST come before the `import { WorkspaceMindmapView } from ...` line, because that import triggers `MindmapCanvas` import chain which loads markmap.

- [ ] **Step 2: Add same mocks to WorkspaceSeriesMindmapView.test.jsx**

Read the file. Add the exact same 3 `vi.mock(...)` blocks before the component import.

- [ ] **Step 3: Run all frontend tests**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/ 2>&1 | tail -10
```
Expected: 121/121 tests pass (119 existing + 2 new — wait, actually: 119 existing - 3 from old MindmapCanvas if any + 4 new = ~120. Check output.)

- [ ] **Step 4: Commit**

```bash
git add tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
git commit -m "test(mindmap-markmap): add markmap mocks to existing view tests"
```

---

## Task 4: Final verification

- [ ] **Step 1: Run all tests**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/ 2>&1 | tail -10
```
Expected: all tests PASS

```bash
cd E:\Project\surmmervay\vsummary-gpu && PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/ -q
```
Expected: 27/27 PASS (backend unchanged)

- [ ] **Step 2: Visual verification (manual)**

```bash
cd src/frontend && npm run dev
```
Open `http://127.0.0.1:4173`, navigate to a video with mindmap data. Verify:
- SVG mindmap renders (not CSS tree)
- Scroll-zoom works
- Nodes with children collapse/expand on click
- Toolbar visible in bottom-right
- Dark mode toggle respected
- Clicking a node fires `onFocusNode` (check chapter scroll)

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore(mindmap-markmap): final verification — all tests pass"
```
