from __future__ import annotations


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
