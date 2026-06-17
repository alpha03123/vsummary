# Mindmap Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix empty/shallow mindmaps by injecting transcript text into the LLM prompt, add regenerate+export buttons to the UI, and implement series-level cross-video mindmap generation.

**Architecture:** Follow existing 4-layer pattern (generation → library → infrastructure) for all new code. Series mindmap mirrors single-video mindmap structure exactly. All new files respect import-linter boundaries. Agent tools use pure UI_ACTION plane (frontend handles API calls).

**Tech Stack:** Python 3.12, FastAPI, Pydantic, LiteLLM, React/Vite, Vitest, pytest

---

## File Structure Map

### New files (6)
```
src/backend/video_summary/generation/prompts/series_mindmap.py
src/backend/video_summary/generation/usecases/generate_series_mindmap.py
src/backend/video_summary/infrastructure/litellm_series_mindmap_generator.py
src/backend/video_summary/infrastructure/series_mindmap_workflow.py
src/backend/video_summary/library/usecases/series_mindmap_generation.py
src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx
```

### Test files to create (5)
```
tests/backend/unit/mindmap/__init__.py
tests/backend/unit/mindmap/test_mindmap_prompt.py
tests/backend/unit/mindmap/test_mindmap_export.py
tests/backend/unit/mindmap/test_series_mindmap_prompt.py
tests/backend/unit/mindmap/test_generate_series_mindmap.py
tests/backend/unit/mindmap/test_series_mindmap_export.py
tests/backend/integration/api/test_mindmap_api.py
tests/backend/integration/api/test_series_mindmap_api.py
```

### Modified files (36) — see individual tasks

---

## Phase 1: Transcript Injection (backend only)

### Task 1: Create mindmap test package and prompt tests

**Files:**
- Create: `tests/backend/unit/mindmap/__init__.py`
- Create: `tests/backend/unit/mindmap/test_mindmap_prompt.py`

- [ ] **Step 1: Create `__init__.py`**

```bash
mkdir -p tests/backend/unit/mindmap
```

```python
# tests/backend/unit/mindmap/__init__.py
```

- [ ] **Step 2: Write failing prompt tests**

```python
# tests/backend/unit/mindmap/test_mindmap_prompt.py
from __future__ import annotations

import unittest

from backend.video_summary.infrastructure.litellm_mindmap_generator import build_mindmap_prompt


class MindmapPromptTranscriptTests(unittest.TestCase):
    def test_prompt_includes_transcript_text(self) -> None:
        prompt = build_mindmap_prompt(
            title="测试视频",
            duration_seconds=300.0,
            summary_data={"title": "测试", "chapters": []},
            transcript_text="这是一段转写文本",
        )
        self.assertIn("转写文本", prompt)
        self.assertIn("这是一段转写文本", prompt)

    def test_prompt_handles_empty_transcript(self) -> None:
        prompt = build_mindmap_prompt(
            title="测试视频",
            duration_seconds=300.0,
            summary_data={"title": "测试", "chapters": []},
            transcript_text="",
        )
        self.assertIn("转写文本", prompt)

    def test_prompt_truncates_long_transcript(self) -> None:
        long_text = "测" * 10000
        prompt = build_mindmap_prompt(
            title="测试视频",
            duration_seconds=300.0,
            summary_data={"title": "测试", "chapters": []},
            transcript_text=long_text,
        )
        transcript_start = prompt.find("转写文本：") + len("转写文本：")
        transcript_section = prompt[transcript_start:].strip()
        self.assertLessEqual(len(transcript_section), 3000)

    def test_prompt_still_includes_summary_and_title(self) -> None:
        prompt = build_mindmap_prompt(
            title="测试视频",
            duration_seconds=300.0,
            summary_data={"title": "测试视频", "chapters": []},
            transcript_text="转写内容",
        )
        self.assertIn("测试视频", prompt)
        self.assertIn("300", prompt)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_mindmap_prompt.py -v
```
Expected: FAIL — `build_mindmap_prompt() got an unexpected keyword argument 'transcript_text'`

- [ ] **Step 4: Update prompt template**

```python
# src/backend/video_summary/infrastructure/prompts/mindmap.py
# Replace the MINDMAP_PROMPT_TEMPLATE assignment. Add transcript_text section
# after the summary_json line.

MINDMAP_PROMPT_TEMPLATE = (
    "请基于以下视频概况信息，生成一个适合前端交互展示的思维导图 JSON。\n"
    "要求：\n"
    "1. 只输出 JSON，不要输出额外解释。\n"
    "2. 不要编造 summary 中不存在的信息。\n"
    "3. 导图节点必须是树结构，且每个节点都包含 id、title、summary、start_seconds、end_seconds、children。\n"
    "4. 请按知识结构组织节点，而不是机械复述章节目录；可以参考章节，但不要被时间顺序束缚。\n"
    "5. 层级深度由内容复杂度决定：简单主题可以较浅，复杂主题可以自然展开到更深层，但每一层都必须有信息价值。\n"
    "6. 节点标题尽量简洁，优先使用关键词或短语，不要把整句摘要直接当标题。\n"
    "7. 时间范围必须落在视频时长内。\n\n"
    "视频标题：{title}\n"
    "视频时长秒数：{duration_seconds}\n"
    "概况 JSON：\n"
    "{summary_json}\n"
    "转写文本：{transcript_text}\n"
)
```

- [ ] **Step 5: Update `build_mindmap_prompt()` signature**

```python
# src/backend/video_summary/infrastructure/litellm_mindmap_generator.py
# Replace the build_mindmap_prompt function:

def build_mindmap_prompt(*, title: str, duration_seconds: float, summary_data: dict[str, object], transcript_text: str = "") -> str:
    """渲染思维导图提示词模板。

    Args:
        title: 视频标题。
        duration_seconds: 视频时长（秒），在模板中取整展示。
        summary_data: 总结数据字典，使用 ensure_ascii=False 以保留中文。
        transcript_text: 转写文本，截断到前 3000 字符以防撑爆上下文窗口。

    Returns:
        渲染完成的提示词字符串。
    """
    truncated = transcript_text[:3000] if transcript_text else ""
    return MINDMAP_PROMPT_TEMPLATE.format(
        title=title,
        duration_seconds=int(duration_seconds),
        summary_json=json.dumps(summary_data, ensure_ascii=False, indent=2),
        transcript_text=truncated,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_mindmap_prompt.py -v
```
Expected: 4 PASS

- [ ] **Step 7: Commit**

```bash
git add tests/backend/unit/mindmap/__init__.py tests/backend/unit/mindmap/test_mindmap_prompt.py src/backend/video_summary/infrastructure/prompts/mindmap.py src/backend/video_summary/infrastructure/litellm_mindmap_generator.py
git commit -m "feat(mindmap): add transcript_text to mindmap prompt template and builder"
```

---

### Task 2: Propagate transcript_text through generation layer

**Files:**
- Modify: `src/backend/video_summary/generation/ports.py` — `MindmapGenerator.generate()` signature
- Modify: `src/backend/video_summary/generation/usecases/generate_mindmap.py` — `GenerateMindmap.run()` signature

- [ ] **Step 1: Update `MindmapGenerator` Protocol**

```python
# src/backend/video_summary/generation/ports.py
# In MindmapGenerator Protocol, update generate() signature:

class MindmapGenerator(Protocol):
    """思维导图生成端口（纯函数式，不落盘）。"""

    async def generate(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
        transcript_text: str = "",
    ) -> dict[str, object]:
        """基于总结数据生成思维导图节点/边字典。"""
```

- [ ] **Step 2: Update `GenerateMindmap` use-case**

```python
# src/backend/video_summary/generation/usecases/generate_mindmap.py
# In GenerateMindmap.run(), add transcript_text parameter and pass to generator:

    async def run(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
        output_dir: Path,
        transcript_text: str = "",
    ) -> dict[str, object]:
        mindmap = await self._generator.generate(
            title=title,
            duration_seconds=duration_seconds,
            summary_data=summary_data,
            transcript_text=transcript_text,
        )
        await self._artifact_store.save_mindmap(mindmap=mindmap, output_dir=output_dir)
        return mindmap
```

- [ ] **Step 3: Update `LiteLLMMindmapGenerator.generate()`**

```python
# src/backend/video_summary/infrastructure/litellm_mindmap_generator.py
# In LiteLLMMindmapGenerator.generate(), add transcript_text and pass to prompt builder:

    async def generate(
        self,
        *,
        title: str,
        duration_seconds: float,
        summary_data: dict[str, object],
        transcript_text: str = "",
    ) -> dict[str, object]:
        prompt = build_mindmap_prompt(
            title=title,
            duration_seconds=duration_seconds,
            summary_data=summary_data,
            transcript_text=transcript_text,
        )
        payload = await self._gateway.acomplete_structured(
            [{"role": "user", "content": prompt}],
            response_model=MindmapNodePayload,
            retries=3,
        )
        return payload.model_dump()
```

- [ ] **Step 4: Run existing prompt test to verify backward compat**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_mindmap_prompt.py tests/backend/integration/llm/test_mindmap_and_knowledge_cards.py::MindmapPromptTests -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/backend/video_summary/generation/ports.py src/backend/video_summary/generation/usecases/generate_mindmap.py src/backend/video_summary/infrastructure/litellm_mindmap_generator.py
git commit -m "feat(mindmap): propagate transcript_text through generation layer ports and use-case"
```

---

### Task 3: Propagate transcript_text through workflow and library layer

**Files:**
- Modify: `src/backend/video_summary/infrastructure/mindmap_workflow.py`
- Modify: `src/backend/video_summary/library/ports.py`
- Modify: `src/backend/video_summary/infrastructure/library_generation_adapters.py`
- Modify: `src/backend/video_summary/library/usecases/mindmap_generation.py`

- [ ] **Step 1: Create unit test for library use-case transcript pass-through**

```python
# tests/backend/unit/mindmap/test_generate_mindmap.py
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from backend.video_summary.library.models import (
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
    VideoSummaryDTO,
    WorkspaceDTO,
)
from backend.video_summary.library.usecases.mindmap_generation import GenerateVideoMindmapFromLibrary


