"""视频库模块的内部常量。

集中维护跨用例共享的魔术值，避免在多个模块中硬编码。
"""

from __future__ import annotations

PLAYGROUND_SERIES_ID = "__playground__"
"""沙盒演练系列的固定 series_id。

用户在未选择具体系列时临时导入的散装视频会被收纳到这个特殊系列下，
从而让所有需要 `series_id` 维度的接口（生成、检索、聊天）仍然可用。
"""

BILIBILI_INBOX_SOURCE_KIND = "bilibili_inbox"
"""浏览器扩展 Bilibili 收件箱在控制面中的 source_kind。"""

BILIBILI_INBOX_TITLE = "B站导入"
"""浏览器扩展 Bilibili 收件箱的固定展示名称。"""

MEDIA_STORAGE_MODES = frozenset({"copy", "hardlink", "external_reference"})
"""本地系列可选的视频存储方式。"""

AUDIO_SUFFIXES = frozenset({".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"})
VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"})
MEDIA_SUFFIXES = AUDIO_SUFFIXES | VIDEO_SUFFIXES

