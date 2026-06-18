# Mindmap Multi-Format Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add HTML and PNG mindmap export formats alongside existing Markdown, with a dropdown menu replacing the single export button.

**Architecture:** Backend adds `render_mindmap_html()` generating a self-contained markmap HTML page. Frontend converts SVG to PNG using native DOM API (no dependencies). Export button becomes a dropdown offering MD / HTML / PNG.

**Tech Stack:** Python 3.12, FastAPI, React 19, native DOM API (XMLSerializer + canvas)

---

## File Structure

### Modified (7)
| # | File | Change |
|---|------|--------|
| 1 | `src/backend/video_summary/infrastructure/mindmap_export.py` | Add `render_mindmap_html()` |
| 2 | `src/backend/api/routes/videos.py` | Expand format validation to "md"/"html" |
| 3 | `src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx` | Replace `<a>` with dropdown |
| 4 | `src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx` | Same dropdown |
| 5 | `tests/backend/unit/mindmap/test_mindmap_export.py` | Add HTML export tests |
| 6 | `tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx` | Update export tests |
| 7 | `tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx` | Update export tests |

### 0 new files, 0 new npm dependencies

---

## Task 1: Backend — add HTML export + update format validation

**Files:**
- Modify: `src/backend/video_summary/infrastructure/mindmap_export.py`
- Modify: `src/backend/api/routes/videos.py`
- Modify: `tests/backend/unit/mindmap/test_mindmap_export.py`

- [ ] **Step 1: Write failing HTML export tests**

Add to `tests/backend/unit/mindmap/test_mindmap_export.py`:

```python
class MindmapHtmlExportTests(unittest.TestCase):
    def test_html_export_renders_valid_html(self):
        from backend.video_summary.infrastructure.mindmap_export import render_mindmap_html
        node = {"id": "root", "title": "测试", "summary": "", "children": []}
        result = render_mindmap_html(node, "测试视频")
        self.assertTrue(result.startswith("<!doctype html>"))
        self.assertIn("markmap-view", result)
        self.assertIn("测试", result)

    def test_html_export_embeds_mindmap_data(self):
        from backend.video_summary.infrastructure.mindmap_export import render_mindmap_html
        node = {"id": "root", "title": "测试视频", "summary": "摘要", "children": []}
        result = render_mindmap_html(node, "测试视频")
        self.assertIn('"title":"测试视频"', result)

    def test_html_export_handles_nested_children(self):
        from backend.video_summary.infrastructure.mindmap_export import render_mindmap_html
        node = {"id": "root", "title": "根", "summary": "", "children": [
            {"id": "c1", "title": "子1", "summary": "", "children": []}
        ]}
        result = render_mindmap_html(node, "根")
        self.assertIn('"title":"子1"', result)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_mindmap_export.py::MindmapHtmlExportTests -v
```
Expected: FAIL — `render_mindmap_html` not defined

- [ ] **Step 3: Implement `render_mindmap_html()`**

Add to `src/backend/video_summary/infrastructure/mindmap_export.py`:

```python
import json


def render_mindmap_html(node: dict, title: str = "Mindmap") -> str:
    """Generate a self-contained HTML page with markmap rendering.
    
    Embeds the mindmap data as JSON and loads markmap-view/markmap-toolbar/d3
    from unpkg CDN. The result is a standalone HTML file the user can open
    in any browser to explore the interactive mindmap.
    """
    data_json = json.dumps(node, ensure_ascii=False)
    return f"""<!doctype html>
<html>
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; }}
#mindmap {{ display: block; width: 100vw; height: 100vh; }}
.markmap-dark {{ background: #27272a; color: white; }}
</style>
<link rel="stylesheet" href="https://unpkg.com/markmap-toolbar@0.18.12/dist/style.css" />
</head>
<body>
<svg id="mindmap"></svg>
<script src="https://unpkg.com/d3@7.9.0/dist/d3.min.js"></script>
<script src="https://unpkg.com/markmap-view@0.18.12/dist/browser/index.js"></script>
<script src="https://unpkg.com/markmap-toolbar@0.18.12/dist/index.js"></script>
<script>
const root = {data_json};
const mm = window.markmap.Markmap.create("svg#mindmap", null, root);
window.markmap.Toolbar.create(mm);
if (window.matchMedia("(prefers-color-scheme: dark)").matches) {{
  document.documentElement.classList.add("markmap-dark");
}}
</script>
</body>
</html>"""
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_mindmap_export.py::MindmapHtmlExportTests -v
```
Expected: 3 PASS

- [ ] **Step 5: Update API routes to accept "html" format**