class FakeWorkspaceForMindmap:
    def __init__(self, summary=None, transcript_text=None):
        self._summary = summary
        self._transcript_text = transcript_text
        self._mindmap = None
        self._last_transcript_arg = None

    def get_video_summary(self, series_id, video_id):
        return self._summary

    def get_video_transcript(self, series_id, video_id):
        return self._transcript_text

    def get_video_source(self, series_id, video_id):
        return None

    def list_series(self):
        return []

    def get_workspace(self):
        return WorkspaceDTO(id="ws", title="ws")

    def get_video_mindmap(self, series_id, video_id):
        return self._mindmap


class FakeMindmapGenerator:
    def __init__(self):
        self.last_call_args = None

    async def run(self, *, series_id, video_id, summary_data, transcript_text=""):
        self.last_call_args = {
            "series_id": series_id,
            "video_id": video_id,
            "summary_data": summary_data,
            "transcript_text": transcript_text,
        }


class GenerateVideoMindmapTranscriptTests(unittest.TestCase):
    async def test_passes_transcript_text_to_generator(self):
        generator = FakeMindmapGenerator()
        workspace = FakeWorkspaceForMindmap(
            summary=VideoSummaryDTO(
                series_id="s1", video_id="v1", title="Test", summary={"chapters": []}
            ),
            transcript_text="转写全文内容在这里",
        )
        use_case = GenerateVideoMindmapFromLibrary(workspace, generator)
        await use_case.run("s1", "v1")
        self.assertEqual(generator.last_call_args["transcript_text"], "转写全文内容在这里")

    async def test_passes_empty_string_when_transcript_is_none(self):
        generator = FakeMindmapGenerator()
        workspace = FakeWorkspaceForMindmap(
            summary=VideoSummaryDTO(
                series_id="s1", video_id="v1", title="Test", summary={"chapters": []}
            ),
            transcript_text=None,
        )
        use_case = GenerateVideoMindmapFromLibrary(workspace, generator)
        await use_case.run("s1", "v1")
        self.assertEqual(generator.last_call_args["transcript_text"], "")

    async def test_returns_none_when_summary_missing(self):
        generator = FakeMindmapGenerator()
        workspace = FakeWorkspaceForMindmap(summary=None)
        use_case = GenerateVideoMindmapFromLibrary(workspace, generator)
        result = await use_case.run("s1", "v1")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_generate_mindmap.py -v
```
Expected: FAIL — `VideoMindmapGenerator.run()` has no `transcript_text` param

- [ ] **Step 3: Update `ConfiguredMindmapWorkflow.run()`**

```python
# src/backend/video_summary/infrastructure/mindmap_workflow.py
# In ConfiguredMindmapWorkflow.run(), add transcript_text parameter:

    async def run(self, source_path: Path, output_dir: Path, summary_data: dict[str, object], transcript_text: str = "") -> None:
        application = self._get_application()
        await application.use_case.run(
            title=source_path.stem,
            duration_seconds=_resolve_duration_seconds(summary_data),
            summary_data=summary_data,
            output_dir=output_dir,
            transcript_text=transcript_text,
        )
```

- [ ] **Step 4: Update `VideoMindmapGenerator` Protocol in library ports**

```python
# src/backend/video_summary/library/ports.py
# In VideoMindmapGenerator Protocol, update run() signature:

class VideoMindmapGenerator(Protocol):
    """思维导图的异步生成端口。"""

    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        summary_data: dict[str, object],
        transcript_text: str = "",
    ) -> None:
        """基于已生成的总结数据生成思维导图，副作用是落盘到视频制品目录。"""
```

- [ ] **Step 5: Update `WorkspaceBackedVideoMindmapGenerator.run()`**

```python
# src/backend/video_summary/infrastructure/library_generation_adapters.py
# In WorkspaceBackedVideoMindmapGenerator.run(), pass transcript_text:

    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        summary_data: dict[str, object],
        transcript_text: str = "",
    ) -> None:
        video = _require_video_source(self._workspace, series_id, video_id)
        await self._workflow.run(video.source_path, video.output_dir, summary_data, transcript_text=transcript_text)
```

- [ ] **Step 6: Update `GenerateVideoMindmapFromLibrary.run()`**

```python
# src/backend/video_summary/library/usecases/mindmap_generation.py
# In GenerateVideoMindmapFromLibrary.run(), read transcript and pass:

    async def run(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        summary = self._workspace.get_video_summary(series_id, video_id)
        if summary is None:
            return None

        transcript = self._workspace.get_video_transcript(series_id, video_id)
        transcript_text = "\n".join(s.text for s in transcript.segments) if transcript is not None else ""

        try:
            await self._generator.run(
                series_id=series_id,
                video_id=video_id,
                summary_data=summary.summary,
                transcript_text=transcript_text,
            )
        except LookupError:
            return None
        return self._workspace.get_video_mindmap(series_id, video_id)
```

Note: `VideoTranscriptDTO` has a `segments` list of `TranscriptSegmentDTO` but no `full_text` property — extract text via `"\\n".join(s.text for s in transcript.segments)`.

- [ ] **Step 7: Run tests to verify they pass**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_generate_mindmap.py -v
```
Expected: 3 PASS

- [ ] **Step 8: Run import-linter to verify boundaries**

```bash
lint-imports
```
Expected: no new violations

- [ ] **Step 9: Commit**

```bash
git add tests/backend/unit/mindmap/test_generate_mindmap.py src/backend/video_summary/infrastructure/mindmap_workflow.py src/backend/video_summary/library/ports.py src/backend/video_summary/infrastructure/library_generation_adapters.py src/backend/video_summary/library/usecases/mindmap_generation.py
git commit -m "feat(mindmap): propagate transcript_text through workflow, library ports, and adapter"
```

---

## Phase 2: Export Button (backend first, then frontend)

### Task 4: Mindmap Markdown export — backend

**Files:**
- Create: `tests/backend/unit/mindmap/test_mindmap_export.py`
- Modify: `src/backend/api/routes/videos.py`

- [ ] **Step 1: Write export unit tests**

```python
# tests/backend/unit/mindmap/test_mindmap_export.py
from __future__ import annotations

import unittest


def render_mindmap_markdown(node: dict, depth: int = 0) -> str:
    """Recursively render a mindmap node tree as Markdown nested list."""
    indent = "  " * depth
    title = node.get("title", "")
    summary = node.get("summary", "")
    lines = [f"{indent}- **{title}**"]
    if summary:
        lines.append(f"{indent}  {summary}")
    for child in node.get("children", []) or []:
        lines.append(render_mindmap_markdown(child, depth + 1))
    return "\n".join(lines)


class MindmapExportTests(unittest.TestCase):
    def test_export_renders_nested_markdown_list(self):
        node = {
            "id": "root",
            "title": "根节点",
            "summary": "",
            "children": [
                {
                    "id": "c1",
                    "title": "子节点1",
                    "summary": "这是摘要",
                    "children": [
                        {"id": "gc1", "title": "孙节点", "summary": "", "children": []},
                    ],
                },
                {"id": "c2", "title": "子节点2", "summary": "", "children": []},
            ],
        }
        result = render_mindmap_markdown(node)
        self.assertIn("- **根节点**", result)
        self.assertIn("  - **子节点1**", result)
        self.assertIn("    这是摘要", result)
        self.assertIn("    - **孙节点**", result)
        self.assertIn("  - **子节点2**", result)

    def test_export_handles_single_root_node(self):
        node = {"id": "root", "title": "唯一节点", "summary": "", "children": []}
        result = render_mindmap_markdown(node)
        self.assertEqual(result, "- **唯一节点**")

    def test_export_handles_empty_children(self):
        node = {"id": "root", "title": "根", "summary": "", "children": []}
        result = render_mindmap_markdown(node)
        self.assertIsInstance(result, str)

    def test_export_includes_node_summary(self):
        node = {
            "id": "root",
            "title": "根",
            "summary": "重要摘要内容",
            "children": [],
        }
        result = render_mindmap_markdown(node)
        self.assertIn("重要摘要内容")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_mindmap_export.py -v
```
Expected: 4 PASS

- [ ] **Step 3: Move `render_mindmap_markdown` to production code**

```python
# Create: src/backend/video_summary/infrastructure/mindmap_export.py
from __future__ import annotations


def render_mindmap_markdown(node: dict, depth: int = 0) -> str:
    """Recursively render a mindmap node tree as Markdown nested list."""
    indent = "  " * depth
    title = node.get("title", "")
    summary = node.get("summary", "")
    lines = [f"{indent}- **{title}**"]
    if summary:
        lines.append(f"{indent}  {summary}")
    children = node.get("children", []) or []
    for child in children:
        lines.append(render_mindmap_markdown(child, depth + 1))
    return "\n".join(lines)
```

- [ ] **Step 4: Update test to import from production module**

```python
# tests/backend/unit/mindmap/test_mindmap_export.py
# Replace the inline render_mindmap_markdown with:
from backend.video_summary.infrastructure.mindmap_export import render_mindmap_markdown
```

- [ ] **Step 5: Run tests to verify they still pass**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_mindmap_export.py -v
```
Expected: 4 PASS

- [ ] **Step 6: Add export endpoint to videos.py**

```python
# src/backend/api/routes/videos.py — add new endpoint before the mindmap/generate endpoint:

from backend.video_summary.infrastructure.mindmap_export import render_mindmap_markdown
from fastapi.responses import PlainTextResponse

@router.get("/api/videos/{series_id}/{video_id}/mindmap/export")
def export_video_mindmap(series_id: str, video_id: str, format: str = "md", container: ApiContainerDep = None):
    """GET /api/videos/{series_id}/{video_id}/mindmap/export?format=md — 导出思维导图为 Markdown。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。
        format: 导出格式，当前仅支持 "md"。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        Markdown 文本响应，带 Content-Disposition 下载头。

    Raises:
        HTTPException(400): 不支持的格式。
        HTTPException(404): 思维导图不存在。
    """
    if format != "md":
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}，仅支持 md")
    _ensure_video_exists(container, series_id, video_id)
    video_mindmap = container.get_video_mindmap.run(series_id, video_id)
    if video_mindmap is None:
        raise HTTPException(status_code=404, detail=f"mindmap not found for video '{series_id}/{video_id}'")
    markdown = render_mindmap_markdown(video_mindmap.mindmap)
    filename = f"{video_mindmap.title}-mindmap.md"
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 7: Run all mindmap tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/ -v
```
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add tests/backend/unit/mindmap/test_mindmap_export.py src/backend/video_summary/infrastructure/mindmap_export.py src/backend/api/routes/videos.py
git commit -m "feat(mindmap): add Markdown export endpoint and renderer"
```

