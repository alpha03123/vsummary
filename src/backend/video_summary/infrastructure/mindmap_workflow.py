"""视频思维导图生成的"配置感知"工作流包装。

业务目的：把 `GenerateMindmap` 用例绑定到项目根目录下的 settings.toml 与 .env；
当配置发生变化（settings.toml 或 .env 被改写）时，自动重建用例缓存，避免
长跑进程里继续使用旧的 LLM 网关参数。
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from backend.video_summary.infrastructure.application_builders import build_mindmap_application
from backend.video_summary.infrastructure.config.settings import ensure_settings_file


class ConfiguredMindmapWorkflow:
    """对 `GenerateMindmap` 用例做"按配置缓存 + 自动失效"的轻量包装。

    业务场景：单视频生成流程结束后由上层调用本类触发思维导图生成；
    通过缓存 `(settings.toml, .env)` 文本签名避免每次重新构造 LLM 网关，
    同时支持用户在运行时改写配置后自动重建。
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
        self._cached_signature: tuple[str, str] | None = None
        self._cached_application = None

    async def run(
        self,
        source_path: Path,
        output_dir: Path,
        summary_data: dict[str, object],
        transcript_text: str = "",
        progress_reporter=None,
    ) -> None:
        """基于当前配置执行一次思维导图生成。

        从 `summary_data` 的最后一个章节推导 `duration_seconds`；
        不直接驱动转写，仅消费已生成的总结。

        Args:
            source_path: 媒体源路径，仅取 `stem` 作为标题。
            output_dir: 思维导图制品的输出目录（`mindmap.json`）。
            summary_data: 来自总结阶段的结构化数据，用于驱动导图生成。
            transcript_text: 转写全文文本，可选注入以丰富导图层级细节。
            progress_reporter: 可选进度上报端口；为 `None` 时不进行 SSE 上报。
        """
        application = self._get_application()
        await application.use_case.run(
            title=source_path.stem,
            duration_seconds=_resolve_duration_seconds(summary_data),
            summary_data=summary_data,
            output_dir=output_dir,
            transcript_text=transcript_text,
            progress_reporter=progress_reporter,
        )

    def _get_application(self):
        """获取（必要时重建）用例。

        缓存键为 `(settings.toml 文本, .env 文本)`，二者任一被修改都会触发重建。
        并发安全由 `_application_lock` 串行化，避免并发触发两次 `build_mindmap_application`。
        """
        ensure_settings_file(self._config_path)
        signature = (
            self._config_path.read_text(encoding="utf-8"),
            self._dotenv_path.read_text(encoding="utf-8") if self._dotenv_path.exists() else "",
        )
        with self._application_lock:
            if self._cached_application is None or self._cached_signature != signature:
                self._cached_application = build_mindmap_application(
                    config_path=self._config_path,
                    root_dir=self._root_dir,
                )
                self._cached_signature = signature
            return self._cached_application


def _resolve_duration_seconds(summary_data: dict[str, object]) -> float:
    """从 summary 结构化数据中推导视频时长（最后一个章节的 `end_seconds`）。

    Args:
        summary_data: 由 `summary_generation` 阶段生成的章节列表。

    Returns:
        视频时长（秒）；`chapters` 缺失或非 dict 时回退为 `0.0`。
    """
    chapters = summary_data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return 0.0
    chapter = chapters[-1]
    if not isinstance(chapter, dict):
        return 0.0
    end_seconds = chapter.get("end_seconds", 0.0)
    return float(end_seconds or 0.0)
