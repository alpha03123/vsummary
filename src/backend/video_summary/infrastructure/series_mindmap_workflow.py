"""系列思维导图生成的"配置感知"工作流包装。

业务目的：把 `GenerateSeriesMindmap` 用例绑定到项目根目录下的 settings.toml 与 .env；
当配置发生变化（settings.toml 或 .env 被改写）时，自动重建用例缓存，避免
长跑进程里继续使用旧的 LLM 网关参数。
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from backend.video_summary.infrastructure.application_builders import build_series_mindmap_application


class ConfiguredSeriesMindmapWorkflow:
    """对 `GenerateSeriesMindmap` 用例做"按配置缓存 + 自动失效"的轻量包装。

    业务场景：系列总结流程结束后由上层调用本类触发系列级思维导图生成；
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
        series_dir: Path,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
    ) -> None:
        """基于当前配置执行一次系列级思维导图生成。

        Args:
            series_dir: 系列制品目录，思维导图 JSON 写入该目录。
            series_title: 系列标题，用于根节点上下文。
            catalog: 系列目录数据字典（series_catalog.json 的内容）。
            video_summaries: 各视频概括列表，每项应包含 title / one_sentence_summary / chapters 等字段。
        """
        application = self._get_application()
        await application.use_case.run(
            series_title=series_title,
            catalog=catalog,
            video_summaries=video_summaries,
            output_dir=series_dir,
        )

    def _get_application(self):
        """获取（必要时重建）用例。

        缓存键为 `(settings.toml 文本, .env 文本)`，二者任一被修改都会触发重建。
        并发安全由 `_application_lock` 串行化，避免并发触发两次 `build_series_mindmap_application`。
        """
        signature = (
            self._config_path.read_text(encoding="utf-8"),
            self._dotenv_path.read_text(encoding="utf-8") if self._dotenv_path.exists() else "",
        )
        with self._application_lock:
            if self._cached_application is None or self._cached_signature != signature:
                self._cached_application = build_series_mindmap_application(
                    config_path=self._config_path,
                    root_dir=self._root_dir,
                )
                self._cached_signature = signature
            return self._cached_application