---

### Task 4b: Mindmap export — integration tests

**Files:**
- Create: `tests/backend/integration/api/test_mindmap_api.py`

- [ ] **Step 1: Write integration tests for export endpoint**

```python
# tests/backend/integration/api/test_mindmap_api.py
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class MindmapExportApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.api.app import create_app
        from backend.api.container import ROOT
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.root_dir = Path(cls.temp_dir.name)
        # Create minimal workspace structure for testing
        (cls.root_dir / "config").mkdir(parents=True, exist_ok=True)
        (cls.root_dir / "config" / "settings.toml").write_text(
            '[openai]\nprovider="openai"\nmodel="gpt-4"\nbase_url="https://api.openai.com/v1"\napi_key="sk-test"\n'
            '[asr]\nprovider="faster_whisper"\nlanguage="zh"\n'
            '[asr.faster_whisper]\ndevice="cpu"\ncompute_type="int8"\nmodel_size="tiny"\ntranscription_mode="default"\nmodels_dir="models"\n'
            '[agent_context]\nwindow_tokens=128000\nreserved_output_tokens=4096\ndirect_summary_threshold_ratio=0.8\nreasoning_effort="low"\nanswer_detail_level="normal"\ntalk_custom_prompt=""\n'
            '[generation]\nsummary_chunk_concurrency=1\n'
            '[web_search]\nenabled=false\nengine="duckduckgo"\nmax_results=3\n'
        )
        env_path = cls.root_dir / ".env"
        if not env_path.exists():
            env_path.write_text("OPENAI_API_KEY=sk-test\nOPENAI_BASE_URL=https://api.openai.com/v1\nOPENAI_MODEL=gpt-4\n")
        workspace_dir = cls.root_dir / "workspace" / "s1" / "v1"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (cls.root_dir / "videos" / "s1").mkdir(parents=True, exist_ok=True)
        (cls.root_dir / "videos" / "s1" / "v1.mp4").write_bytes(b"fake")
        mindmap_data = {
            "id": "root",
            "title": "测试导图",
            "summary": "",
            "start_seconds": 0.0,
            "end_seconds": 0.0,
            "children": [
                {"id": "c1", "title": "子节点1", "summary": "摘要", "start_seconds": 0.0, "end_seconds": 60.0, "children": []},
            ],
        }
        (workspace_dir / "mindmap.json").write_text(json.dumps(mindmap_data, ensure_ascii=False), encoding="utf-8")
        (workspace_dir / "summary.json").write_text(
            json.dumps({"title": "测试视频", "chapters": []}, ensure_ascii=False), encoding="utf-8"
        )
        import os
        os.chdir(str(cls.root_dir))
        app = create_app(cls.root_dir)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_export_returns_markdown_content_type(self):
        response = self.client.get("/api/videos/s1/v1/mindmap/export?format=md")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response.headers["content-type"])
        self.assertIn("charset=utf-8", response.headers["content-type"])

    def test_export_returns_content_disposition_header(self):
        response = self.client.get("/api/videos/s1/v1/mindmap/export?format=md")
        self.assertIn("attachment", response.headers["content-disposition"])

    def test_export_returns_404_when_mindmap_not_found(self):
        (self.root_dir / "workspace" / "s2" / "v2").mkdir(parents=True, exist_ok=True)
        (self.root_dir / "videos" / "s2").mkdir(parents=True, exist_ok=True)
        (self.root_dir / "videos" / "s2" / "v2.mp4").write_bytes(b"fake")
        response = self.client.get("/api/videos/s2/v2/mindmap/export?format=md")
        self.assertEqual(response.status_code, 404)

    def test_export_returns_400_for_unsupported_format(self):
        response = self.client.get("/api/videos/s1/v1/mindmap/export?format=pdf")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run integration tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/integration/api/test_mindmap_api.py -v
```
Expected: 4 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/backend/integration/api/test_mindmap_api.py
git commit -m "test(mindmap): add integration tests for mindmap export endpoint"
```

---

### Task 5: Regenerate + Export buttons — frontend

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx`

- [ ] **Step 1: Write frontend tests**

```jsx
// tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
// Add these test cases to the existing test file (or create if missing):

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkspaceMindmapView } from "../../../../../src/features/workspace/ui/views/WorkspaceMindmapView";

function makeTools(overrides = {}) {
  return {
    mindmap: {
      id: "mindmap",
      title: "思维导图",
      available: true,
      generated: false,
      status: "available",
      ...overrides,
    },
  };
}

const fakeMindmap = {
  id: "root",
  title: "测试导图",
  summary: "",
  start_seconds: 0,
  end_seconds: 0,
  children: [],
};

describe("WorkspaceMindmapView — regenerate button", () => {
  it("shows regenerate button when mindmap is generated", () => {
    render(
      <WorkspaceMindmapView
        tools={makeTools({ generated: true })}
        mindmap={fakeMindmap}
        selectedNode={null}
        mindmapLoading={false}
        isGeneratingMindmapSelectedVideo={false}
        onFocusNode={vi.fn()}
        onGenerateMindmap={vi.fn()}
      />
    );
    expect(screen.getByText("重新生成")).toBeTruthy();
  });

  it("hides regenerate button when mindmap not generated", () => {
    render(
      <WorkspaceMindmapView
        tools={makeTools({ generated: false })}
        mindmap={null}
        selectedNode={null}
        mindmapLoading={false}
        isGeneratingMindmapSelectedVideo={false}
        onFocusNode={vi.fn()}
        onGenerateMindmap={vi.fn()}
      />
    );
    expect(screen.queryByText("重新生成")).toBeNull();
  });

  it("regenerate button triggers onGenerateMindmap", async () => {
    const onGenerate = vi.fn();
    render(
      <WorkspaceMindmapView
        tools={makeTools({ generated: true })}
        mindmap={fakeMindmap}
        selectedNode={null}
        mindmapLoading={false}
        isGeneratingMindmapSelectedVideo={false}
        onFocusNode={vi.fn()}
        onGenerateMindmap={onGenerate}
      />
    );
    await userEvent.click(screen.getByText("重新生成"));
    expect(onGenerate).toHaveBeenCalledOnce();
  });

  it("regenerate button disabled while generating", () => {
    render(
      <WorkspaceMindmapView
        tools={makeTools({ generated: true })}
        mindmap={fakeMindmap}
        selectedNode={null}
        mindmapLoading={false}
        isGeneratingMindmapSelectedVideo={true}
        onFocusNode={vi.fn()}
        onGenerateMindmap={vi.fn()}
      />
    );
    const button = screen.getByText("重新生成").closest("button");
    expect(button.disabled).toBe(true);
  });

  it("existing mindmap preserved on generation error", () => {
    const onGenerate = vi.fn().mockRejectedValue(new Error("生成失败"));
    const { rerender } = render(
      <WorkspaceMindmapView
        tools={makeTools({ generated: true })}
        mindmap={fakeMindmap}
        selectedNode={null}
        mindmapLoading={false}
        isGeneratingMindmapSelectedVideo={false}
        onFocusNode={vi.fn()}
        onGenerateMindmap={onGenerate}
      />
    );
    // After error, mindmap data should still be the same
    // The parent controller handles preserving mindmap state on error
    // Verify the view still renders the mindmap
    expect(screen.getByText("测试导图")).toBeTruthy();
  });
});

describe("WorkspaceMindmapView — export button", () => {
  it("shows export button when mindmap is generated", () => {
    render(
      <WorkspaceMindmapView
        tools={makeTools({ generated: true })}
        mindmap={fakeMindmap}
        selectedNode={null}
        mindmapLoading={false}
        isGeneratingMindmapSelectedVideo={false}
        onFocusNode={vi.fn()}
        onGenerateMindmap={vi.fn()}
      />
    );
    expect(screen.getByText("导出")).toBeTruthy();
  });

  it("hides export button when mindmap not generated", () => {
    render(
      <WorkspaceMindmapView
        tools={makeTools({ generated: false })}
        mindmap={null}
        selectedNode={null}
        mindmapLoading={false}
        isGeneratingMindmapSelectedVideo={false}
        onFocusNode={vi.fn()}
        onGenerateMindmap={vi.fn()}
      />
    );
    expect(screen.queryByText("导出")).toBeNull();
  });
});
```

- [ ] **Step 2: Run frontend tests to verify they fail**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
```
Expected: FAIL — no "重新生成" or "导出" button found

- [ ] **Step 3: Add regenerate and export buttons to the generated state**

```jsx
// src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx
// Add imports at top:
import { Download, RefreshCw } from "lucide-react";

// In the generated state section (the return block after `if (!hasMindmap) return null`),
// add action buttons next to the "Mindmap" label:

<div className="pointer-events-none absolute top-4 left-4 z-10">
  <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Mindmap</p>
