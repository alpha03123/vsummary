from __future__ import annotations

import json
import shutil
from pathlib import Path

from backend.common.filesystem import atomic_write_text
from backend.video_summary.adapters.plugin.bilibili.models import (
    BilibiliPluginSummaryResult,
    BilibiliPluginVideoKey,
    BilibiliPluginVideoMeta,
)


class BilibiliPluginWorkspace:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._output_root = root_dir / "workspace" / "plugin" / "bilibili"
        self._temp_root = root_dir / "temp" / "plugin" / "bilibili"

    def output_dir(self, key: BilibiliPluginVideoKey) -> Path:
        return self._output_root / key.bvid / key.page_dir_name

    def temp_dir(self, key: BilibiliPluginVideoKey) -> Path:
        return self._temp_root / key.bvid / key.page_dir_name

    def save_meta(self, meta: BilibiliPluginVideoMeta) -> None:
        output_dir = self.output_dir(BilibiliPluginVideoKey(meta.bvid, meta.page))
        output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            output_dir / "meta.json",
            json.dumps(
                {
                    "bvid": meta.bvid,
                    "page": meta.page,
                    "video_id": meta.video_id,
                    "title": meta.title,
                    "source_url": meta.source_url,
                    "cover_url": meta.cover_url,
                    "duration_seconds": meta.duration_seconds,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    def get_meta(self, key: BilibiliPluginVideoKey) -> BilibiliPluginVideoMeta | None:
        meta_path = self.output_dir(key) / "meta.json"
        if not meta_path.exists():
            return None
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        return BilibiliPluginVideoMeta(
            bvid=_require_text(payload.get("bvid"), "meta.bvid"),
            page=_as_positive_int(payload.get("page"), 1),
            video_id=_require_text(payload.get("video_id"), "meta.video_id"),
            title=_require_text(payload.get("title"), "meta.title"),
            source_url=str(payload.get("source_url", "")),
            cover_url=str(payload.get("cover_url", "")),
            duration_seconds=_as_positive_int(payload.get("duration_seconds"), 0),
        )

    def get_summary(self, key: BilibiliPluginVideoKey) -> BilibiliPluginSummaryResult | None:
        meta = self.get_meta(key)
        if meta is None:
            return None
        summary_path = self.output_dir(key) / "summary.json"
        if not summary_path.exists():
            return None
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("summary.json 格式错误：必须是对象。")
        return BilibiliPluginSummaryResult(key=key, meta=meta, summary=payload)

    def cleanup_temp_dir(self, key: BilibiliPluginVideoKey) -> None:
        temp_dir = self.temp_dir(key)
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空字符串。")
    return value.strip()


def _as_positive_int(value: object, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return fallback
