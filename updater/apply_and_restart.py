"""在应用进程退出后应用 Pack delta 并启动新版本。"""

from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import subprocess
import time

if __package__:
    from .update import apply_prepared_update, run_update
else:
    from update import apply_prepared_update, run_update


def apply_and_restart(*, root: Path, wait_for_pid: int, variant: str | None = None, prepared: bool = False) -> int:
    """等待旧服务退出，复用事务更新器应用 delta，成功后启动 Pack。"""
    try:
        if not _wait_for_process_exit(wait_for_pid, timeout_seconds=180):
            raise RuntimeError("Timed out waiting for the running application to exit.")
        result = apply_prepared_update(root) if prepared else run_update(root=root, variant=variant)
        for message in result.messages:
            print(message, flush=True)
        return 2 if result.requires_full_package else 0
    finally:
        _restart_pack(root)


def _wait_for_process_exit(pid: int, *, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_process_running(pid):
            return True
        time.sleep(0.25)
    return False


def _is_process_running(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    kernel32 = ctypes.windll.kernel32
    process = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not process:
        return False
    try:
        return kernel32.WaitForSingleObject(process, 0) == 258  # WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(process)


def _restart_pack(root: Path) -> None:
    start_script = root / "start.bat"
    if not start_script.is_file():
        raise RuntimeError(f"Pack start script not found: {start_script}")
    subprocess.Popen(
        ["cmd.exe", "/c", "start", "", str(start_script)],
        cwd=root,
        close_fds=True,
        creationflags=_background_process_flags(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _background_process_flags() -> int:
    return (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a pending vsummary Pack update and restart.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--wait-for-pid", type=int, required=True)
    parser.add_argument("--variant", choices=("cpu", "gpu"), default=None)
    parser.add_argument("--prepared", action="store_true")
    args = parser.parse_args()
    try:
        return apply_and_restart(root=args.root.resolve(), wait_for_pid=args.wait_for_pid, variant=args.variant, prepared=args.prepared)
    except KeyboardInterrupt:
        print("Update interrupted before completion.", flush=True)
        return 130
    except Exception as error:
        print(f"Update failed: {error}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