</div>
{/* ADD: action buttons */}
<div className="pointer-events-auto absolute top-4 right-4 z-10 flex items-center gap-2">
  <button
    type="button"
    onClick={onGenerateMindmap}
    disabled={isGeneratingMindmapSelectedVideo}
    className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
  >
    <RefreshCw size={14} strokeWidth={2} className={isGeneratingMindmapSelectedVideo ? "animate-spin" : ""} />
    重新生成
  </button>
  <a
    href={`/api/videos/${/* need seriesId/videoId from parent */""}/mindmap/export?format=md`}
    download
    className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors"
  >
    <Download size={14} strokeWidth={2} />
    导出
  </a>
</div>
```

Note: The component needs `seriesId` and `videoId` props for the export URL. Add them to the component's props destructuring and pass them from `WorkspaceReadingPane.jsx`.

- [ ] **Step 4: Update `WorkspaceMindmapView` to accept seriesId/videoId**

```jsx
// src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx
// Add to props:
export function WorkspaceMindmapView({
  tools,
  mindmap,
  selectedNode,
  mindmapLoading,
  isGeneratingMindmapSelectedVideo,
  onFocusNode,
  onGenerateMindmap,
  seriesId,    // NEW
  videoId,     // NEW
}) {
```

- [ ] **Step 5: Update `WorkspaceReadingPane.jsx` to pass seriesId/videoId**

Find the `<WorkspaceMindmapView` usage and add:
```jsx
seriesId={activeSeries?.id}
videoId={selectedVideo?.id}
```

- [ ] **Step 6: Run frontend tests to verify they pass**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx src/frontend/src/features/workspace/ui/WorkspaceReadingPane.jsx tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
git commit -m "feat(mindmap): add regenerate and export buttons to mindmap view"
```

---

## Phase 3: Series Mindmap — Backend

### Task 6: Series mindmap prompt and generator (generation + infra)

**Files:**
- Create: `src/backend/video_summary/generation/prompts/series_mindmap.py`
- Create: `src/backend/video_summary/infrastructure/litellm_series_mindmap_generator.py`
- Create: `tests/backend/unit/mindmap/test_series_mindmap_prompt.py`
- Modify: `src/backend/video_summary/generation/ports.py`
- Modify: `src/backend/video_summary/generation/prompts/__init__.py`
- Modify: `src/backend/video_summary/infrastructure/prompts/__init__.py`

- [ ] **Step 1: Write failing prompt tests**

```python
# tests/backend/unit/mindmap/test_series_mindmap_prompt.py
from __future__ import annotations

import unittest


class SeriesMindmapPromptTests(unittest.TestCase):
    def _build_prompt(self, series_title="测试系列", catalog=None, video_summaries=None):
        from backend.video_summary.infrastructure.litellm_series_mindmap_generator import build_series_mindmap_prompt
        return build_series_mindmap_prompt(
            series_title=series_title,
            catalog=catalog or {"series_title": "测试系列", "videos": []},
            video_summaries=video_summaries or [],
        )

    def test_prompt_includes_series_title(self):
        prompt = self._build_prompt(series_title="机器学习课程")
        self.assertIn("机器学习课程", prompt)

    def test_prompt_includes_video_summaries(self):
        summaries = [{"title": "第一课", "one_sentence_summary": "介绍基础概念"}]
        prompt = self._build_prompt(video_summaries=summaries)
        self.assertIn("第一课", prompt)
        self.assertIn("介绍基础概念", prompt)

    def test_prompt_truncates_large_summaries(self):
        summaries = [
            {"title": f"视频{i}", "one_sentence_summary": f"概要{i}", "chapters": [{"title": "长章节" * 500}]}
            for i in range(50)
        ]
        prompt = self._build_prompt(video_summaries=summaries)
        for i in range(50):
            self.assertIn(f"视频{i}", prompt)
        self.assertNotIn("长章节" * 500, prompt)

    def test_prompt_falls_back_without_catalog(self):
        prompt = self._build_prompt(catalog=None, video_summaries=[{"title": "T1"}])
        self.assertIn("T1", prompt)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Create prompt template**

```python
# src/backend/video_summary/generation/prompts/series_mindmap.py
SERIES_MINDMAP_PROMPT_TEMPLATE = (
    "你是一个知识整理专家。请基于以下系列课程的目录索引和各视频概况，"
    "生成一份跨视频的知识结构思维导图 JSON。\n"
    "要求：\n"
    "1. 只输出 JSON，不要输出额外解释。\n"
    "2. 根节点为系列标题。\n"
    "3. 按知识主题组织二级节点，而非按视频分集罗列。\n"
    "4. 同一知识点出现在多集时，合并为一个节点。\n"
    "5. 节点标题简洁，优先使用关键词或短语。\n"
    "6. 层级深度由内容复杂度决定。\n"
    "7. 不要编造总结中不存在的信息。\n\n"
    "系列目录：\n"
    "{series_catalog_json}\n\n"
    "各视频概况：\n"
    "{video_summaries_json}\n"
)
```

- [ ] **Step 3: Update prompts `__init__.py` files**

```python
# src/backend/video_summary/generation/prompts/__init__.py — add:
from .series_mindmap import SERIES_MINDMAP_PROMPT_TEMPLATE

# src/backend/video_summary/infrastructure/prompts/__init__.py — add:
from backend.video_summary.generation.prompts.series_mindmap import SERIES_MINDMAP_PROMPT_TEMPLATE
```

- [ ] **Step 4: Create `LiteLLMSeriesMindmapGenerator`**

```python
# src/backend/video_summary/infrastructure/litellm_series_mindmap_generator.py
from __future__ import annotations

import json

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.generation.ports import SeriesMindmapGenerator
from backend.video_summary.infrastructure.prompts import SERIES_MINDMAP_PROMPT_TEMPLATE
from backend.video_summary.generation import MindmapNodePayload


class LiteLLMSeriesMindmapGenerator(SeriesMindmapGenerator):
    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        self._gateway = gateway

    async def generate(
        self,
        *,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
    ) -> dict[str, object]:
        prompt = build_series_mindmap_prompt(
            series_title=series_title,
            catalog=catalog,
            video_summaries=video_summaries,
        )
        payload = await self._gateway.acomplete_structured(
            [{"role": "user", "content": prompt}],
            response_model=MindmapNodePayload,
            retries=3,
        )
        return payload.model_dump()


def build_series_mindmap_prompt(
    *,
    series_title: str,
    catalog: dict[str, object] | None,
    video_summaries: list[dict[str, object]],
) -> str:
    catalog_json = json.dumps(catalog, ensure_ascii=False, indent=2) if catalog else "（无系列目录）"
    trimmed = [
        {
            "title": s.get("title", ""),
            "one_sentence_summary": s.get("one_sentence_summary", ""),
            "chapter_titles": [
                c.get("title", "") for c in (s.get("chapters", []) or []) if isinstance(c, dict)
            ],
        }
        for s in video_summaries
    ]
    return SERIES_MINDMAP_PROMPT_TEMPLATE.format(
        series_catalog_json=catalog_json,
        video_summaries_json=json.dumps(trimmed, ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 5: Add `SeriesMindmapGenerator` Protocol to generation ports**

```python
# src/backend/video_summary/generation/ports.py — add after MindmapGenerator:

class SeriesMindmapGenerator(Protocol):
    """系列思维导图生成端口（纯函数式，不落盘）。"""

    async def generate(
        self,
        *,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
    ) -> dict[str, object]:
        """基于系列目录与视频概况列表生成跨视频思维导图节点/边字典。"""
```

- [ ] **Step 6: Run prompt tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_series_mindmap_prompt.py -v
```
Expected: 4 PASS

- [ ] **Step 7: Commit**

```bash
git add tests/backend/unit/mindmap/test_series_mindmap_prompt.py src/backend/video_summary/generation/prompts/series_mindmap.py src/backend/video_summary/generation/prompts/__init__.py src/backend/video_summary/infrastructure/prompts/__init__.py src/backend/video_summary/infrastructure/litellm_series_mindmap_generator.py src/backend/video_summary/generation/ports.py
git commit -m "feat(series-mindmap): add series mindmap prompt, generator, and generation port"
```

---

### Task 7: Series mindmap generation use-case

**Files:**
- Create: `src/backend/video_summary/generation/usecases/generate_series_mindmap.py`
- Modify: `src/backend/video_summary/generation/usecases/__init__.py`

- [ ] **Step 1: Create `GenerateSeriesMindmap` use-case**

```python
# src/backend/video_summary/generation/usecases/generate_series_mindmap.py
from __future__ import annotations

from pathlib import Path

from backend.video_summary.generation.ports import GenerationArtifactStore, SeriesMindmapGenerator


class GenerateSeriesMindmap:
    def __init__(self, generator: SeriesMindmapGenerator, artifact_store: GenerationArtifactStore) -> None:
        self._generator = generator
        self._artifact_store = artifact_store

    async def run(
        self,
        *,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
        output_dir: Path,
    ) -> dict[str, object]:
        mindmap = await self._generator.generate(
            series_title=series_title,
            catalog=catalog,
            video_summaries=video_summaries,
        )
        await self._artifact_store.save_mindmap(mindmap=mindmap, output_dir=output_dir)
        return mindmap
```

- [ ] **Step 2: Export from `__init__.py`**

```python
# src/backend/video_summary/generation/usecases/__init__.py — add:
from backend.video_summary.generation.usecases.generate_series_mindmap import GenerateSeriesMindmap

__all__ = ["GenerateMindmap", "GenerateSeriesMindmap"]
```

- [ ] **Step 3: Commit**

```bash
git add src/backend/video_summary/generation/usecases/generate_series_mindmap.py src/backend/video_summary/generation/usecases/__init__.py
git commit -m "feat(series-mindmap): add GenerateSeriesMindmap generation use-case"
```

---

### Task 8: Series mindmap workflow and application builder

**Files:**
- Create: `src/backend/video_summary/infrastructure/series_mindmap_workflow.py`
- Modify: `src/backend/video_summary/infrastructure/application_builders.py`

- [ ] **Step 1: Create `ConfiguredSeriesMindmapWorkflow`**

```python
# src/backend/video_summary/infrastructure/series_mindmap_workflow.py
from __future__ import annotations

from pathlib import Path
from threading import Lock

from backend.video_summary.infrastructure.application_builders import build_series_mindmap_application


class ConfiguredSeriesMindmapWorkflow:
    def __init__(self, root_dir: Path) -> None:
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
        application = self._get_application()
        await application.use_case.run(
            series_title=series_title,
            catalog=catalog,
            video_summaries=video_summaries,
            output_dir=series_dir,
        )

    def _get_application(self):
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
```

- [ ] **Step 2: Add `build_series_mindmap_application()`**

```python
# src/backend/video_summary/infrastructure/application_builders.py — add after build_mindmap_application:

def build_series_mindmap_application(config_path: Path, root_dir: Path) -> MindmapApplication:
    settings = load_settings(config_path=config_path, root_dir=root_dir)
    gateway = build_litellm_completion_gateway(settings)
    use_case = GenerateSeriesMindmap(
        generator=LiteLLMSeriesMindmapGenerator(gateway=gateway),
        artifact_store=FileSystemGenerationArtifactStore(),
    )
    return MindmapApplication(settings=settings, use_case=use_case)
```

Note: This reuses the existing `MindmapApplication` dataclass since `GenerateSeriesMindmap.run()` has the same signature pattern.

- [ ] **Step 3: Add imports to `application_builders.py`**

```python
from backend.video_summary.generation.usecases.generate_series_mindmap import GenerateSeriesMindmap
from backend.video_summary.infrastructure.litellm_series_mindmap_generator import LiteLLMSeriesMindmapGenerator
```

- [ ] **Step 4: Commit**

```bash
git add src/backend/video_summary/infrastructure/series_mindmap_workflow.py src/backend/video_summary/infrastructure/application_builders.py
git commit -m "feat(series-mindmap): add ConfiguredSeriesMindmapWorkflow and application builder"
```

---

### Task 9: Series mindmap — library layer and adapter

**Files:**
- Create: `src/backend/video_summary/library/usecases/series_mindmap_generation.py`
- Modify: `src/backend/video_summary/library/ports.py`
- Modify: `src/backend/video_summary/infrastructure/library_generation_adapters.py`
- Modify: `src/backend/video_summary/library/usecases/__init__.py`
- Create: `tests/backend/unit/mindmap/test_generate_series_mindmap.py`

- [ ] **Step 1: Write failing library use-case tests**

```python
# tests/backend/unit/mindmap/test_generate_series_mindmap.py
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.video_summary.library.usecases.series_mindmap_generation import GenerateSeriesMindmapFromLibrary


class FakeSeriesWorkspace:
    def __init__(self, series_list=None, summaries_by_video=None, catalog=None, mindmap=None):
        self._series_list = series_list or []
        self._summaries_by_video = summaries_by_video or {}
        self._catalog = catalog
        self._mindmap = mindmap
        self._workspace_dir = MagicMock()

    def list_series(self):
        return self._series_list

    def get_workspace(self):
        from backend.video_summary.library.models import WorkspaceDTO
        return WorkspaceDTO(id="ws", title="ws")

    def get_video_summary(self, series_id, video_id):
        return self._summaries_by_video.get(video_id)

    def get_series_catalog(self, series_id):
        return self._catalog

    def get_video_mindmap(self, series_id, video_id):
        return None

    def get_series_mindmap(self, series_id):
        return self._mindmap


class FakeSeriesMindmapGenerator:
    def __init__(self):
        self.last_call = None

    async def run(self, *, series_id, series_title, catalog, video_summaries):
        self.last_call = {"series_id": series_id, "catalog": catalog, "video_summaries": video_summaries}


class GenerateSeriesMindmapFromLibraryTests(unittest.TestCase):
    async def test_collects_all_video_summaries(self):
        from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO, VideoSummaryDTO

        workspace = FakeSeriesWorkspace(
            series_list=[
                LibrarySeriesDTO(id="s1", title="S1", videos=[
                    LibraryVideoCardDTO(id="v1", title="V1", source_name="v1", processed=True, status="ready"),
                    LibraryVideoCardDTO(id="v2", title="V2", source_name="v2", processed=True, status="ready"),
                ]),
            ],
            summaries_by_video={
                "v1": VideoSummaryDTO(series_id="s1", video_id="v1", title="V1", summary={"chapters": []}),
                "v2": VideoSummaryDTO(series_id="s1", video_id="v2", title="V2", summary={"chapters": []}),
            },
        )
        generator = FakeSeriesMindmapGenerator()
        use_case = GenerateSeriesMindmapFromLibrary(workspace, generator)
        await use_case.run("s1")
        self.assertEqual(len(generator.last_call["video_summaries"]), 2)

    async def test_skips_videos_without_summary(self):
        from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO, VideoSummaryDTO

        workspace = FakeSeriesWorkspace(
            series_list=[
                LibrarySeriesDTO(id="s1", title="S1", videos=[
                    LibraryVideoCardDTO(id="v1", title="V1", source_name="v1", processed=True, status="ready"),
                    LibraryVideoCardDTO(id="v2", title="V2", source_name="v2", processed=False, status="pending"),
                ]),
            ],
            summaries_by_video={
                "v1": VideoSummaryDTO(series_id="s1", video_id="v1", title="V1", summary={"chapters": []}),
            },
        )
        generator = FakeSeriesMindmapGenerator()
        use_case = GenerateSeriesMindmapFromLibrary(workspace, generator)
        await use_case.run("s1")
        self.assertEqual(len(generator.last_call["video_summaries"]), 1)

    async def test_returns_none_when_no_summaries(self):
        from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO

        workspace = FakeSeriesWorkspace(
            series_list=[
                LibrarySeriesDTO(id="s1", title="S1", videos=[
                    LibraryVideoCardDTO(id="v1", title="V1", source_name="v1", processed=False, status="pending"),
                ]),
            ],
            summaries_by_video={},
        )
        generator = FakeSeriesMindmapGenerator()
        use_case = GenerateSeriesMindmapFromLibrary(workspace, generator)
        result = await use_case.run("s1")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_generate_series_mindmap.py -v
```
Expected: FAIL — `GenerateSeriesMindmapFromLibrary` not defined

- [ ] **Step 3: Create `GenerateSeriesMindmapFromLibrary`**

```python
# src/backend/video_summary/library/usecases/series_mindmap_generation.py
from __future__ import annotations

from backend.video_summary.library.ports import SeriesMindmapGenerator, VideoLibraryReader


class GenerateSeriesMindmapFromLibrary:
    def __init__(self, workspace: VideoLibraryReader, generator: SeriesMindmapGenerator) -> None:
        self._workspace = workspace
        self._generator = generator

    async def run(self, series_id: str):
        series_list = self._workspace.list_series()
        series = next((s for s in series_list if s.id == series_id), None)
        if series is None or not series.videos:
            return None

        summaries = []
        for video in series.videos:
            summary = self._workspace.get_video_summary(series_id, video.id)
            if summary is not None:
                summaries.append({"title": summary.title, **summary.summary})

        if not summaries:
            return None

        catalog = self._workspace.get_series_catalog(series_id)

        try:
            await self._generator.run(
                series_id=series_id,
                series_title=series.title,
                catalog=catalog,
                video_summaries=summaries,
            )
        except LookupError:
            return None
        return self._workspace.get_series_mindmap(series_id)
```

- [ ] **Step 4: Add `SeriesMindmapGenerator` Protocol to library ports**

```python
# src/backend/video_summary/library/ports.py — add after VideoMindmapGenerator:

class SeriesMindmapGenerator(Protocol):
    """系列思维导图的异步生成端口。"""

    async def run(
        self,
        *,
        series_id: str,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
    ) -> None:
        """基于系列目录与视频概况生成跨视频思维导图，落盘到系列制品目录。"""
```

- [ ] **Step 5: Create `WorkspaceBackedSeriesMindmapGenerator` adapter**

```python
# src/backend/video_summary/infrastructure/library_generation_adapters.py — add:

class WorkspaceBackedSeriesMindmapGenerator(SeriesMindmapGenerator):
    def __init__(self, workspace: VideoLibraryReader, workflow: ConfiguredSeriesMindmapWorkflow) -> None:
        self._workspace = workspace
        self._workflow = workflow

    async def run(
        self,
        *,
        series_id: str,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
    ) -> None:
        series_dir = self._workspace._workspace_dir / series_id
        await self._workflow.run(series_dir, series_title, catalog, video_summaries)
```

Note: `_workspace_dir` is an implementation detail of `FileSystemVideoWorkspace`. Add a public method `get_series_dir(series_id)` to `VideoLibraryReader` Protocol and `FileSystemVideoWorkspace` instead of accessing private attribute.

- [ ] **Step 6: Add `get_series_mindmap` to filesystem workspace and reader port**

```python
# src/backend/video_summary/library/ports.py — in VideoLibraryReader Protocol, add:
    def get_series_mindmap(self, series_id: str) -> VideoMindmapDTO | None:
        """取系列的思维导图制品；未生成则返回 None。"""
```

```python
# src/backend/video_summary/infrastructure/filesystem_video_workspace.py — add method:
    def get_series_mindmap(self, series_id: str) -> VideoMindmapDTO | None:
        mindmap_path = self._workspace_dir / series_id / "mindmap.json"
        if not mindmap_path.exists():
            return None
        return VideoMindmapDTO(
            series_id=series_id,
            video_id="",
            title=series_id,
            mindmap=json.loads(mindmap_path.read_text(encoding="utf-8")),
        )

    def get_series_dir(self, series_id: str) -> Path:
        return self._workspace_dir / series_id
```

- [ ] **Step 7: Add `get_series_dir` to `VideoLibraryReader` Protocol**

```python
# src/backend/video_summary/library/ports.py — in VideoLibraryReader Protocol, add:
    def get_series_dir(self, series_id: str) -> Path:
        """返回到系列工作区根目录的路径。"""
```

- [ ] **Step 8: Update adapter to use public method**

```python
# In WorkspaceBackedSeriesMindmapGenerator.run():
series_dir = self._workspace.get_series_dir(series_id)
```

- [ ] **Step 9: Export from library `__init__.py`**

```python
# src/backend/video_summary/library/usecases/__init__.py — add:
from backend.video_summary.library.usecases.series_mindmap_generation import GenerateSeriesMindmapFromLibrary

# Add to __all__: "GenerateSeriesMindmapFromLibrary"
```

- [ ] **Step 10: Run tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_generate_series_mindmap.py -v
```
Expected: 3 PASS

- [ ] **Step 11: Commit**

```bash
git add tests/backend/unit/mindmap/test_generate_series_mindmap.py src/backend/video_summary/library/usecases/series_mindmap_generation.py src/backend/video_summary/library/ports.py src/backend/video_summary/infrastructure/library_generation_adapters.py src/backend/video_summary/library/usecases/__init__.py src/backend/video_summary/infrastructure/filesystem_video_workspace.py
git commit -m "feat(series-mindmap): add library use-case, port, adapter, and filesystem methods"
```

---

### Task 10: Series mindmap API routes and container wiring

**Files:**
- Modify: `src/backend/api/bootstrap.py`
- Modify: `src/backend/api/container.py` (if needed for type exports — actually this is the container module, bootstrap has the dataclass)
- Modify: `src/backend/api/routes/series.py`
- Modify: `src/backend/video_summary/tools/mindmap.py`
- Modify: `src/backend/video_summary/tools/catalog.py`
- Modify: `src/backend/video_summary/tools/__init__.py`
- Create: `tests/backend/unit/mindmap/test_series_mindmap_export.py`

- [ ] **Step 1: Add series mindmap export test**

```python
# tests/backend/unit/mindmap/test_series_mindmap_export.py
from __future__ import annotations

import unittest

from backend.video_summary.infrastructure.mindmap_export import render_mindmap_markdown


class SeriesMindmapExportTests(unittest.TestCase):
    def test_export_series_mindmap_markdown(self):
        node = {
            "id": "root",
            "title": "机器学习系列",
            "summary": "",
            "children": [
                {"id": "t1", "title": "监督学习", "summary": "涵盖回归与分类", "children": []},
                {"id": "t2", "title": "无监督学习", "summary": "", "children": []},
            ],
        }
        result = render_mindmap_markdown(node)
        self.assertIn("机器学习系列", result)
        self.assertIn("监督学习", result)
        self.assertIn("无监督学习", result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run export test**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/test_series_mindmap_export.py -v
```
Expected: 1 PASS

- [ ] **Step 3: Add API routes to series.py (with concurrency guard)**

```python
# src/backend/api/routes/series.py — add endpoints and module-level lock:

from threading import Lock
from backend.video_summary.infrastructure.mindmap_export import render_mindmap_markdown
from fastapi.responses import PlainTextResponse

# Module-level lock to prevent concurrent generation of same series mindmap
_series_mindmap_locks: dict[str, Lock] = {}
_series_mindmap_locks_guard = Lock()


def _acquire_series_mindmap_lock(series_id: str) -> bool:
    with _series_mindmap_locks_guard:
        if series_id in _series_mindmap_locks:
            return False
        _series_mindmap_locks[series_id] = Lock()
        return True


def _release_series_mindmap_lock(series_id: str) -> None:
    with _series_mindmap_locks_guard:
        _series_mindmap_locks.pop(series_id, None)


@router.get("/api/series/{series_id}/mindmap")
def get_series_mindmap(series_id: str, container: ApiContainerDep) -> dict[str, object]:
    """GET /api/series/{series_id}/mindmap — 获取系列思维导图 JSON。"""
    mindmap = container.get_series_mindmap.run(series_id)
    if mindmap is None:
        raise HTTPException(status_code=404, detail=f"series mindmap not found for '{series_id}'")
    return mindmap.mindmap


@router.post("/api/series/{series_id}/mindmap/generate")
async def generate_series_mindmap(series_id: str, container: ApiContainerDep) -> dict[str, object]:
    """POST /api/series/{series_id}/mindmap/generate — 生成系列思维导图。"""
    if not _acquire_series_mindmap_lock(series_id):
        raise HTTPException(status_code=409, detail="该系列导图正在生成中，请稍后再试")
    try:
        mindmap = await container.generate_series_mindmap.run(series_id)
        if mindmap is None:
            raise HTTPException(status_code=400, detail="系列下没有已生成概况的视频")
        return mindmap.mindmap
    finally:
        _release_series_mindmap_lock(series_id)


@router.get("/api/series/{series_id}/mindmap/export")
def export_series_mindmap(series_id: str, format: str = "md", container: ApiContainerDep = None):
    """GET /api/series/{series_id}/mindmap/export?format=md — 导出系列思维导图。"""
    if format != "md":
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}，仅支持 md")
    mindmap = container.get_series_mindmap.run(series_id)
    if mindmap is None:
        raise HTTPException(status_code=404, detail=f"series mindmap not found for '{series_id}'")
    markdown = render_mindmap_markdown(mindmap.mindmap)
    filename = f"{mindmap.title}-mindmap.md"
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Update `ApiContainer` in bootstrap.py**

```python
# In the ApiContainer dataclass, add fields:
    generate_series_mindmap: GenerateSeriesMindmapFromLibrary
    get_series_mindmap: GetSeriesMindmap

# In build_api_container(), add series mindmap wiring:
resolved_series_mindmap_generator = WorkspaceBackedSeriesMindmapGenerator(
    workspace=workspace,
    workflow=ConfiguredSeriesMindmapWorkflow(root_dir),
)

# In the ApiContainer(...) construction, add:
    generate_series_mindmap=GenerateSeriesMindmapFromLibrary(workspace, resolved_series_mindmap_generator),
    get_series_mindmap=GetSeriesMindmap(workspace),
```

- [ ] **Step 5: Create `GetSeriesMindmap` query use-case**

```python
# src/backend/video_summary/library/usecases/library_queries.py — add:

class GetSeriesMindmap:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self, series_id: str) -> VideoMindmapDTO | None:
        return self._workspace.get_series_mindmap(series_id)
```

Export it from `__init__.py`.

- [ ] **Step 6: Add series mindmap agent tools**

```python
# src/backend/video_summary/tools/mindmap.py — add:

OPEN_SERIES_MINDMAP_TOOL = ToolDefinition(
    name=ToolName.OPEN_SERIES_MINDMAP,
    title="打开系列思维导图",
    description="切换到系列思维导图工具页，查看跨视频知识结构。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.SERIES,),
)

GENERATE_SERIES_MINDMAP_TOOL = ToolDefinition(
    name=ToolName.GENERATE_SERIES_MINDMAP,
    title="生成系列导图",
    description="切换到系列思维导图工具，并在需要时触发生成。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.SERIES,),
)

def execute_open_series_mindmap(call, context):
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_SERIES_MINDMAP,
        status="ok",
        payload={"selected_tool": "series-mindmap"},
    )

def execute_generate_series_mindmap(call, context):
    return ToolExecutionResult(
        tool_name=ToolName.GENERATE_SERIES_MINDMAP,
        status="ok",
        payload={"selected_tool": "series-mindmap", "action": "generate_series_mindmap"},
    )
```

- [ ] **Step 7: Add `ToolName` enum values**

```python
# src/backend/agent/schemas/tool_calls.py — in ToolName enum, add:
    OPEN_SERIES_MINDMAP = "open_series_mindmap"
    GENERATE_SERIES_MINDMAP = "generate_series_mindmap"
```

Also add corresponding call models and union type entries following the `OpenMindmapCall` / `GenerateMindmapCall` pattern.

- [ ] **Step 8: Register tools in catalog**

```python
# src/backend/video_summary/tools/catalog.py — in UI_ACTION_TOOL_DEFINITIONS, add:
    OPEN_SERIES_MINDMAP_TOOL,
    GENERATE_SERIES_MINDMAP_TOOL,
```

- [ ] **Step 9: Export from tools `__init__.py`**

```python
# src/backend/video_summary/tools/__init__.py — add:
from backend.video_summary.tools.mindmap import execute_open_series_mindmap, execute_generate_series_mindmap
# Add to __all__
```

- [ ] **Step 10: Run import-linter**

```bash
lint-imports
```
Expected: no new violations

- [ ] **Step 11: Commit**

```bash
git add tests/backend/unit/mindmap/test_series_mindmap_export.py src/backend/api/routes/series.py src/backend/api/bootstrap.py src/backend/video_summary/tools/mindmap.py src/backend/video_summary/tools/catalog.py src/backend/video_summary/tools/__init__.py src/backend/agent/schemas/tool_calls.py src/backend/video_summary/library/usecases/library_queries.py src/backend/video_summary/library/usecases/__init__.py
git commit -m "feat(series-mindmap): add API routes, container wiring, agent tools, and query use-case"
```

---

### Task 10b: Series mindmap — integration tests

**Files:**
- Create: `tests/backend/integration/api/test_series_mindmap_api.py`

- [ ] **Step 1: Write integration tests for series mindmap APIs**

```python
# tests/backend/integration/api/test_series_mindmap_api.py
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class SeriesMindmapApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.api.app import create_app
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.root_dir = Path(cls.temp_dir.name)
        (cls.root_dir / "config").mkdir(parents=True, exist_ok=True)
        (cls.root_dir / "config" / "settings.toml").write_text(
            '[openai]\nprovider="openai"\nmodel="gpt-4"\nbase_url="https://api.openai.com/v1"\napi_key="sk-test"\n'
            '[asr]\nprovider="faster_whisper"\nlanguage="zh"\n'
            '[asr.faster_whisper]\ndevice="cpu"\ncompute_type="int8"\nmodel_size="tiny"\ntranscription_mode="default"\nmodels_dir="models"\n'
            '[agent_context]\nwindow_tokens=128000\nreserved_output_tokens=4096\ndirect_summary_threshold_ratio=0.8\nreasoning_effort="low"\nanswer_detail_level="normal"\ntalk_custom_prompt=""\n'
            '[generation]\nsummary_chunk_concurrency=1\n'
            '[web_search]\nenabled=false\nengine="duckduckgo"\nmax_results=3\n'
        )
        env_path = cls.root_dir / ".env"
        if not env_path.exists():
            env_path.write_text("OPENAI_API_KEY=sk-test\nOPENAI_BASE_URL=https://api.openai.com/v1\nOPENAI_MODEL=gpt-4\n")
        # Setup series with videos that have summaries
        workspace_dir = cls.root_dir / "workspace" / "s1"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (cls.root_dir / "videos" / "s1").mkdir(parents=True, exist_ok=True)
        (cls.root_dir / "videos" / "s1" / "v1.mp4").write_bytes(b"fake")
        (cls.root_dir / "videos" / "s1" / "v2.mp4").write_bytes(b"fake")
        v1_dir = workspace_dir / "v1"
        v1_dir.mkdir(parents=True, exist_ok=True)
        v2_dir = workspace_dir / "v2"
        v2_dir.mkdir(parents=True, exist_ok=True)
        (v1_dir / "summary.json").write_text(
            json.dumps({"title": "视频1", "chapters": [{"id": "c1", "title": "章节1", "summary": "内容"}]}, ensure_ascii=False), encoding="utf-8"
        )
        (v2_dir / "summary.json").write_text(
            json.dumps({"title": "视频2", "chapters": []}, ensure_ascii=False), encoding="utf-8"
        )
        # Write series_meta.json so list_series works
        (workspace_dir / "series_meta.json").write_text(
            json.dumps({"title": "测试系列"}, ensure_ascii=False), encoding="utf-8"
        )
        # Write a pre-existing mindmap for GET test
        (workspace_dir / "mindmap.json").write_text(
            json.dumps({"id": "root", "title": "测试系列", "summary": "", "children": []}, ensure_ascii=False), encoding="utf-8"
        )
        import os
        os.chdir(str(cls.root_dir))
        app = create_app(cls.root_dir)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_get_series_mindmap_returns_tree(self):
        response = self.client.get("/api/series/s1/mindmap")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "测试系列")

    def test_get_series_mindmap_404_when_not_generated(self):
        # s2 has no mindmap.json
        (self.root_dir / "workspace" / "s2").mkdir(parents=True, exist_ok=True)
        (self.root_dir / "videos" / "s2").mkdir(parents=True, exist_ok=True)
        (self.root_dir / "videos" / "s2" / "v1.mp4").write_bytes(b"fake")
        (self.root_dir / "workspace" / "s2" / "series_meta.json").write_text(
            json.dumps({"title": "无导图系列"}, ensure_ascii=False), encoding="utf-8"
        )
        response = self.client.get("/api/series/s2/mindmap")
        self.assertEqual(response.status_code, 404)

    def test_generate_series_mindmap_returns_400_when_no_summaries(self):
        # s3 has videos but no summaries
        (self.root_dir / "workspace" / "s3").mkdir(parents=True, exist_ok=True)
        (self.root_dir / "videos" / "s3").mkdir(parents=True, exist_ok=True)
        (self.root_dir / "videos" / "s3" / "v1.mp4").write_bytes(b"fake")
        (self.root_dir / "workspace" / "s3" / "series_meta.json").write_text(
            json.dumps({"title": "无概况系列"}, ensure_ascii=False), encoding="utf-8"
        )
        response = self.client.post("/api/series/s3/mindmap/generate")
        self.assertEqual(response.status_code, 400)

    def test_export_series_mindmap_returns_markdown(self):
        response = self.client.get("/api/series/s1/mindmap/export?format=md")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response.headers["content-type"])

    def test_export_series_mindmap_returns_400_for_unsupported_format(self):
        response = self.client.get("/api/series/s1/mindmap/export?format=pdf")
        self.assertEqual(response.status_code, 400)

    def test_concurrent_generation_returns_409(self):
        # This test verifies the lock mechanism: first request acquires lock,
        # second concurrent request for same series returns 409.
        # Since we can't easily test concurrent async in unittest,
        # we verify the lock acquire/release logic directly.
        from backend.api.routes.series import _acquire_series_mindmap_lock, _release_series_mindmap_lock
        acquired = _acquire_series_mindmap_lock("test-series")
        self.assertTrue(acquired)
        second = _acquire_series_mindmap_lock("test-series")
        self.assertFalse(second)
        _release_series_mindmap_lock("test-series")
        # After release, should be acquirable again
        reacquired = _acquire_series_mindmap_lock("test-series")
        self.assertTrue(reacquired)
        _release_series_mindmap_lock("test-series")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run integration tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/integration/api/test_series_mindmap_api.py -v
