"""Pack 更新状态与受控重启调度。"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from threading import Lock, Thread
import time


RESTART_DELAY_SECONDS = 10
_schedule_lock = Lock()
_restart_scheduled = False


class ApplicationUpdateError(RuntimeError):
    """应用更新检查或调度失败。"""


def get_update_status(root: Path) -> dict[str, object]:
    """读取安装形态；仅 Pack 会访问远端 manifest。"""
    if not _is_pack_installation(root):
        return {
            "installation_kind": "source",
            "current_version": "v.Source",
            "variant": None,
            "update_available": False,
            "can_apply": False,
            "requires_full_package": False,
            "latest_version": None,
            "full_package_url": None,
            "message": "源码版不支持自动更新。",
        }

    try:
        check_for_update = _load_pack_updater(root)
        check = check_for_update(root)
    except Exception as error:
        raise ApplicationUpdateError(str(error)) from error
    return {
        "installation_kind": "pack",
        "current_version": check.current_version,
        "variant": check.variant,
        "update_available": check.update_available,
        "can_apply": check.can_apply,
        "requires_full_package": check.requires_full_package,
        "latest_version": check.target_version,
        "full_package_url": check.full_package_url,
        "message": " ".join(check.messages),
    }


def schedule_update(*, root: Path, variant: str, container: object) -> int:
    """启动独立更新器，随后在固定倒计时后退出当前后端。"""
    global _restart_scheduled
    if _has_active_tasks(container):
        raise ApplicationUpdateError("存在正在处理的任务，请完成或取消后再更新。")
    with _schedule_lock:
        if _restart_scheduled:
            raise ApplicationUpdateError("更新重启已经安排，请等待应用退出。")
        launcher_path = root / "updater" / "apply_and_restart.py"
        if not launcher_path.is_file():
            raise ApplicationUpdateError("Pack 更新启动器缺失，请下载完整安装包。")
        try:
            subprocess.Popen(
                [
                    sys.executable,
                    str(launcher_path),
                    "--root",
                    str(root),
                    "--wait-for-pid",
                    str(os.getpid()),
                    "--variant",
                    variant,
                ],
                cwd=root,
                close_fds=True,
            )
        except OSError as error:
            raise ApplicationUpdateError(f"无法启动更新器：{error}") from error
        _restart_scheduled = True
    Thread(target=_exit_after_delay, daemon=True).start()
    return RESTART_DELAY_SECONDS


def _is_pack_installation(root: Path) -> bool:
    return all(
        path.is_file()
        for path in (
            root / "VERSION",
            root / "updater" / "installed.json",
            root / "updater" / "config.json",
            root / "runtime" / "python.exe",
        )
    )


def _load_pack_updater(root: Path):
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    from updater.update import check_for_update

    return check_for_update


def _has_active_tasks(container: object) -> bool:
    tracker_names = (
        "generation_progress_tracker",
        "mindmap_progress_tracker",
        "video_download_progress_tracker",
        "model_download_progress_tracker",
        "chaoxing_import_progress_tracker",
        "knowledge_memory_progress_tracker",
    )
    trackers = [getattr(container, name, None) for name in tracker_names]
    rag_manager = getattr(container, "rag_model_manager", None)
    trackers.append(getattr(rag_manager, "progress_tracker", None))
    return any(getattr(tracker, "has_active_tasks", lambda: False)() for tracker in trackers if tracker is not None)


def _exit_after_delay() -> None:
    time.sleep(RESTART_DELAY_SECONDS)
    os._exit(0)
