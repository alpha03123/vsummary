from __future__ import annotations

import asyncio
import argparse
import sys

import uvicorn


def configure_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy is None:
        return
    asyncio.set_event_loop_policy(selector_policy())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    configure_event_loop_policy()
    uvicorn.run("backend.api.http.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