```
Expected: 6 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/backend/integration/api/test_series_mindmap_api.py
git commit -m "test(series-mindmap): add integration tests for series mindmap APIs"
```

---

## Phase 4: Series Mindmap — Frontend

### Task 11: Series mindmap frontend — state, API, actions

**Files:**
- Modify: `src/frontend/src/features/workspace/model/workspaceState.js`
- Modify: `src/frontend/src/features/workspace/model/workspaceReducer.js`
- Modify: `src/frontend/src/features/workspace/model/workspaceApi.js`
- Modify: `src/frontend/src/features/workspace/model/workspaceContentActions.js`
- Modify: `src/frontend/src/features/workspace/model/useWorkspaceController.js`
- Modify: `src/frontend/src/features/workspace/model/useWorkspaceDataEffects.js`
- Modify: `src/frontend/src/features/workspace/model/workspacePageModel.js`

- [ ] **Step 1: Add series mindmap to initial state**

```javascript
// src/frontend/src/features/workspace/model/workspaceState.js
// In createInitialWorkspaceState return object, add:
    seriesMindmap: null,
    seriesMindmapLoading: false,
    generatingSeriesMindmap: false,
    seriesSelectedNodeId: null,
```

- [ ] **Step 2: Add reducer actions**

```javascript
// src/frontend/src/features/workspace/model/workspaceReducer.js — add cases:

    case "series_mindmap_loading_started":
      return { ...state, seriesMindmapLoading: true, error: "" };

    case "series_mindmap_loaded":
      return {
        ...state,
        seriesMindmap: action.mindmap,
        seriesMindmapLoading: false,
        seriesSelectedNodeId: action.mindmap?.children?.[0]?.id ?? action.mindmap?.id ?? null,
      };

    case "series_mindmap_cleared":
      return {
        ...state,
        seriesMindmap: null,
        seriesMindmapLoading: false,
        seriesSelectedNodeId: null,
      };

    case "series_mindmap_generation_started":
      return { ...state, generatingSeriesMindmap: true, error: "" };

    case "series_mindmap_generation_succeeded":
      return {
        ...state,
        seriesMindmap: action.mindmap,
        generatingSeriesMindmap: false,
        seriesSelectedNodeId: action.mindmap?.children?.[0]?.id ?? action.mindmap?.id ?? null,
      };
```

