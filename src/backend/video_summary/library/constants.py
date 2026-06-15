"""视频库模块的内部常量。

集中维护跨用例共享的魔术值，避免在多个模块中硬编码。
"""

from __future__ import annotations

PLAYGROUND_SERIES_ID = "__playground__"
"""沙盒演练系列的固定 series_id。

用户在未选择具体系列时临时导入的散装视频会被收纳到这个特殊系列下，
从而让所有需要 `series_id` 维度的接口（生成、检索、聊天）仍然可用。
"""

