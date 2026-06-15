"""视频总结生成的"配置感知"工作流包装与调试进度 reporter。

本模块包含两个组件：
- `ConfiguredVideoSummaryWorkflow`：把 `GenerateVideoSummary` 用例绑定到
  `config/settings.toml` 与 `.env`，配置变更时自动重建用例；
- `DebugFileProgressReporter`：当 `settings.debug.mode` 开启时，把每一次
  进度事件以 JSON Lines 形式追加到 `output_dir/debug.log`，便于本地排错。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from threading import Lock

from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.infrastructure.application_builders import build_video_summary_application


class ConfiguredVideoSummaryWorkflow:
    """对 `GenerateVideoSummary` 用例做"按配置缓存 + 自动失效"的轻量包装。

    业务场景：上层（API 路由 / 后台任务）触发单视频总结生成；本类负责把
    用例构建（LiteLLM 网关、转写器等）与 settings.toml/.env 解耦，避免
    每次调用都重建昂贵的资源，并保证配置变更后能立即生效。
    """

    def __init__(self, root_dir: Path) -> None:
        """记录项目根目录、配置文件路径与缓存状态。

        Args:
            root_dir: 项目根目录，用于解析 `config/settings.toml` 与 `.env`。
        """
        self._root_dir = root_dir
        self._config_path = root_dir / "config" / "settings.toml"
        self._dotenv_path = root_dir / ".env"
        self._application_lock = Lock()
        self._cached_signature: tuple[str, str, bool | None] | None = None
        self._cached_application = None

    async def run(
        self,
        source_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> None:
        """基于当前配置执行一次视频总结生成。

        当 `progress_reporter` 与 `application.settings.debug.mode` 同时满足时，
        会在调用下游用例前自动包一层 `DebugFileProgressReporter`，把事件
        落到 `output_dir/debug.log`。

        Args:
            source_path: 媒体源路径。
            output_dir: 总结制品的输出目录（`summary.json` 等）。
            progress_reporter: 可选的上层进度 reporter；为 `None` 时
                由下游用例自行创建。
            transcript_enhancement_enabled: 是否启用转写增强；为 `None`
                时由用例按默认配置决定。该参数参与缓存签名。
        """
        application = self._get_application(transcript_enhancement_enabled)
        resolved_progress_reporter = progress_reporter
        if progress_reporter is not None and application.settings.debug.mode:
            resolved_progress_reporter = DebugFileProgressReporter(
                wrapped=progress_reporter,
                log_path=output_dir / "debug.log",
            )
        await application.use_case.run(
            video_path=source_path,
            output_dir=output_dir,
            progress_reporter=resolved_progress_reporter,
        )

    def _get_application(self, transcript_enhancement_enabled: bool | None):
        """获取（必要时重建）用例。

        缓存键为 `(settings.toml 文本, .env 文本, transcript_enhancement_enabled)`，
        任意维度变更都会触发重建。并发安全由 `_application_lock` 串行化。
        """
        signature = (
            self._config_path.read_text(encoding="utf-8"),
            self._dotenv_path.read_text(encoding="utf-8") if self._dotenv_path.exists() else "",
            transcript_enhancement_enabled,
        )
        with self._application_lock:
            if self._cached_signature != signature or self._cached_application is None:
                self._cached_application = build_video_summary_application(
                    config_path=self._config_path,
                    root_dir=self._root_dir,
                    transcript_enhancement_enabled=transcript_enhancement_enabled,
                )
                self._cached_signature = signature
            return self._cached_application


class DebugFileProgressReporter:
    """把进度事件以 JSON Lines 形式落盘到 `log_path` 的调试 reporter。

    业务目的：在 debug 模式下记录每一次阶段切换、用时、详情，便于
    本地排查"为什么这次生成变慢了 / 卡在哪一步"。

    实现要点：
        - 包装一个下层 `ProgressReporter`，自身只追加日志并不阻断事件流；
        - 通过 `stage` 字符串比对感知阶段切换，切换时先闭合上一阶段
          的 `stage_completed` 事件再写 `stage_started`；
        - `update` 同一 `stage` 内的连续事件只写 `stage_progress`，避免日志膨胀。
    """

    def __init__(self, wrapped: ProgressReporter, log_path: Path) -> None:
        """记录下层 reporter、日志路径与开始时间，并落第一条 `run_started` 事件。

        Args:
            wrapped: 被包装的下层 `ProgressReporter`。
            log_path: 调试日志的输出文件路径；父目录不存在时会自动创建。
        """
        self._wrapped = wrapped
        self._log_path = log_path
        self._started_at = time.perf_counter()
        self._current_stage: str | None = None
        self._current_stage_started_at: float | None = None
        self._log("run_started", detail="开始生成 AI 概况")

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        """转发进度更新到下层 reporter，并把事件追加到调试日志。

        当 `stage` 相对上次发生变化时先闭合上一阶段，再写
        `stage_started`；同 `stage` 内只写 `stage_progress`。
        """
        now = time.perf_counter()
        if stage != self._current_stage:
            self._log_stage_completed(now)
            self._current_stage = stage
            self._current_stage_started_at = now
            self._log(
                "stage_started",
                stage=stage,
                progress=progress,
                detail=detail,
                elapsed_seconds=now - self._started_at,
            )
        else:
            self._log(
                "stage_progress",
                stage=stage,
                progress=progress,
                detail=detail,
                elapsed_seconds=now - self._started_at,
                stage_elapsed_seconds=(
                    None if self._current_stage_started_at is None else now - self._current_stage_started_at
                ),
            )
        self._wrapped.update(stage, progress, detail)

    def completed(self, detail: str | None = None) -> None:
        """标记运行完成：闭合当前阶段 + 写 `run_completed`，再转发到下层。"""
        now = time.perf_counter()
        self._log_stage_completed(now)
        self._log(
            "run_completed",
            detail=detail,
            elapsed_seconds=now - self._started_at,
        )
        self._wrapped.completed(detail)

    def failed(self, message: str) -> None:
        """标记运行失败：闭合当前阶段 + 写 `run_failed`，再转发到下层。"""
        now = time.perf_counter()
        self._log_stage_completed(now)
        self._log(
            "run_failed",
            detail=message,
            elapsed_seconds=now - self._started_at,
        )
        self._wrapped.failed(message)

    def is_cancel_requested(self) -> bool:
        """透传下层 reporter 的取消询问。"""
        return self._wrapped.is_cancel_requested()

    def raise_if_cancelled(self) -> None:
        """透传下层 reporter 的取消异常。"""
        self._wrapped.raise_if_cancelled()

    def cancelled(self, detail: str | None = None) -> None:
        """标记运行取消：闭合当前阶段 + 写 `run_cancelled`，再转发到下层。"""
        now = time.perf_counter()
        self._log_stage_completed(now)
        self._log(
            "run_cancelled",
            detail=detail,
            elapsed_seconds=now - self._started_at,
        )
        self._wrapped.cancelled(detail)

    def _log_stage_completed(self, now: float) -> None:
        """在阶段切换/结束时写入一条 `stage_completed` 事件并清空阶段状态。"""
        if self._current_stage is None or self._current_stage_started_at is None:
            return
        self._log(
            "stage_completed",
            stage=self._current_stage,
            elapsed_seconds=now - self._started_at,
            stage_elapsed_seconds=now - self._current_stage_started_at,
        )
        self._current_stage = None
        self._current_stage_started_at = None

    def _log(
        self,
        event: str,
        *,
        stage: str | None = None,
        progress: float | None = None,
        detail: str | None = None,
        elapsed_seconds: float | None = None,
        stage_elapsed_seconds: float | None = None,
    ) -> None:
        """把一条调试事件以 JSON 形式追加到 `log_path`。

        Args:
            event: 事件名（`run_started` / `stage_started` / `stage_progress` /
                `stage_completed` / `run_completed` / `run_failed` / `run_cancelled`）。
            stage: 当前阶段名；非进度事件时为 `None`。
            progress: 阶段进度百分比。
            detail: 人类可读的详情。
            elapsed_seconds: 距 `run_started` 的总耗时（秒）。
            stage_elapsed_seconds: 距当前阶段开始的耗时（秒）。
        """
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "stage": stage,
            "progress": progress,
            "detail": detail,
            "elapsed_seconds": _round_seconds(elapsed_seconds),
            "stage_elapsed_seconds": _round_seconds(stage_elapsed_seconds),
        }
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _round_seconds(value: float | None) -> float | None:
    """把秒数四舍五入到 3 位小数；负值夹到 0；`None` 直接透传。"""
    if value is None:
        return None
    return round(max(0.0, value), 3)