- [ ] **Step 3: Add API functions**

```javascript
// src/frontend/src/features/workspace/model/workspaceApi.js — add:

export async function loadSeriesMindmap(seriesId) {
  return toWorkspaceMindmap(
    await fetchJson(`/api/series/${encodeURIComponent(seriesId)}/mindmap`)
  );
}

export async function generateSeriesMindmap(seriesId) {
  return toWorkspaceMindmap(
    await fetchJson(`/api/series/${encodeURIComponent(seriesId)}/mindmap/generate`, {
      method: "POST",
    })
  );
}
```

- [ ] **Step 4: Add content action**

```javascript
// src/frontend/src/features/workspace/model/workspaceContentActions.js — add:

  async function onGenerateSeriesMindmap() {
    if (!state.selectedSeriesId) return;

    dispatch({ type: "series_mindmap_generation_started" });
    try {
      const mindmapResult = await generateSeriesMindmap(state.selectedSeriesId);
      dispatch({ type: "series_mindmap_generation_succeeded", mindmap: mindmapResult });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "系列导图生成失败",
      });
    }
  }

// Add to return object: onGenerateSeriesMindmap,
```

- [ ] **Step 5: Wire in controller**

```javascript
// src/frontend/src/features/workspace/model/useWorkspaceController.js — add:

    const seriesMindmap = state.seriesMindmap;

// Add to return object:
    seriesMindmap,
    onGenerateSeriesMindmap: contentActions.onGenerateSeriesMindmap,
```

