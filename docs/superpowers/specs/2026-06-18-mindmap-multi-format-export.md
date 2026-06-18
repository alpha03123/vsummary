# Mindmap Multi-Format Export

2026-06-18 | Status: Design

## Overview

Add HTML and PNG export formats to mindmap, replacing the single "导出" button with a dropdown menu offering MD / HTML / PNG options.

## Current State

- `GET /api/videos/{sid}/{vid}/mindmap/export?format=md` — Markdown download
- `GET /api/series/{sid}/mindmap/export?format=md` — same for series
- Frontend: single `<a download>` link pointing to the Markdown endpoint

## Design

### Backend: HTML Export

**New endpoint (same path, new format):**

`GET /api/videos/{sid}/{vid}/mindmap/export?format=html`  
`GET /api/series/{sid}/mindmap/export?format=html`

Generates a self-contained HTML file with:
- mindmap data embedded as JSON
- markmap-view + markmap-toolbar + d3 CDN scripts (unpkg, same as reference)
- Fullscreen SVG mindmap (100vw × 100vh)
- Dark mode auto-detection

**New file:** `src/backend/video_summary/infrastructure/mindmap_export.py` — add `render_mindmap_html(node: dict, title: str) -> str`.

### Frontend: PNG Export + Dropdown Menu

**PNG strategy:** Convert markmap SVG to PNG using the browser's native `XMLSerializer` + `<canvas>`. No external library needed — the SVG is already rendered in the DOM.

```javascript
function downloadPNG(svgEl, filename) {
  const svgData = new XMLSerializer().serializeToString(svgEl);
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const img = new Image();
  img.onload = () => {
    canvas.width = svgEl.clientWidth * 2;   // 2x retina
    canvas.height = svgEl.clientHeight * 2;
    ctx.scale(2, 2);
    ctx.fillStyle = '#ffffff';  // white background
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    const a = document.createElement('a');
    a.download = filename;
    a.href = canvas.toDataURL('image/png');
    a.click();
  };
  img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
}
```

**Export button → dropdown:** Replace single `<a download>` with a `<button>` + floating dropdown menu.

```jsx
<div className="relative">
  <button onClick={() => setExportOpen(!exportOpen)} className="...">
    <Download /> 导出
  </button>
  {exportOpen && (
    <div className="absolute right-0 top-full mt-1 rounded-xl border bg-white ...">
      <a href={`/api/videos/${sid}/${vid}/mindmap/export?format=md`} download>Markdown</a>
      <a href={`/api/videos/${sid}/${vid}/mindmap/export?format=html`} download>HTML</a>
      <button onClick={handlePNGExport}>PNG</button>
    </div>
  )}
</div>
```

### Files

| # | File | Change |
|---|------|--------|
| 1 | `infrastructure/mindmap_export.py` | Add `render_mindmap_html()` function |
| 2 | `api/routes/videos.py` | Change `format != "md"` check to `format not in {"md","html"}` |
| 3 | `ui/views/WorkspaceMindmapView.jsx` | Single `<a>` → dropdown with MD/HTML/PNG |
| 4 | `ui/views/WorkspaceSeriesMindmapView.jsx` | Same dropdown |
| 5 | `tests/backend/unit/mindmap/test_mindmap_export.py` | Add HTML export tests |

### Test Cases

```
tests/backend/unit/mindmap/test_mindmap_export.py
  ├── test_html_export_renders_valid_html
  │     render_mindmap_html(node) → starts with <!doctype html>
  ├── test_html_export_includes_mindmap_data
  │     output contains embedded JSON with node title
  ├── test_html_export_includes_markmap_scripts
  │     output contains markmap-view CDN URLs
  ├── test_export_endpoint_rejects_unsupported_format
  │     ?format=pdf → 400 (update: supports md, html only)

tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
  ├── test_export_dropdown_has_three_options
  │     MD, HTML, PNG all visible when dropdown open
```

## Acceptance Criteria

| AC# | Condition |
|-----|-----------|
| E1.1 | `format=html` exports self-contained HTML with embedded data |
| E1.2 | `format=md` still works unchanged |
| E1.3 | `format=pdf` returns 400 (was supported before, now explicitly rejected) |
| E1.4 | Frontend export button is a dropdown with MD / HTML / PNG |
| E1.5 | PNG uses browser SVG→canvas conversion, no external libs |
| E1.6 | Series mindmap supports same 3 formats |
| E1.7 | Dropdown closes on click-outside and on option select |

## Scope

- 1 backend file: add `render_mindmap_html()`
- 2 API routes: expand format check
- 2 frontend view files: dropdown UI + PNG handler
- 2 test files extended
- 0 new npm dependencies (PNG via native DOM API)
