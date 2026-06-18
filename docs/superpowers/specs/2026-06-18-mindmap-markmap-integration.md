# Mindmap — markmap Integration

2026-06-18 | Status: Design

## Overview

Replace the CSS-based tree visualization (`MindmapCanvas.jsx`) with [markmap](https://markmap.js.org/) — an SVG-based interactive mindmap library powered by d3.js. This brings zoom/pan/collapse capabilities matching the reference implementation at `计组思维导图v2.html`.

## Current State

`MindmapCanvas.jsx` renders a CSS `ul`/`li` tree with manual pan (pointer events) and wheel zoom. No SVG, no d3, no collapse/expand, no smooth transitions.

## Design

### Architecture

```
MindmapCanvas.jsx (rewritten)
  ├── markmap-view      (SVG rendering, d3 layout, zoom/pan)
  ├── markmap-toolbar   (optional toggle)
  └── convertToMarkmapNode()  (data adapter)
```

**Backend:** 0 changes. `MindmapNodePayload` schema unchanged. `mindmap.json` unchanged.

**Frontend files modified (1):**

| File | Change |
|------|--------|
| `src/frontend/src/features/workspace/ui/MindmapCanvas.jsx` | Rewrite: CSS tree → markmap SVG |

**No changes to:** `WorkspaceMindmapView.jsx`, `WorkspaceSeriesMindmapView.jsx`, `WorkspaceReadingPane.jsx` — they consume `MindmapCanvas` as a black box.

### New Dependencies

```bash
cd src/frontend
npm install markmap-view markmap-toolbar
```

| Package | Version | Purpose |
|---------|---------|---------|
| `markmap-view` | ^0.18 | SVG mindmap renderer |
| `markmap-toolbar` | ^0.18 | Zoom/fit/reset toolbar |
| `d3` | ^7.9 | Used for click delegation (`d3.select().datum()`) |

### Data Adapter

```typescript
// MindmapNodePayload → markmap INode
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

### Component API (unchanged)

```jsx
<MindmapCanvas
  root={mindmap}           // MindmapNodePayload tree
  selectedNodeId={id}      // string | null — highlights matching node
  onSelectNode={callback}  // (node) => void — fires onClick
/>
```

### Implementation Sketch

```jsx
import { useEffect, useRef } from "react";
import { Markmap } from "markmap-view";
import { Toolbar } from "markmap-toolbar";
import * as d3 from "d3";

export function MindmapCanvas({ root, selectedNodeId, onSelectNode }) {
  const svgRef = useRef(null);
  const mmRef = useRef(null);

  useEffect(() => {
    if (!root || !svgRef.current) return;

    // Destroy previous instance
    mmRef.current?.destroy();

    const data = convertToMarkmapNode(root);
    const mm = Markmap.create(svgRef.current, null, data);
    mmRef.current = mm;

    // Attach toolbar
    const toolbar = Toolbar.create(mm);
    toolbar.el.setAttribute('style', 'position:absolute;bottom:20px;right:20px');
    svgRef.current.parentElement?.appendChild(toolbar.el);

    // Wire onClick via d3 delegation (top-level import, not inside useEffect)
    d3.select(svgRef.current).on('click', (event) => {
      const target = event.target.closest('.markmap-node');
      if (!target || !onSelectNode) return;
      const data = d3.select(target).datum();
      if (!data) return;
      onSelectNode({
        id: data.payload?.id,
        title: data.content,
        summary: data.payload?.summary,
        start_seconds: data.payload?.startSeconds ?? 0,
        end_seconds: data.payload?.endSeconds ?? 0,
        children: data.children || [],
      });
    });

    return () => {
      toolbar.el.remove();
      mm.destroy();
    };
  }, [root]);

  // Highlight selected node by walking markmap's internal g elements
  useEffect(() => {
    if (!svgRef.current || !selectedNodeId) return;
    const svg = svgRef.current;
    svg.querySelectorAll('.mindmap-selected').forEach(el => el.classList.remove('mindmap-selected'));
    svg.querySelectorAll('g.markmap-node').forEach(g => {
      const data = g.__data__;
      if (data?.payload?.id === selectedNodeId) {
        g.classList.add('mindmap-selected');
      }
    });
  }, [selectedNodeId, root]);

  return <svg ref={svgRef} className="w-full h-full" />;
}
```

### Style Integration

markmap respects CSS custom properties for theming. Override via `src/frontend/src/styles.css`:

```css
.markmap-node > circle {
  fill: var(--color-accent, #3b82f6);
}
.mindmap-selected > circle {
  stroke: var(--color-accent, #3b82f6);
  stroke-width: 3;
}
```

**Dark mode:** markmap natively detects `prefers-color-scheme: dark` via a listener in `Markmap.create()`. However, the app controls dark mode via `html.dark` class. To sync:

```js
// In MindmapCanvas.jsx, useEffect after Markmap.create():
if (document.documentElement.classList.contains('dark')) {
  mm.svg.node()?.classList.add('markmap-dark');
}
```

Also delete orphaned `.css-tree` CSS rules from `styles.css` (lines 522-617).

### Trade-offs (Features Lost)

| Feature | Current | markmap | Accepted? |
|---------|---------|---------|-----------|
| Child count badge on nodes | `mindmap-badge` shows `node.children.length` | Not supported | Yes — markmap visually expands nodes, badge redundant |
| Double-click reset view | `onDoubleClick={resetView}` | Toolbar reset button instead | Yes |
| Custom zoom limits | `MIN_SCALE=0.55, MAX_SCALE=2.4` | markmap defaults (0.5–5.0) | Yes — acceptable range |
| `isPanning` cursor feedback | `cursor-grab`/`cursor-grabbing` | d3-zoom handles internally | Yes |
| CSS tree drawing connector lines | `.css-tree` pseudo-elements | markmap SVG connector lines | Yes — upgrade

### Implementation Notes

**Zoom/pan (M1.2) and collapse (M1.3):** Built into markmap via d3-zoom. No custom code needed — these are implicit behaviors of `Markmap.create()`.

**`__data__` fragility:** The `selectedNodeId` highlight uses `g.__data__`, which is d3's internal data binding property (private API). It is stable across minor versions but could break on a markmap major upgrade. Acceptable risk for now — refactor to markmap's public API if available later.

**Click interaction (M1.4):** Clicking a node both collapses/expands it (markmap default) AND fires `onSelectNode`. This is intentional — the collapse behavior is visual, the selection behavior feeds the parent component.

### Selected Node Highlight

markmap doesn't natively support "selected node" state. Walk SVG DOM to find matching node:

```jsx
useEffect(() => {
  if (!mmRef.current || !selectedNodeId) return;
  const svg = svgRef.current;
  // Clear previous
  svg.querySelectorAll('.mindmap-selected').forEach(el => {
    el.classList.remove('mindmap-selected');
  });
  // Walk markmap's internal g elements to find node with matching payload.id
  svg.querySelectorAll('g.markmap-node').forEach(g => {
    const data = g.__data__;
    if (data?.payload?.id === selectedNodeId) {
      g.classList.add('mindmap-selected');
    }
  });
}, [selectedNodeId, root]);
```

## Acceptance Criteria

| AC# | Condition |
|-----|-----------|
| M1.1 | `MindmapCanvas` renders SVG mindmap via markmap (not CSS tree) |
| M1.2 | Scroll-wheel zoom and drag-pan work |
| M1.3 | Nodes with children are collapsible (click to toggle) |
| M1.4 | `onSelectNode` fires with node data on click |
| M1.5 | `selectedNodeId` highlights matching node in SVG |
| M1.6 | `root` prop change destroys old instance and creates new one |
| M1.7 | WorkspaceMindmapView and WorkspaceSeriesMindmapView render unchanged |
| M1.8 | Markmap toolbar (zoom/fit/reset) visible in bottom-right corner |
| M1.9 | Dark mode respected (markmap auto-detects `prefers-color-scheme`) |

## Test Cases

```
tests/frontend/features/workspace/ui/MindmapCanvas.test.jsx
  (new file)
  ├── test_renders_svg_when_root_provided              [M1.1]
  │     root with children → <svg> element present in DOM
  ├── test_onSelectNode_fires_on_click                  [M1.4]
  │     mock onSelectNode → simulate click on .markmap-node → called with node data
  ├── test_highlights_selectedNodeId                    [M1.5]
  │     selectedNodeId matches a node → node has .mindmap-selected class
  ├── test_clears_when_root_changes                     [M1.6]
  │     render rootA → rerender rootB → old mm destroyed, new mm created
  ├── test_renders_nothing_when_root_is_null            [edge]
  │     root=null → no <svg> element
  ├── test_markmap_toolbar_attached                     [M1.8]
  │     root provided → Toolbar.create called; toolbar elements in DOM

tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
  (modify existing)
  - Add vi.mock('markmap-view') and vi.mock('markmap-toolbar')
  - Existing regenerate/export tests pass unchanged

tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
  (modify existing)
  - Add vi.mock('markmap-view') and vi.mock('markmap-toolbar')
```

**ACs implicitly covered by markmap built-in behavior (no test needed):**
- M1.2 (zoom/pan) — d3-zoom built into markmap
- M1.3 (collapse) — markmap circle-click toggles children natively
- M1.7 (views unchanged) — existing tests pass with mocks
- M1.9 (dark mode) — markmap auto-detects; verified by visual QA

### Mock Strategy

markmap-view requires a DOM + SVG environment. For Vitest, use `vi.mock()` in the test file:

```jsx
// In tests/frontend/features/workspace/ui/MindmapCanvas.test.jsx
vi.mock('markmap-view', () => ({
  Markmap: { create: vi.fn() },
}));
vi.mock('markmap-toolbar', () => ({
  Toolbar: { create: vi.fn(() => ({ el: document.createElement('div') })) },
}));
vi.mock('d3', () => ({
  select: vi.fn(() => ({ on: vi.fn(), datum: vi.fn() })),
}));
```

Also add these mocks to `WorkspaceMindmapView.test.jsx` and `WorkspaceSeriesMindmapView.test.jsx` (since they render `MindmapCanvas` which imports markmap).

## Scope

- 1 source file rewritten: `MindmapCanvas.jsx`
- 2 npm dependencies added: `markmap-view`, `markmap-toolbar`
- 2 mock files created (for tests)
- Existing view components unchanged
- 0 backend changes