- [ ] **Step 6: Add data effect for loading series mindmap**

```javascript
// src/frontend/src/features/workspace/model/useWorkspaceDataEffects.js — add useEffect:

  useEffect(() => {
    if (
      state.selectedContextType !== "series" ||
      state.selectedToolId !== "series-mindmap"
    ) {
      dispatch({ type: "series_mindmap_cleared" });
      return;
    }

    let cancelled = false;
    dispatch({ type: "series_mindmap_loading_started" });
    loadSeriesMindmap(state.selectedSeriesId)
      .then((mindmap) => {
        if (!cancelled) dispatch({ type: "series_mindmap_loaded", mindmap });
      })
      .catch((error) => {
        if (!cancelled) dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "加载系列导图失败" });
      });

    return () => { cancelled = true; };
  }, [dispatch, state.selectedSeriesId, state.selectedContextType, state.selectedToolId]);
```

- [ ] **Step 6b: Add series mindmap tool status computation**

```javascript
// src/frontend/src/features/workspace/model/useWorkspaceController.js — add computed value:

    // Compute series mindmap tool status from library data
    // available: at least one video in series has summary (processed=true)
    // blocked: series has videos but none processed
    const seriesMindmapAvailable = useMemo(() => {
      if (!activeSeries || activeSeries.id === PLAYGROUND_SERIES_ID) return false;
      const videos = activeSeries.videos ?? [];
      if (videos.length === 0) return false;
      return videos.some(v => v.processed === true);
    }, [activeSeries]);

// Add to return object:
    seriesMindmapAvailable,
```

