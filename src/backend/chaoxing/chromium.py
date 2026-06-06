from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from threading import Lock, Thread
from typing import Callable

from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker


CHAOXING_CHROMIUM_KEY = "chaoxing-chromium"


@dataclass(frozen=True)
class ChaoxingChromiumStatus:
    key: str
    label: str
    local_path: str
    purpose: str
    downloaded: bool
    status: str
    progress: float | None
    detail: str | None
    error: str | None


CommandRunner = Callable[[list[str], dict[str, str]], None]


class ChaoxingChromiumManager:
    def __init__(
        self,
        *,
        root_dir: Path,
        progress_tracker: InMemoryProgressTracker,
        command_runner: CommandRunner | None = None,
        run_in_background: bool = True,
    ) -> None:
        self._root_dir = root_dir
        self._browsers_dir = root_dir / "data" / "playwright-browsers"
        self._progress_tracker = progress_tracker
        self._command_runner = command_runner or _run_command
        self._run_in_background = run_in_background
        self._lock = Lock()
        self._active = False
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(self._browsers_dir)

    @property
    def progress_tracker(self) -> InMemoryProgressTracker:
        return self._progress_tracker

    @property
    def browsers_dir(self) -> Path:
        return self._browsers_dir

    def get_status(self) -> ChaoxingChromiumStatus:
        snapshot = self._progress_tracker.get_snapshot(self._task_id())
        return ChaoxingChromiumStatus(
            key=CHAOXING_CHROMIUM_KEY,
            label="Chromium内核",
            local_path=str(self._browsers_dir),
            purpose="用于chaoxing登录初始化登录",
            downloaded=self.is_downloaded(),
            status=snapshot.status,
            progress=snapshot.progress,
            detail=snapshot.detail,
            error=snapshot.error,
        )

    def is_downloaded(self) -> bool:
        if not self._browsers_dir.is_dir():
            return False
        return any(path.is_dir() and path.name.startswith("chromium-") for path in self._browsers_dir.iterdir())

    def start_download(self) -> ChaoxingChromiumStatus:
        if self.is_downloaded():
            return self.get_status()

        with self._lock:
            if self._active:
                return self.get_status()
            snapshot = self._progress_tracker.get_snapshot(self._task_id())
            if snapshot.status == "running":
                return self.get_status()
            self._active = True
            reporter = self._progress_tracker.create_reporter(self._task_id())
            reporter.update("download", 0.0, "正在下载超星 Chromium 浏览器内核")

        if self._run_in_background:
            Thread(target=self._run_download, args=(reporter,), daemon=True).start()
        else:
            self._run_download(reporter)
        return self.get_status()

    def stream_task_id(self) -> str:
        return self._task_id()

    def _run_download(self, reporter: ProgressReporter) -> None:
        try:
            if find_spec("playwright") is None:
                raise RuntimeError("当前 Python 环境缺少 playwright 包，请先安装项目依赖。")
            self._browsers_dir.mkdir(parents=True, exist_ok=True)
            reporter.update("download", None, "正在下载 Chromium 浏览器内核")
            self._command_runner(self._download_command(), self._download_env())
            reporter.update("validate", None, "正在校验 Chromium 浏览器内核")
            if not self.is_downloaded():
                raise RuntimeError("Chromium 下载完成但未找到 chromium-* 目录。")
            reporter.completed("超星 Chromium 浏览器内核已下载")
        except Exception as error:
            reporter.failed(str(error))
        finally:
            with self._lock:
                self._active = False

    def _download_command(self) -> list[str]:
        return [sys.executable, "-m", "playwright", "install", "chromium", "--no-shell"]

    def _download_env(self) -> dict[str, str]:
        return {
            **os.environ,
            "PLAYWRIGHT_BROWSERS_PATH": str(self._browsers_dir),
        }

    @staticmethod
    def _task_id() -> str:
        return f"chaoxing-chromium-download/{CHAOXING_CHROMIUM_KEY}"


def _run_command(command: list[str], env: dict[str, str]) -> None:
    result = subprocess.run(
        command,
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        return
    output = result.stdout.strip()
    detail = f"：{output}" if output else ""
    raise RuntimeError(f"Playwright Chromium 下载命令失败，退出码 {result.returncode}{detail}")