In `src/backend/api/routes/videos.py`, find the export endpoints. Change the format check from `format != "md"` to `format not in ("md", "html")`:

In `export_video_mindmap` (around line 291):
```python
    if format not in ("md", "html"):
```
In `export_series_mindmap` (around line 910):
```python
    if format not in ("md", "html"):
```

Also update the render call to dispatch by format:
```python
    if format == "html":
        content = render_mindmap_html(video_mindmap.mindmap, video_mindmap.title)
        filename = f"{video_mindmap.title}-mindmap.html"
        return _html_response(content, filename)
    markdown = render_mindmap_markdown(video_mindmap.mindmap)
    filename = f"{video_mindmap.title}-mindmap.md"
    return _markdown_response(markdown, filename)
```

Add `_html_response` helper near `_markdown_response`:
```python
def _html_response(html: str, filename: str) -> Response:
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": _content_disposition_attachment(filename)},
    )
```

Also add import at top: `from backend.video_summary.infrastructure.mindmap_export import render_mindmap_markdown, render_mindmap_html` (replace the existing import which only has `render_mindmap_markdown`).

Apply same changes to the series export endpoint in the same file (around line 910).

- [ ] **Step 6: Run all mindmap tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/ -v
```
Expected: 30 PASS (27 + 3 new HTML tests)

- [ ] **Step 7: Commit**

```bash
git add src/backend/video_summary/infrastructure/mindmap_export.py src/backend/api/routes/videos.py tests/backend/unit/mindmap/test_mindmap_export.py
git commit -m "feat(mindmap-export): add HTML format export — standalone markmap page"
```

---

## Task 2: Frontend — Export dropdown component + PNG handler

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx`
- Modify: `src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx`
- Modify: `tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx`
- Modify: `tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx`

- [ ] **Step 1: Read current WorkspaceMindmapView.jsx to locate the export button**

The export button is at lines 107-114: a single `<a download href={...format=md}>导出</a>`. Replace it with a dropdown.

- [ ] **Step 2: Add `useState` import and dropdown state**

Add `useState` to the React import at top of `WorkspaceMindmapView.jsx`:
```jsx
import { useState } from "react";
```
Already imported: `useLoaderCircle, Network, Download, RefreshCw` — keep them.

Add state near the top of the component function (before the first `if` guard):
```jsx
const [exportOpen, setExportOpen] = useState(false);
```

- [ ] **Step 3: Replace the export `<a>` link with a dropdown menu**

Replace lines 107-114:
```jsx
        <a
          href={`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap/export?format=md`}
          download
          className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors"
        >
          <Download size={14} strokeWidth={2} />
          导出
        </a>
```

With:
```jsx
        <div className="relative">
          <button
            type="button"
            onClick={() => setExportOpen(!exportOpen)}
            className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors"
          >
            <Download size={14} strokeWidth={2} />
            导出
          </button>
          {exportOpen && (
            <div className="absolute right-0 top-full mt-1 z-20 rounded-xl border border-stone-200 bg-white dark:bg-neutral-900 shadow-lg py-1 min-w-[120px]">
              <a
                href={`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap/export?format=md`}
                download
                className="block px-4 py-2 text-xs text-stone-700 dark:text-zinc-300 hover:bg-stone-50 dark:hover:bg-neutral-800"
                onClick={() => setExportOpen(false)}
              >
                Markdown (.md)
              </a>
              <a
                href={`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap/export?format=html`}
                download
                className="block px-4 py-2 text-xs text-stone-700 dark:text-zinc-300 hover:bg-stone-50 dark:hover:bg-neutral-800"
                onClick={() => setExportOpen(false)}
              >
                HTML (.html)
              </a>
              <button
                type="button"
                className="block w-full text-left px-4 py-2 text-xs text-stone-700 dark:text-zinc-300 hover:bg-stone-50 dark:hover:bg-neutral-800"
                onClick={() => {
                  setExportOpen(false);
                  handleExportPNG(`mindmap-${videoId}.png`);
                }}
              >
                PNG (.png)
              </button>
            </div>
          )}
        </div>
```

- [ ] **Step 4: Add PNG export handler**

Add `handleExportPNG` function inside the component (before the `return`):
```jsx
function handleExportPNG(filename) {
  const svgEl = document.querySelector("#mindmap svg, .workspace-elevated-panel svg");
  if (!svgEl) return;
  const svgData = new XMLSerializer().serializeToString(svgEl);
  const canvas = document.createElement("canvas");
  canvas.width = svgEl.clientWidth * 2;
  canvas.height = svgEl.clientHeight * 2;
  const ctx = canvas.getContext("2d");
  ctx.scale(2, 2);
  const img = new Image();
  img.onload = () => {
    ctx.fillStyle = getComputedStyle(svgEl).backgroundColor || "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    const a = document.createElement("a");
    a.download = filename;
    a.href = canvas.toDataURL("image/png");
    a.click();
  };
  img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(svgData)));
}
```

