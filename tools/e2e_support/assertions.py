"""Small reusable assertions for externally observable E2E artifacts."""

from __future__ import annotations


def require_generated_tools(tools: dict[str, object], *names: str) -> None:
    for name in names:
        value = tools.get(name)
        if not isinstance(value, dict) or value.get("generated") is not True:
            raise RuntimeError(f"Tool state is not ready: {name}")
