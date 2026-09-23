from __future__ import annotations

import asyncio
import importlib
import sys

def configure_event_loop_policy() -> None:
    """Configure the legacy entry module without owning Local composition."""

    if sys.platform != "win32":
        return
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy is not None:
        asyncio.set_event_loop_policy(selector_policy())


def main() -> None:
    """Retain the historical executable module while deferring to Local composition."""

    local_server = importlib.import_module("backend.local.http.server")
    local_server.main()


if __name__ == "__main__":
    main()
