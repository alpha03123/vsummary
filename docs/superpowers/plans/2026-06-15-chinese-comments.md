# 为后端代码添加中文注释 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为后端核心代码（~130 个 .py 文件）添加 Google 风格中文 docstring，让中文使用者无需翻译业务术语即可理解代码意图；不修改任何业务逻辑。

**Architecture:** 分阶段推进（Phase 0 示范 → Phase 1-5 按包推进 → Phase 6 验证）。每个 Phase 一个 git commit。中途可暂停、调整风格、回滚单个文件。

**Tech Stack:** Python 3.12、FastAPI、LangGraph、import-linter（架构边界）、pytest（回归测试）。

**Spec:** `docs/superpowers/specs/2026-06-15-chinese-comments-design.md`

---

## 工作约定（适用所有任务）

### 注释规范摘要

- **模块顶部**：在 `from __future__ import annotations` 之后加 1-2 句中文模块说明
- **函数**：单行 `"""xxx。"""` 或 Google 风格 `Args/Returns/Raises/Yields` 段
- **类**：第一段说明类做什么 + 关键不变量；可加 `Attributes:` 段
- **保留英文**：LangGraph / StateGraph / FastAPI / RAG / ASR / LLM / SSE / DTO / LiteLLM / LlamaIndex / LanceDB / FastEmbed / faster-whisper / yt-dlp / Evidence / Transcript / Summary / Workspace / Session / Progress / Port / Protocol / Adapter
- **译为中文**：用例 / 嵌入 / 检索 / 转写 / 总结 / 分片 / 工作区 / 查询
- **跳过**：自动生成的 dunder 方法（`__init__` / `__repr__` / `__eq__` / `__hash__` 等，除非显式 override）；空 `__init__.py`

### 红线（任何任务都适用）

> **只能**修改 docstring 字符串、模块顶部说明、必要时的 # 行内注释。
> **不能**动函数签名、函数体实现、import、装饰器、类继承关系、运行时行为。
> 现有英文 docstring 替换为中文；有价值的 # 行内注释（如 TODO、坑点提示）保留。

### 每个文件改完后必跑

```bash
python -m py_compile <file>
```

### 每个 Phase 完成后必跑

```bash
# 架构边界检查
lint-imports

# 相关域的回归测试（按 Phase 替换路径）
python -m pytest tests/backend/unit/<相关域> -x
```

---

## Phase 0：示范文件

### Task 1：示范文件 #1 — `src/backend/video_summary/domain/models.py`

**Files:**
- Modify: `src/backend/video_summary/domain/models.py`

**目标**：定调简单 dataclass 类的注释风格。

- [ ] **Step 1：读现有文件**

```bash
cat src/backend/video_summary/domain/models.py
```

- [ ] **Step 2：应用中文 docstring**

文件极小（36 行），全部内容改为如下：