Note: The SVG selector `#mindmap svg` targets the markmap SVG element. The fallback `.workspace-elevated-panel svg` catches the series view (which doesn't have `#mindmap` wrapper).

- [ ] **Step 5: Apply same changes to WorkspaceSeriesMindmapView.jsx**

Find the export `<a>` link (lines 100-107). Replace with the same dropdown, but change the URLs to use `/api/series/` path:

```jsx
        <div className="relative">
          <button
            type="button"
            onClick={() => setExportOpen(!exportOpen)}
            className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors"
          >
            <Download size={14} strokeWidth={2} />
            导出
          </button>
          {exportOpen && (
            <div className="absolute right-0 top-full mt-1 z-20 rounded-xl border border-stone-200 bg-white dark:bg-neutral-900 shadow-lg py-1 min-w-[120px]">
              <a
                href={`/api/series/${encodeURIComponent(seriesId)}/mindmap/export?format=md`}
                download
                className="block px-4 py-2 text-xs text-stone-700 dark:text-zinc-300 hover:bg-stone-50 dark:hover:bg-neutral-800"
                onClick={() => setExportOpen(false)}
              >
                Markdown (.md)
              </a>
              <a
                href={`/api/series/${encodeURIComponent(seriesId)}/mindmap/export?format=html`}
                download
                className="block px-4 py-2 text-xs text-stone-700 dark:text-zinc-300 hover:bg-stone-50 dark:hover:bg-neutral-800"
                onClick={() => setExportOpen(false)}
              >
                HTML (.html)
              </a>
              <button
                type="button"
                className="block w-full text-left px-4 py-2 text-xs text-stone-700 dark:text-zinc-300 hover:bg-stone-50 dark:hover:bg-neutral-800"
                onClick={() => {
                  setExportOpen(false);
                  handleExportPNG(`series-mindmap-${seriesId}.png`);
                }}
              >
                PNG (.png)
              </button>
            </div>
          )}
        </div>
```

Also add `useState` import and `handleExportPNG` function (same as in single-video view).

- [ ] **Step 6: Update frontend tests**

In `tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx`, update the existing export button tests:

Find the old `describe("WorkspaceMindmapView — export button", ...)` block. Update the 2 tests to check for the dropdown instead of a single link:

```jsx
describe("WorkspaceMindmapView — export dropdown", () => {
  const baseProps = {
    tools: makeTools({ generated: true }),
    mindmap: fakeMindmap, selectedNode: null, mindmapLoading: false,
    isGeneratingMindmapSelectedVideo: false,
    onFocusNode: vi.fn(), onGenerateMindmap: vi.fn(),
    seriesId: "s1", videoId: "v1", mindmapGenerationProgress: null,
  };

  it("shows export button when mindmap is generated", () => {
    render(<WorkspaceMindmapView {...baseProps} />);
    expect(screen.getByText("导出")).toBeTruthy();
  });

  it("hides export button when mindmap not generated", () => {
    render(<WorkspaceMindmapView {...baseProps} tools={makeTools({ generated: false })} mindmap={null} />);
    expect(screen.queryByText("导出")).toBeNull();
  });
});
```

In `tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx`, the existing export button test is inside `describe("WorkspaceSeriesMindmapView", ...)`. Update the assertion in `test_shows_regenerate_and_export_buttons_when_mindmap_exists` to still check for "导出" button text (same assertion, just the underlying HTML structure changed).

- [ ] **Step 7: Run frontend tests**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/
```
Expected: 123/123 tests PASS (no regressions)

- [ ] **Step 8: Commit**

```bash
git add src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx tests/frontend/features/workspace/ui/views/WorkspaceMindmapView.test.jsx tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
git commit -m "feat(mindmap-export): add HTML/PNG export + dropdown menu replacing single button"
```

---

## Task 3: Final verification

- [ ] **Step 1: Run all tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/ -v  # Expected: 30 PASS
cd src/frontend && npx vitest run tests/frontend/features/workspace/  # Expected: 123 PASS
```

- [ ] **Step 2: Commit (if any final tweaks)**

```bash
git add -A
git commit -m "chore(mindmap-export): final verification — 30 backend + 123 frontend"
```