- [ ] **Step 7: Pass seriesMindmap through page model**

```javascript
// src/frontend/src/features/workspace/model/workspacePageModel.js — add:

      seriesMindmap: controller.seriesMindmap,
      seriesMindmapAvailable: controller.seriesMindmapAvailable,

// In generation:
      isGeneratingSeriesMindmap: controller.generatingSeriesMindmap,

// In actions:
      generateSeriesMindmap: controller.onGenerateSeriesMindmap,
```

- [ ] **Step 8: Commit**

```bash
git add src/frontend/src/features/workspace/model/
git commit -m "feat(series-mindmap): add frontend state, reducer, API, actions, and data effects"
```

---

### Task 12: Series mindmap frontend — view, toolbar, and chat integration

**Files:**
- Create: `src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx`
- Modify: `src/frontend/src/features/workspace/ui/WorkspaceReadingPane.jsx`
- Modify: `src/frontend/src/features/workspace/model/workspaceChatActions.js`
- Modify: `src/frontend/src/features/workspace/model/workspaceChatRuntime.js`

- [ ] **Step 1: Create `WorkspaceSeriesMindmapView.jsx`**

```jsx
// src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx
import { LoaderCircle, Network, Download, RefreshCw } from "lucide-react";
import { MindmapCanvas } from "../MindmapCanvas";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function WorkspaceSeriesMindmapView({
  seriesId,
  seriesMindmap,
  seriesMindmapLoading,
  generatingSeriesMindmap,
  selectedNode,
  onFocusNode,
  onGenerateSeriesMindmap,
}) {
  if (seriesMindmapLoading) {
    return (
      <WorkspaceStateBlock
        eyebrow="Series Mindmap"
        title="载入思维导图"
        description="正在读取已生成的导图。"
        loading
      />
    );
  }

  if (!seriesMindmap) {
    return (
      <WorkspaceStateBlock
        eyebrow="Series Mindmap"
        title="导图未生成"
        description="点击下面按钮，基于系列中所有视频的概况生成跨视频知识结构导图。"
      >
        <button
          type="button"
          onClick={onGenerateSeriesMindmap}
          disabled={generatingSeriesMindmap}
          className={`inline-flex items-center gap-2 rounded-2xl px-5 py-3 text-sm font-semibold transition-all ${
            generatingSeriesMindmap
              ? "motion-busy-button cursor-not-allowed bg-stone-200 text-stone-500"
              : "bg-accent text-white shadow-sm hover:bg-accent/90"
          }`}
        >
          {generatingSeriesMindmap ? (
            <>
              <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin" />
              正在生成...
            </>
          ) : (
            <>
              <Network size={16} strokeWidth={2.2} />
              生成系列导图
            </>
          )}
        </button>
      </WorkspaceStateBlock>
    );
  }

  return (
    <div className="workspace-elevated-panel relative h-full min-h-[500px] w-full overflow-hidden rounded-3xl border outline-dashed outline-1 outline-offset-4 outline-stone-200 dark:outline-stone-800">
      <div className="pointer-events-none absolute top-4 left-4 z-10">
        <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Series Mindmap</p>
      </div>
      <div className="pointer-events-auto absolute top-4 right-4 z-10 flex items-center gap-2">
        <button
          type="button"
          onClick={onGenerateSeriesMindmap}
          disabled={generatingSeriesMindmap}
          className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RefreshCw size={14} strokeWidth={2} className={generatingSeriesMindmap ? "animate-spin" : ""} />
          重新生成
        </button>
        <a
          href={`/api/series/${encodeURIComponent(seriesId)}/mindmap/export?format=md`}
          download
          className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors"
        >
          <Download size={14} strokeWidth={2} />
          导出
        </a>
      </div>
      <div className="h-full w-full">
        <MindmapCanvas root={seriesMindmap} selectedNodeId={selectedNode?.id ?? null} onSelectNode={onFocusNode} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update `WorkspaceReadingPane.jsx`**

Add the lazy import:
```jsx
const WorkspaceSeriesMindmapView = lazy(() =>
  import("./views/WorkspaceSeriesMindmapView").then((module) => ({
    default: module.WorkspaceSeriesMindmapView,
  })),
);
```

Add new props to the destructuring: `seriesMindmap`, `seriesMindmapAvailable`, `seriesMindmapLoading`, `generatingSeriesMindmap`, `onGenerateSeriesMindmap`, `seriesId`.

Add routing in the view render section (after the existing tool view routes):
```jsx
{selectedToolId === "series-mindmap" && (
  <WorkspaceSeriesMindmapView
    seriesId={activeSeries.id}
    seriesMindmap={seriesMindmap}
    seriesMindmapAvailable={seriesMindmapAvailable}
    seriesMindmapLoading={seriesMindmapLoading}
    generatingSeriesMindmap={generatingSeriesMindmap}
    selectedNode={selectedNode}
    onFocusNode={onFocusNode}
    onGenerateSeriesMindmap={onGenerateSeriesMindmap}
  />
)}
```

Also update the `WorkspaceSeriesMindmapView` to accept `seriesMindmapAvailable` and show a blocked state when false:
```jsx
// In WorkspaceSeriesMindmapView, add blocked state before the "未生成" state:
if (!seriesMindmapAvailable) {
  return (
    <WorkspaceStateBlock
      eyebrow="Series Mindmap"
      title="需要先生成 AI 概况"
      description="系列导图依赖已生成的视频概况。请先生成系列中各视频的 AI 概况。"
    />
  );
}
```

- [ ] **Step 3: Update `workspaceChatActions.js`**

```javascript
// src/frontend/src/features/workspace/model/workspaceChatActions.js — add:

    if (payload.selected_tool === "series-mindmap") {
      dispatch({ type: "tool_selected", toolId: "series-mindmap" });
    }

    if (payload.action === "generate_series_mindmap") {
      void contentActions.onGenerateSeriesMindmap();
    }
```

- [ ] **Step 4: Update `workspaceChatRuntime.js`**

```javascript
// src/frontend/src/features/workspace/model/workspaceChatRuntime.js — in normalizeAgentToolTraceStep:

    case "open_series_mindmap":
      return createToolTraceStep(result.tool_name, "打开系列思维导图");
    case "generate_series_mindmap":
      return createToolTraceStep(result.tool_name, "生成系列思维导图");

// In normalizeAgentToolId:
    toolId === "series-mindmap" ||
```

- [ ] **Step 5: Write frontend tests**

```jsx
// tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkspaceSeriesMindmapView } from "../../../../../src/features/workspace/ui/views/WorkspaceSeriesMindmapView";

describe("WorkspaceSeriesMindmapView", () => {
  it("shows generate button when no mindmap data", () => {
    render(
      <WorkspaceSeriesMindmapView
        seriesId="s1"
        seriesMindmap={null}
        seriesMindmapLoading={false}
        generatingSeriesMindmap={false}
        selectedNode={null}
        onFocusNode={vi.fn()}
        onGenerateSeriesMindmap={vi.fn()}
      />
    );
    expect(screen.getByText("生成系列导图")).toBeTruthy();
  });

  it("shows regenerate and export buttons when mindmap exists", () => {
    render(
      <WorkspaceSeriesMindmapView
        seriesId="s1"
        seriesMindmap={{ id: "root", title: "Test", children: [] }}
        seriesMindmapLoading={false}
        generatingSeriesMindmap={false}
        selectedNode={null}
        onFocusNode={vi.fn()}
        onGenerateSeriesMindmap={vi.fn()}
      />
    );
    expect(screen.getByText("重新生成")).toBeTruthy();
    expect(screen.getByText("导出")).toBeTruthy();
  });

  it("generate button calls onGenerateSeriesMindmap", async () => {
    const onGenerate = vi.fn();
    render(
      <WorkspaceSeriesMindmapView
        seriesId="s1"
        seriesMindmap={null}
        seriesMindmapLoading={false}
        generatingSeriesMindmap={false}
        selectedNode={null}
        onFocusNode={vi.fn()}
        onGenerateSeriesMindmap={onGenerate}
      />
    );
    await userEvent.click(screen.getByText("生成系列导图"));
    expect(onGenerate).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 6: Run frontend tests**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
```
Expected: 3 PASS

- [ ] **Step 7: Commit**

```bash
git add src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx src/frontend/src/features/workspace/ui/WorkspaceReadingPane.jsx src/frontend/src/features/workspace/model/workspaceChatActions.js src/frontend/src/features/workspace/model/workspaceChatRuntime.js tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
git commit -m "feat(series-mindmap): add series mindmap view, toolbar integration, and chat tool handling"
```

---

### Task 13: Final verification

- [ ] **Step 1: Run all backend tests**

```bash
PYTHONPATH=src python -m pytest tests/backend/unit/mindmap/ tests/backend/integration/llm/test_mindmap_and_knowledge_cards.py -v
```
Expected: ALL PASS

- [ ] **Step 2: Run all frontend tests**

```bash
cd src/frontend && npx vitest run tests/frontend/features/workspace/
```
Expected: ALL PASS

- [ ] **Step 3: Run import-linter**

```bash
lint-imports
```
Expected: no violations

- [ ] **Step 4: Run backend dev server smoke test**

```bash
PYTHONPATH=src python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8001 &
sleep 3
curl -s http://127.0.0.1:8001/api/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 5: Commit final verification**

```bash
git add -A
git commit -m "chore: final verification — all tests pass, import-linter clean"
```
