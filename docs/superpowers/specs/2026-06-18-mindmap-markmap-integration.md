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
| `markmap-view` | ^0.18 | SVG mindmap renderer (includes d3 internally) |
| `markmap-toolbar` | ^0.18 | Zoom/fit/reset toolbar |

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

    // Wire onClick via d3 delegation
    import * as d3 from 'd3';
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

    return () => mm.destroy();
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
.markmap-node--highlight > circle {
  stroke: var(--color-accent, #3b82f6);
  stroke-width: 3;
}
```

Dark mode: markmap detects `prefers-color-scheme: dark` automatically (same as reference implementation). Your app's `dark:` Tailwind classes should work via the existing `html.dark` class on the root element.

### Selected Node Highlight

markmap doesn't natively support "selected node" state. Implementation approach:

Since `Markmap.create()` returns an instance with `d.data` at the root, we can traverse the internal d3 selection to find the matching node and add a CSS class:

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
  (new file — replaces old MindmapCanvas importer)
  ├── test_renders_svg_when_root_provided
  │     root with children → <svg> element present in DOM
  ├── test_onSelectNode_fires_on_click
  │     mock onSelectNode → click a node → called with node data
  ├── test_highlights_selectedNodeId
  │     selectedNodeId matches a node → node has .mindmap-selected class
  ├── test_clears_when_root_changes
  │     render with rootA → rerender with rootB → old SVG gone, new SVG present
  ├── test_renders_nothing_when_root_is_null
  │     root=null → no <svg> element

tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
  (modify existing — import markmap and mock)
  - Existing tests that render WorkspaceMindmapView will now need markmap mock
    because MindmapCanvas internally imports markmap-view

tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
  (same mock needed)
```

### markmap Mock Strategy

markmap-view requires a DOM environment with SVG support. For Vitest:

```jsx
// tests/frontend/__mocks__/markmap-view.js
export const Markmap = {
  create: vi.fn(() => ({
    destroy: vi.fn(),
    options: {},
  })),
};
```

Add to `src/frontend/vite.config.js` or `vitest.config.js`:
```js
resolve: {
  alias: [
    { find: 'markmap-view', replacement: '__mocks__/markmap-view.js' },
    { find: 'markmap-toolbar', replacement: '__mocks__/markmap-toolbar.js' },
  ]
}
```

## Scope

- 1 source file rewritten: `MindmapCanvas.jsx`
- 2 npm dependencies added: `markmap-view`, `markmap-toolbar`
- 2 mock files created (for tests)
- Existing view components unchanged
- 0 backend changes
