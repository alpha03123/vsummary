# Issue #6: Task 3 — Protocol widening breaks existing FakeSeriesMindmapGenerator

**来源：** Task 3 of Mindmap SSE Progress plan — `test_generate_series_mindmap.py`

## 问题

Task 3 把 `library/ports.py` 的 `SeriesMindmapGenerator.run()` 协议新增了一个 keyword-only 参数
`progress_reporter: ProgressReporter | None = None`。

`tests/backend/unit/mindmap/test_generate_series_mindmap.py` 里现有的 `FakeSeriesMindmapGenerator.run()`
签名是：

```python
async def run(self, *, series_id, series_title, catalog, video_summaries):
    self.last_call = {"series_id": series_id, "catalog": catalog, "video_summaries": video_summaries}
```

没有 `**kwargs`，也没声明 `progress_reporter`。当 `GenerateSeriesMindmapFromLibrary.run()`
传递 `progress_reporter=progress_reporter` 给它时，Python 在运行时直接抛 `TypeError`：

```
TypeError: FakeSeriesMindmapGenerator.run() got an unexpected keyword argument 'progress_reporter'
```

失败用例：

```
FAILED tests/backend/unit/mindmap/test_generate_series_mindmap.py::GenerateSeriesMindmapFromLibraryTests::test_collects_all_video_summaries
FAILED tests/backend/unit/mindmap/test_generate_series_mindmap.py::GenerateSeriesMindmapFromLibraryTests::test_skips_videos_without_summary
```

## 严重程度

**中** — 不影响生产代码（真实实现 `WorkspaceBackedSeriesMindmapGenerator` 已经更新签名），
只影响现有 unit test fake；只要同步更新 fake 即可恢复 green。

## 修复

让 fake 也接收 `progress_reporter`，并把它存到 `last_call` 里以便后续断言。

```python
class FakeSeriesMindmapGenerator:
    def __init__(self):
        self.last_call = None

    async def run(self, *, series_id, series_title, catalog, video_summaries, progress_reporter=None):
        self.last_call = {
            "series_id": series_id,
            "catalog": catalog,
            "video_summaries": video_summaries,
            "progress_reporter": progress_reporter,
        }
```

## 经验教训

任何向 `Protocol.run()` 新增 keyword 参数时，**必须**同步扫描所有 fake / 测试替身并补齐签名
（或改成 `**kwargs`）。建议在 plan spec 里加一条 checklist：
"扩展 Protocol 后，搜 `class.*Generator` / `class.*Adapter` 检查每个实现是否补齐新参数"。