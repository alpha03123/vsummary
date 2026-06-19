from __future__ import annotations

import json


def render_mindmap_markdown(node: dict, depth: int = 0) -> str:
    """Recursively render a mindmap node tree as Markdown nested list."""
    indent = "  " * depth
    title = node.get("title", "")
    summary = node.get("summary", "")
    lines = [f"{indent}- **{title}**"]
    if summary:
        lines.append(f"{indent}  {summary}")
    children = node.get("children", []) or []
    for child in children:
        lines.append(render_mindmap_markdown(child, depth + 1))
    return "\n".join(lines)


def render_mindmap_html(node: dict, title: str = "Mindmap") -> str:
    """Generate a self-contained HTML page with markmap rendering.

    Transforms MindmapNodePayload (title/children) to markmap INode
    (content/children) before embedding, matching the frontend's
    convertToMarkmapNode() logic.
    """
    markmap_data = _convert_to_markmap_data(node)
    data_json = json.dumps(markmap_data, ensure_ascii=False)
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


def _convert_to_markmap_data(node: dict) -> dict:
    """Transform MindmapNodePayload → markmap INode.

    markmap requires {content, children} format; our source uses
    {title, children}. We preserve id/summary/start/end in payload
    for potential use, matching MindmapCanvas.convertToMarkmapNode().
    """
    return {
        "content": node.get("title", ""),
        "payload": {
            "id": node.get("id"),
            "summary": node.get("summary", ""),
            "start_seconds": node.get("start_seconds", 0.0),
            "end_seconds": node.get("end_seconds", 0.0),
        },
        "children": [
            _convert_to_markmap_data(child)
            for child in (node.get("children") or [])
        ],
    }
