# Issue #6: bootstrap.py 缺失 GenerateSeriesMindmapFromLibrary 导入（pre-existing）

**来源：** Task 4 of Mindmap SSE Progress plan — 验证集成测试时发现

## 问题

`src/backend/api/bootstrap.py` 在 `build_api_container()` 中**引用**了 `GenerateSeriesMindmapFromLibrary`，但**顶部 `from backend.video_summary.library.usecases import (...)` 块里没有导入它**：

```python
# 顶部 import 块只有这些：
from backend.video_summary.library.usecases import (
    ...
    GenerateVideoMindmapFromLibrary,
    ...
    GetSeriesMindmap,
    ...
)
# ❌ GenerateSeriesMindmapFromLibrary 缺失

# 但 container 构造时使用了：
generate_series_mindmap=GenerateSeriesMindmapFromLibrary(workspace, resolved_series_mindmap_generator),
```

任何**走默认容器**的入口（最显著的是 `backend.api.app` 模块级的 `app = create_app()`）都会触发 `NameError`。这导致所有 `tests/backend/integration/api/test_*.py` 在 collection 阶段就报错：

```
NameError: name 'GenerateSeriesMindmapFromLibrary' is not defined
```

## 验证

在 stash 我的改动后重新运行 `tests/backend/integration/api/test_mindmap_api.py` —— 仍然同样报 `NameError`。说明这不是我的改动引入的回归，而是 pre-existing bug。

## 修复

在 `bootstrap.py` 顶部 import 块加入 `GenerateSeriesMindmapFromLibrary`：

```python
from backend.video_summary.library.usecases import (
    ...
    GenerateSeriesMindmapFromLibrary,  # 新增
    GenerateVideoMindmapFromLibrary,
    GenerateVideoSummaryFromLibrary,
    ...
)
```

## 严重程度

**中** — 任何 `from backend.api.app import create_app` 或 `from backend.api.app import app` 都会触发 `NameError`，导致 import-time 失败。但用 mock container 直接传给 `create_app(container=...)` 时**不会**触发，因为 `build_api_container` 不会被调用。

## 解决方式

不在 Task 4 范围里（spec 明确说"Integration tests may have collection errors from missing `lancedb` dependency — that's a pre-existing env issue, not your problem"）。建议另开一个 issue 修复，或在 Task 5+ 实施前顺带修掉。