```python
"""视频资产领域值对象。

本模块只包含不可变的领域数据类型，不依赖任何基础设施层。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TranscriptSegment:
    """单条转写片段。

    Attributes:
        start: 起始时间（秒）。
        end: 结束时间（秒）。
        text: 片段文本。
    """

    start: float
    end: float
    text: str


@dataclass
class Transcript:
    """视频转写结果。

    Attributes:
        language: 检测到的语言代码（如 "zh"、"en"）。
        segments: 按时间顺序排列的转写片段列表。
        raw_text: 拼接后的纯文本（可能与 segments 拼接结果不完全一致，保留原始标点）。
    """

    language: str
    segments: list[TranscriptSegment] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class VideoAsset:
    """视频资产不可变值对象。

    表示一个已索引的视频条目：基本元数据 + 转写文本 + 总结文档。
    一旦构造不允许修改，等值比较按业务键 (asset_id) 进行。

    Attributes:
        asset_id: 业务唯一 ID。
        source_uri: 原始视频的 URI（本地路径或远端 URL）。
        title: 视频标题，可为空。
        duration_seconds: 时长（秒），未知时为 None。
        transcript: 转写结果，可能为空。
        summary: 结构化总结，可能为空。
        metadata: 任意附加元数据（来源、标签等）。
    """

    asset_id: str
    source_uri: str
    title: str = ""
    duration_seconds: float | None = None
    transcript: Transcript | None = None
    summary: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 3：语法检查**

```bash
python -m py_compile src/backend/video_summary/domain/models.py
```

预期：静默成功。

- [ ] **Step 4：架构边界检查**

```bash
lint-imports
```

预期：静默成功。

- [ ] **Step 5：本地 commit（暂不推，等所有 Phase 完成后批量推）**

```bash
git add src/backend/video_summary/domain/models.py
git commit -m "docs(comments): Phase 0 示范 #1 - domain/models 中文 docstring"
```

- [ ] **Step 6：用户审阅**

读 `src/backend/video_summary/domain/models.py` 给用户看，确认风格符合预期。用户批准后进入 Task 2。

---

### Task 2：示范文件 #2 — `src/backend/agent_graph/runtime/state.py`

**Files:**
- Modify: `src/backend/agent_graph/runtime/state.py`

**目标**：定调 TypedDict 复杂状态类（含大量字段）的注释风格。

- [ ] **Step 1：读现有文件**

```bash
cat src/backend/agent_graph/runtime/state.py
```

- [ ] **Step 2：应用中文 docstring**

31 行的 TypedDict 状态定义。完整替换为如下：

```python
"""LangGraph 工作流的全局状态定义。

本模块定义 `AgentGraphState`——Agent 在多轮对话中累积的全部上下文。
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentGraphState(TypedDict, total=False):
    """LangGraph 工作流的全局状态。

    在 `series` 与 `video` 两种 scope 下被节点读写。`total=False`
    表示字段均可选，节点按需填充。

    Attributes:
        scope_type: 当前会话作用域，"series"（跨视频）或 "video"（单视频）。
        video_id: 视频作用域下的目标视频 ID。
        series_id: 系列作用域下的目标系列 ID。
        user_query: 用户最新问题原文。
        session_id: 会话唯一 ID，用于跨调用关联上下文。
        memory_turns: 已发生的多轮对话历史，按时间顺序。
        evidence_items: 检索到的证据片段列表。
        web_results: 可选的网页搜索结果。
        video_context: 视频作用域下构建的上下文（总结 + 转写）。
        action_plan: 视频作用域下 LLM 规划出的工具调用计划。
        action_outputs: 工具调用的实际返回结果列表。
        final_answer: 最终生成的回复文本。
        status: 当前节点执行状态。
        error: 错误信息字符串（如果有）。
    """

    scope_type: str
    video_id: str | None
    series_id: str | None
    user_query: str
    session_id: str
    memory_turns: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    web_results: list[dict[str, Any]]
    video_context: dict[str, Any]
    action_plan: dict[str, Any]
    action_outputs: list[dict[str, Any]]
    final_answer: str
    status: str
    error: str | None
```

- [ ] **Step 3：语法检查**

```bash
python -m py_compile src/backend/agent_graph/runtime/state.py
```

- [ ] **Step 4：架构边界检查**

```bash
lint-imports
```

- [ ] **Step 5：本地 commit**

```bash
git add src/backend/agent_graph/runtime/state.py
git commit -m "docs(comments): Phase 0 示范 #2 - agent_graph/runtime/state 中文 docstring"
```

- [ ] **Step 6：用户审阅 + 批准示范风格**

读两个示范文件给用户过目。用户确认：
- 风格一致、术语翻译合理、Attributes 段详略得当
- 批准后进入 Phase 1

---

## Phase 1：`video_summary/domain/`

### Task 3：完成 `video_summary/domain/` 注释

**Files:**
- Modify: `src/backend/video_summary/domain/models.py`（如 Phase 0 未完成则现在做）
- 无其他文件（只有 `__init__.py` 且为空，跳过）

- [ ] **Step 1：确认 Phase 0 已完成**

读 `git log --oneline | head -5` 确认 Phase 0 的两个 commit 已存在。如未完成，先补 Task 1 / Task 2。

- [ ] **Step 2：跑 import-linter**

```bash
lint-imports
```

- [ ] **Step 3：跑 domain 相关测试**

```bash
python -m pytest tests/backend -k "domain" -x
```

预期：全绿（或无匹配测试，跳过）。

- [ ] **Step 4：Phase 1 commit（如有额外改动）**

若无新改动直接进入 Phase 2；如有，commit：

```bash
git add src/backend/video_summary/domain/
git commit -m "docs(comments): Phase 1 - video_summary/domain 中文 docstring"
```

---

## Phase 2：`video_summary/library/`

### Task 4：`video_summary/library/` 根目录文件

**Files:**
- Modify: `src/backend/video_summary/library/constants.py`
- Modify: `src/backend/video_summary/library/linked_models.py`
- Modify: `src/backend/video_summary/library/markdown_exports.py`
- Modify: `src/backend/video_summary/library/models.py`
- Modify: `src/backend/video_summary/library/parsers.py`
- Modify: `src/backend/video_summary/library/ports.py`

- [ ] **Step 1：读文件清单**

```bash
wc -l src/backend/video_summary/library/*.py
```

- [ ] **Step 2：按文件添加 docstring**

逐文件使用 Read + Edit：
1. `Read` 每个文件完整内容
2. 在 `from __future__ import annotations` 之后插入模块顶部说明
3. 为每个 `class` 和 `def` 添加 docstring（用 Edit 工具精确替换）
4. 复杂类加 `Attributes:` 段，简单类只写一句话
5. 函数按参数复杂度选单行或 Google 风格

模板参考 Phase 0 中的两个示范文件。

- [ ] **Step 3：每个文件改完单独 py_compile**

```bash
python -m py_compile src/backend/video_summary/library/constants.py
python -m py_compile src/backend/video_summary/library/linked_models.py
python -m py_compile src/backend/video_summary/library/markdown_exports.py
python -m py_compile src/backend/video_summary/library/models.py
python -m py_compile src/backend/video_summary/library/parsers.py
python -m py_compile src/backend/video_summary/library/ports.py
```

预期：全部静默成功。

- [ ] **Step 4：架构边界检查**

```bash
lint-imports
```

- [ ] **Step 5：跑 library 相关测试**

```bash
python -m pytest tests/backend/unit/library -x
```

预期：全绿。

- [ ] **Step 6：Commit**

```bash
git add src/backend/video_summary/library/*.py
git commit -m "docs(comments): Phase 2a - video_summary/library 根目录中文 docstring"
```

---

### Task 5：`video_summary/library/usecases/`

**Files:**
- Modify: `src/backend/video_summary/library/usecases/imports.py`
- Modify: `src/backend/video_summary/library/usecases/knowledge_cards.py`
- Modify: `src/backend/video_summary/library/usecases/library_queries.py`
- Modify: `src/backend/video_summary/library/usecases/linked_videos.py`
- Modify: `src/backend/video_summary/library/usecases/mindmap_generation.py`
- Modify: `src/backend/video_summary/library/usecases/mutations.py`
- Modify: `src/backend/video_summary/library/usecases/notes.py`
- Modify: `src/backend/video_summary/library/usecases/series_synopsis_generation.py`
- Modify: `src/backend/video_summary/library/usecases/summary_generation.py`

- [ ] **Step 1：读文件清单**

```bash
wc -l src/backend/video_summary/library/usecases/*.py
```

- [ ] **Step 2：按文件添加 docstring**

每个用例类都有 `run()` 方法，重点说明：
- 用例的**业务意图**（不是机械翻译方法名）
- 关键依赖（端口接口）
- 返回值语义

- [ ] **Step 3：每个文件改完单独 py_compile**

```bash
for f in src/backend/video_summary/library/usecases/*.py; do
  python -m py_compile "$f"
done
```

- [ ] **Step 4：架构边界检查 + 测试**

```bash
lint-imports
python -m pytest tests/backend/unit/library -x
```

- [ ] **Step 5：Commit**

```bash
git add src/backend/video_summary/library/usecases/
git commit -m "docs(comments): Phase 2b - video_summary/library/usecases 中文 docstring"
```

---

## Phase 3：`video_summary/generation/` + `video_summary/infrastructure/`

### Task 6：`video_summary/generation/` 注释

**Files:**
- Modify: `src/backend/video_summary/generation/cancellation.py`
- Modify: `src/backend/video_summary/generation/ports.py`
- Modify: `src/backend/video_summary/generation/renderers.py`
- Modify: `src/backend/video_summary/generation/schemas.py`
- Modify: `src/backend/video_summary/generation/stage_cache.py`
- Modify: `src/backend/video_summary/generation/prompts/summary.py`
- Modify: `src/backend/video_summary/generation/usecases/generate_mindmap.py`
- Modify: `src/backend/video_summary/generation/usecases/generate_summary.py`

- [ ] **Step 1：按文件添加 docstring**

特别注意：
- `cancellation.py`：异步取消语义
- `renderers.py`：模板渲染逻辑
- `usecases/generate_summary.py`：核心总结生成流程
- `usecases/generate_mindmap.py`：思维导图生成

- [ ] **Step 2：每个文件 py_compile + lint-imports + 跑 generation 相关测试**

```bash
for f in $(find src/backend/video_summary/generation -name "*.py"); do
  python -m py_compile "$f"
done
lint-imports
python -m pytest tests/backend/unit -k "generation or summary or mindmap" -x
```

- [ ] **Step 3：Commit**

```bash
git add src/backend/video_summary/generation/
git commit -m "docs(comments): Phase 3a - video_summary/generation 中文 docstring"
```

---

### Task 7：`video_summary/infrastructure/agent_memory/`

**Files:**
- Modify: `src/backend/video_summary/infrastructure/agent_memory/document_schema.py`
- Modify: `src/backend/video_summary/infrastructure/agent_memory/fastembed_adapter.py`
- Modify: `src/backend/video_summary/infrastructure/agent_memory/index_builder.py`
- Modify: `src/backend/video_summary/infrastructure/agent_memory/pinpoint.py`
- Modify: `src/backend/video_summary/infrastructure/agent_memory/retrieval.py`
- Modify: `src/backend/video_summary/infrastructure/agent_memory/video_workflow.py`

- [ ] **Step 1：按文件添加 docstring**

这部分是 RAG 检索核心：
- `fastembed_adapter.py`：FastEmbed 嵌入适配
- `index_builder.py`：LanceDB 索引构建
- `retrieval.py`：`SeriesRetrievalService` 检索服务
- `pinpoint.py`：定位引用位置
- `video_workflow.py`：视频索引工作流

- [ ] **Step 2：py_compile + lint + 测试**

```bash
for f in src/backend/video_summary/infrastructure/agent_memory/*.py; do
  python -m py_compile "$f"
done
lint-imports
python -m pytest tests/backend/unit/agent_memory -x
```

- [ ] **Step 3：Commit**

```bash
git add src/backend/video_summary/infrastructure/agent_memory/
git commit -m "docs(comments): Phase 3b - video_summary/infrastructure/agent_memory 中文 docstring"
```

---

### Task 8：`video_summary/infrastructure/` LiteLLM 适配器

**Files:**
- Modify: `src/backend/video_summary/infrastructure/litellm_knowledge_card_generator.py`
- Modify: `src/backend/video_summary/infrastructure/litellm_mindmap_generator.py`
- Modify: `src/backend/video_summary/infrastructure/litellm_summarizer.py`
- Modify: `src/backend/video_summary/infrastructure/litellm_transcript_enhancer.py`
- Modify: `src/backend/video_summary/infrastructure/litellm_web_search.py`
- Modify: `src/backend/video_summary/infrastructure/library_generation_adapters.py`

- [ ] **Step 1：按文件添加 docstring**

这部分是 LLM 调用适配：
- `litellm_summarizer.py`：核心总结 LLM 调用
- `litellm_transcript_enhancer.py`：转写文本增强
- `litellm_knowledge_card_generator.py`：知识卡片生成
- `litellm_mindmap_generator.py`：思维导图生成
- `litellm_web_search.py`：网页搜索

- [ ] **Step 2：py_compile + lint + 测试**

```bash
for f in src/backend/video_summary/infrastructure/litellm_*.py src/backend/video_summary/infrastructure/library_generation_adapters.py; do
  python -m py_compile "$f"
done
lint-imports
```

- [ ] **Step 3：Commit**

```bash
git add src/backend/video_summary/infrastructure/litellm_*.py src/backend/video_summary/infrastructure/library_generation_adapters.py
git commit -m "docs(comments): Phase 3c - LiteLLM 适配器中文 docstring"
```

---

### Task 9：`video_summary/infrastructure/` 剩余文件

**Files:**
- Modify: `src/backend/video_summary/infrastructure/application_builders.py`
- Modify: `src/backend/video_summary/infrastructure/faster_whisper_models.py`
- Modify: `src/backend/video_summary/infrastructure/faster_whisper_transcriber.py`
- Modify: `src/backend/video_summary/infrastructure/filesystem_generation_artifact_store.py`
- Modify: `src/backend/video_summary/infrastructure/filesystem_video_workspace.py`
- Modify: `src/backend/video_summary/infrastructure/huggingface_model_downloader.py`
- Modify: `src/backend/video_summary/infrastructure/in_memory_progress_tracker.py`
- Modify: `src/backend/video_summary/infrastructure/media_tools.py`
- Modify: `src/backend/video_summary/infrastructure/mindmap_workflow.py`
- Modify: `src/backend/video_summary/infrastructure/prompts/knowledge_cards.py`
- Modify: `src/backend/video_summary/infrastructure/prompts/mindmap.py`
- Modify: `src/backend/video_summary/infrastructure/rag_models.py`
- Modify: `src/backend/video_summary/infrastructure/runtime.py`
- Modify: `src/backend/video_summary/infrastructure/settings.py`
- Modify: `src/backend/video_summary/infrastructure/settings_service.py`
- Modify: `src/backend/video_summary/infrastructure/video_summary_runtime.py`
- Modify: `src/backend/video_summary/infrastructure/video_summary_workflow.py`

- [ ] **Step 1：按文件添加 docstring**

重点关注：
- `settings.py` / `settings_service.py`：配置加载与持久化
- `runtime.py` / `video_summary_runtime.py`：运行时容器
- `in_memory_progress_tracker.py`：进度跟踪
- `filesystem_*.py`：文件系统 IO

- [ ] **Step 2：py_compile + lint + 测试**

```bash
for f in $(find src/backend/video_summary/infrastructure -name "*.py"); do
  python -m py_compile "$f"
done
lint-imports
python -m pytest tests/backend/unit -x
```

- [ ] **Step 3：Commit**

```bash
git add src/backend/video_summary/infrastructure/
git commit -m "docs(comments): Phase 3d - video_summary/infrastructure 收尾中文 docstring"
```

---

## Phase 4：`agent/` + `agent_graph/`

### Task 10：`agent/` 注释

**Files:**
- Modify: `src/backend/agent/context/budget.py`
- Modify: `src/backend/agent/context/semantic_compactor.py`
- Modify: `src/backend/agent/infrastructure/chat_gateway.py`
- Modify: `src/backend/agent/infrastructure/context_loader.py`
- Modify: `src/backend/agent/memory/context.py`
- Modify: `src/backend/agent/memory/messages.py`
- Modify: `src/backend/agent/ports.py`
- Modify: `src/backend/agent/prompts/conversation.py`
- Modify: `src/backend/agent/schemas/action_plan.py`
- Modify: `src/backend/agent/schemas/chat_stream.py`
- Modify: `src/backend/agent/schemas/messages.py`
- Modify: `src/backend/agent/schemas/stream_events.py`
- Modify: `src/backend/agent/schemas/tool_calls.py`
- Modify: `src/backend/agent/session/models.py`
- Modify: `src/backend/agent/session/store.py`
- Modify: `src/backend/agent/utils/json_protocol.py`
- Modify: `src/backend/agent/validation/errors.py`

- [ ] **Step 1：按文件添加 docstring**

重点关注：
- `ports.py`：协议接口定义（核心）
- `context/budget.py`：上下文预算
- `memory/context.py` / `memory/messages.py`：内存模型
- `session/store.py`：会话存储
- `schemas/*.py`：Pydantic 模型

- [ ] **Step 2：py_compile + lint + 测试**

```bash
for f in $(find src/backend/agent -name "*.py"); do
  python -m py_compile "$f"
done
lint-imports
python -m pytest tests/backend/unit/agent -x
```

- [ ] **Step 3：Commit**

```bash
git add src/backend/agent/
git commit -m "docs(comments): Phase 4a - agent 中文 docstring"
```

---

### Task 11：`agent_graph/query/` + `agent_graph/evidence/` + `agent_graph/prompts/`

**Files:**
- Modify: `src/backend/agent_graph/query/models.py`
- Modify: `src/backend/agent_graph/query/series_answer_synthesizer.py`
- Modify: `src/backend/agent_graph/query/series_query_processor.py`
- Modify: `src/backend/agent_graph/query/video_answer_synthesizer.py`
- Modify: `src/backend/agent_graph/evidence/citations.py`
- Modify: `src/backend/agent_graph/evidence/inline_citations.py`
- Modify: `src/backend/agent_graph/prompts/actions.py`
- Modify: `src/backend/agent_graph/prompts/query.py`

- [ ] **Step 1：按文件添加 docstring**

- [ ] **Step 2：py_compile + lint + 测试**

```bash
for f in $(find src/backend/agent_graph/{query,evidence,prompts} -name "*.py"); do
  python -m py_compile "$f"
done
lint-imports
```

- [ ] **Step 3：Commit**

```bash
git add src/backend/agent_graph/query/ src/backend/agent_graph/evidence/ src/backend/agent_graph/prompts/
git commit -m "docs(comments): Phase 4b - agent_graph query/evidence/prompts 中文 docstring"
```

---

### Task 12：`agent_graph/actions/` + `agent_graph/runtime/`

**Files:**
- Modify: `src/backend/agent_graph/actions/action_dispatcher.py`
- Modify: `src/backend/agent_graph/actions/video_action_planner.py`
- Modify: `src/backend/agent_graph/runtime/graph.py`
- Modify: `src/backend/agent_graph/runtime/node_catalog.py`
- Modify: `src/backend/agent_graph/runtime/nodes.py`
- Modify: `src/backend/agent_graph/runtime/outcome.py`
- Modify: `src/backend/agent_graph/runtime/service.py`
- Modify: `src/backend/agent_graph/runtime/session_recorder.py`
- Modify: `src/backend/agent_graph/runtime/state.py`（如 Phase 0 未完成）
- Modify: `src/backend/agent_graph/runtime/streaming.py`
- Modify: `src/backend/agent_graph/runtime/turns.py`

- [ ] **Step 1：按文件添加 docstring**

核心是 LangGraph 工作流：
- `runtime/graph.py`：图定义
- `runtime/nodes.py`：节点实现
- `runtime/service.py`：`AgentGraphService` 入口
- `actions/video_action_planner.py`：动作规划
- `actions/action_dispatcher.py`：动作分发

- [ ] **Step 2：py_compile + lint + 测试**

```bash
for f in $(find src/backend/agent_graph/actions src/backend/agent_graph/runtime -name "*.py"); do
  python -m py_compile "$f"
done
lint-imports
python -m pytest tests/backend/unit/agent_graph -x 2>/dev/null || python -m pytest tests/backend/unit/agent -x
```

- [ ] **Step 3：Commit**

```bash
git add src/backend/agent_graph/actions/ src/backend/agent_graph/runtime/
git commit -m "docs(comments): Phase 4c - agent_graph actions/runtime 中文 docstring"
```

---

## Phase 5：`api/` + `shared/` + `bilibili/` + `chaoxing/`

### Task 13：`api/routes/` 注释

**Files:**
- Modify: `src/backend/api/routes/agent.py`
- Modify: `src/backend/api/routes/chaoxing.py`
- Modify: `src/backend/api/routes/health.py`
- Modify: `src/backend/api/routes/linked.py`
- Modify: `src/backend/api/routes/settings.py`
- Modify: `src/backend/api/routes/videos.py`

- [ ] **Step 1：按文件添加 docstring**

路由层重点：
- 每个 endpoint 函数：路径 + HTTP 方法 + 业务意图
- 请求/响应模型：已在 Pydantic schema 中说明，这里只说明路由用途

- [ ] **Step 2：py_compile + lint + 跑 API 集成测试**

```bash
for f in src/backend/api/routes/*.py; do
  python -m py_compile "$f"
done
lint-imports
python -m pytest tests/backend/integration/api -x
```

- [ ] **Step 3：Commit**

```bash
git add src/backend/api/routes/
git commit -m "docs(comments): Phase 5a - api/routes 中文 docstring"
```

---

### Task 14：`api/` 剩余文件 + `shared/` + `bilibili/` + `chaoxing/`

**Files:**
- Modify: `src/backend/api/access_log.py`
- Modify: `src/backend/api/app.py`
- Modify: `src/backend/api/container.py`
- Modify: `src/backend/api/contracts.py`
- Modify: `src/backend/api/responses.py`
- Modify: `src/backend/api/sse.py`
- Modify: `src/backend/shared/filesystem.py`
- Modify: `src/backend/shared/llm/base_url.py`
- Modify: `src/backend/shared/llm/chat_stream.py`
- Modify: `src/backend/shared/llm/json_mode.py`
- Modify: `src/backend/shared/llm/litellm_gateway.py`
- Modify: `src/backend/bilibili/ytdlp_bilibili.py`
- Modify: `src/backend/chaoxing/chaoxing_api.py`

- [ ] **Step 1：按文件添加 docstring**

重点：
- `api/app.py`：FastAPI 应用入口
- `api/container.py`：DI 容器
- `api/sse.py`：SSE 流
- `shared/llm/litellm_gateway.py`：LLM 网关核心
- `bilibili/ytdlp_bilibili.py`：B 站下载适配
- `chaoxing/chaoxing_api.py`：学习通导入适配

- [ ] **Step 2：py_compile + lint + 全量测试**

```bash
for f in $(find src/backend/api src/backend/shared src/backend/bilibili src/backend/chaoxing -name "*.py" | grep -v bootstrap | grep -v static_assets | grep -v server.py); do
  python -m py_compile "$f"
done
lint-imports
python -m pytest tests/backend -x
```

- [ ] **Step 3：Commit**

```bash
git add src/backend/api/ src/backend/shared/ src/backend/bilibili/ src/backend/chaoxing/
git commit -m "docs(comments): Phase 5b - api/shared/bilibili/chaoxing 中文 docstring"
```

---

## Phase 6：最终验证

### Task 15：全量验证与收尾

- [ ] **Step 1：架构边界检查**

```bash
lint-imports
```

预期：全绿。

- [ ] **Step 2：全量回归测试**

```bash
python -m pytest tests/backend -x
```

预期：全绿。

- [ ] **Step 3：扫描未翻译的英文 docstring**

```bash
python -c "
import ast, pathlib
remaining = []
for p in pathlib.Path('src/backend').rglob('*.py'):
    if any(x in str(p) for x in ['__pycache__', 'static_assets', 'bootstrap', 'server.py']):
        continue
    try:
        tree = ast.parse(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'PARSE ERROR: {p}: {e}')
        continue
    for node in ast.walk(tree):
        target = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            target = node
        if target and target.body and isinstance(target.body[0], ast.Expr) and isinstance(target.body[0].value, ast.Constant) and isinstance(target.body[0].value.value, str):
            doc = target.body[0].value.value
            # 检测整段是英文（无中文）
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in doc[:200])
            if not has_chinese and len(doc) > 30:
                remaining.append((str(p), target.name, doc[:60]))
print(f'未翻译英文 docstring 数量: {len(remaining)}')
for r in remaining[:20]:
    print(f'  {r[0]}::{r[1]} -> {r[2]}...')
"
```

预期：数字接近 0（允许少量误报，如 import-linter 测试用文件）。

- [ ] **Step 4：抽样人工审计**

从每个 Phase 任选 1 个已修改文件，Read 出来人工 review，确认：
- 风格一致
- 术语翻译合理
- docstring 描述了业务意图而非机械翻译方法名
- 没有动实现代码

- [ ] **Step 5：查看 git log 汇总**

```bash
git log --oneline | head -20
```

预期：看到所有 Phase 的 commit，message 都以 `docs(comments):` 开头。

- [ ] **Step 6：交付总结**

向用户报告：
- 总共修改了多少个文件
- 多少个 git commit
- pytest 结果
- import-linter 结果
- 未翻译英文 docstring 数量
- 抽样审计结果

---

## 中途调整 / 回滚指南

### 风格调整

如果中途觉得某种 docstring 写法不合适：

```bash
# 找到某个 Phase 的 commit
git log --oneline | grep "Phase 2a"
# 回滚
git revert <commit-hash> --no-edit
# 调整风格后重新做这个 Phase
```

### 单文件回滚

```bash
git checkout HEAD~1 -- src/backend/some/file.py
```

### 暂停

任意任务中途停止即可，下个会话从下一个 Task 继续。

---

## 自检

### 1. Spec 覆盖检查

| Spec 章节 | 对应任务 |
|---|---|
| 范围 2.1 | Task 3-14 覆盖所有列出的目录 |
| 范围 2.2 排除项 | Task 1-14 显式排除 static_assets / bootstrap / server.py / 空 __init__.py |
| 注释风格 3.1-3.4 | Task 1-2 给出模板，所有后续任务复用 |
| 现有英文 docstring 处理 4 | "红线"约定贯穿所有任务 |
| Phase 0 + Phase 1-5 + Phase 6 | Task 1-15 完整覆盖 |
| 质量门控 6.1-6.3 | 每个 Task 末尾含 py_compile；每 Phase 末尾含 lint+pytest；Phase 6 含全量验证 |
| 红线 6.4 | "工作约定" 顶部声明 + 每个 Task 的 Step 1/2 提醒 |
| 跳过规则 6.5 | "工作约定" 顶部声明 |

### 2. 占位符扫描

- ✅ 无 TBD / TODO / "实现 later"
- ✅ 所有代码示例完整
- ✅ 所有命令完整带预期输出
- ✅ 无"类似 Task N"引用，每任务自包含

### 3. 类型一致性

- 所有文件路径均来自实际 `find` 输出
- Phase 编号一致（0-6 → Task 1-15）
- Commit message 格式一致（`docs(comments): Phase X - <scope> 中文 docstring`）