# Mindmap Enhancement Design

2026-06-17 | Status: Design Approved

## Overview

Four improvements to the mindmap generation feature:

1. **Inject transcript into mindmap prompt** — fix empty/shallow mindmaps by giving the LLM the full transcript text, not just the summary
2. **Regenerate button** — allow re-triggering mindmap generation without leaving the view
3. **Export button** — download mindmap as Markdown
4. **Series-level mindmap** — cross-video knowledge structure for an entire series, based on `series_catalog.json` + per-video `summary.json`

## Current State

### Single-video mindmap flow

```
POST /api/videos/{sid}/{vid}/mindmap/generate
  -> GenerateVideoMindmapFromLibrary.run()
    -> workspace.get_video_summary()  // read summary.json
    -> generator.run(series_id, video_id, summary_data)
      -> WorkspaceBackedVideoMindmapGenerator
        -> ConfiguredMindmapWorkflow
          -> GenerateMindmap (generation use-case)
            -> LiteLLMMindmapGenerator.generate(title, duration, summary_data)
              -> build_mindmap_prompt(title, duration, summary_json)
              -> gateway.acomplete_structured(MindmapNodePayload)
            -> artifact_store.save_mindmap()  // write mindmap.json
    -> workspace.get_video_mindmap()  // read back -> VideoMindmapDTO
```

**Key problem:** `MINDMAP_PROMPT_TEMPLATE` only receives `{title}`, `{duration_seconds}`, `{summary_json}`. The LLM cannot access the original transcript, so if the summary is sparse, the mindmap is empty.

### Series catalog structure (`series_catalog.json`)

```python
class SeriesCatalogPayload:
    series_id: str
    series_title: str
    videos: list[SeriesCatalogVideoRecord]  # {video_id, title, one_sentence_summary, chapter_titles, processed}
    updated_at: str
```

### Mindmap data schema (`MindmapNodePayload`)

```python
class MindmapNodePayload(BaseModel):
    id: str
    title: str
    summary: str = ""
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    children: list[MindmapNodePayload] = []
```

Both single-video and series mindmaps use this same recursive tree schema. For series mindmaps, `start_seconds`/`end_seconds` may be 0.0 since nodes span multiple videos.

## Design

### 1. Inject transcript into mindmap prompt

**Files changed (bottom-up):**

| Layer | File | Change |
|-------|------|--------|
| infra/prompts | `mindmap.py` | Add `{transcript_text}` placeholder to `MINDMAP_PROMPT_TEMPLATE` |
| generation/ports | `ports.py` | `MindmapGenerator.generate()` adds `transcript_text: str = ""` |
| generation/usecases | `generate_mindmap.py` | `GenerateMindmap.run()` passes through `transcript_text` |
| infra | `litellm_mindmap_generator.py` | `build_mindmap_prompt()` accepts and injects transcript (truncated to first 3000 chars) |
| infra | `mindmap_workflow.py` | `ConfiguredMindmapWorkflow.run()` adds `transcript_text` param |
| library/ports | `ports.py` | `VideoMindmapGenerator.run()` adds `transcript_text` param |
| infra | `library_generation_adapters.py` | Pass through `transcript_text` |
| library/usecases | `mindmap_generation.py` | `GenerateVideoMindmapFromLibrary.run()` reads `workspace.get_video_transcript()` and passes transcript text |

**Prompt change:**

```
# Before
…视频标题：{title}
视频时长秒数：{duration_seconds}
概况 JSON：{summary_json}

# After
…视频标题：{title}
视频时长秒数：{duration_seconds}
概况 JSON：{summary_json}
转写文本：{transcript_text}
```

No schema change. `MindmapNodePayload` unchanged. Frontend unaffected.

### 2. Regenerate button

**File:** `src/frontend/src/features/workspace/ui/views/WorkspaceMindmapView.jsx`

When mindmap is already generated (`tools.mindmap.generated === true`), add a small icon button next to the "Mindmap" label that calls `onGenerateMindmap`. Reuse existing `isGeneratingMindmapSelectedVideo` for loading state.

### 3. Export button

**Backend — new endpoint:**
```
GET /api/videos/{series_id}/{video_id}/mindmap/export?format=md
```

Reads `mindmap.json`, recursively renders as Markdown nested list, returns with `Content-Type: text/markdown; charset=utf-8` and `Content-Disposition: attachment`.

**Frontend:** `WorkspaceMindmapView.jsx` — add download icon button, `window.open(exportUrl)`.

### 4. Series-level mindmap

**Input data sources:**
- `series_catalog.json` — lightweight index of all videos with titles and one-sentence summaries
- Each video's `summary.json` — full structured summary (chapters, key points, takeaways)

**New backend files (mirroring single-video pattern):**

```
generation/prompts/series_mindmap.py               # SERIES_MINDMAP_PROMPT_TEMPLATE
generation/usecases/generate_series_mindmap.py      # GenerateSeriesMindmap
infrastructure/litellm_series_mindmap_generator.py  # LiteLLMSeriesMindmapGenerator
infrastructure/series_mindmap_workflow.py           # ConfiguredSeriesMindmapWorkflow
library/usecases/series_mindmap_generation.py       # GenerateSeriesMindmapFromLibrary
```

**Modified files:**
- `generation/ports.py` — new `SeriesMindmapGenerator` Protocol
- `library/ports.py` — new `SeriesMindmapGenerator` Protocol
- `infrastructure/application_builders.py` — `build_series_mindmap_application()`
- `infrastructure/library_generation_adapters.py` — `WorkspaceBackedSeriesMindmapGenerator`
- `api/bootstrap.py` — wire into `ApiContainer`
- `api/container.py` — add fields
- `api/routes/series.py` — new endpoints

**New API endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/series/{sid}/mindmap` | Read existing series mindmap |
| POST | `/api/series/{sid}/mindmap/generate` | Generate series mindmap |
| GET | `/api/series/{sid}/mindmap/export?format=md` | Export series mindmap |

**Artifact location:** `workspace/{series_id}/mindmap.json`

**Data flow:**
```
POST /api/series/{sid}/mindmap/generate
  -> GenerateSeriesMindmapFromLibrary.run(series_id)
    -> list all videos in series
    -> for each video: workspace.get_video_summary(series_id, video_id)
    -> workspace.get_series_catalog(series_id)
    -> generator.run(series_title, catalog, video_summaries)
      -> build_series_mindmap_prompt(...)
      -> gateway.acomplete_structured(..., MindmapNodePayload)
      -> artifact_store.save_mindmap(mindmap, series_dir)
    -> read back mindmap.json -> return DTO
```

**Prompt design:**
```
你是一个知识整理专家。请基于以下系列课程的目录索引和各视频概况，
生成一份跨视频的知识结构思维导图 JSON。

要求：
1. 只输出 JSON，不要输出额外解释
2. 根节点为系列标题
3. 按知识主题组织二级节点，而非按视频分集罗列
4. 同一知识点出现在多集时，合并为一个节点
5. 节点标题简洁，优先使用关键词或短语
6. 层级深度由内容复杂度决定
7. 不要编造总结中不存在的信息

系列目录：
{series_catalog_json}

各视频概况：
{video_summaries_json}
```

**Frontend changes:**
- Series context toolbar: add "思维导图" tool item
- New `WorkspaceSeriesMindmapView.jsx` component (reuses `MindmapCanvas`)
- Buttons: generate / regenerate / export (mirrors single-video UX)
- Series mindmap state in `workspaceReducer.js` and `workspaceState.js`

## Architecture Boundaries

All changes respect existing `import-linter` boundaries:
- New generation use-cases only import from `domain` + `generation.ports`
- New infrastructure adapters implement generation/library ports
- Library use-cases only depend on `library.ports` + DTOs
- API routes only use `ApiContainer` dependencies
- No new cross-boundary violations

## Testing

- **Unit:** `tests/backend/unit/mindmap/` — new tests for `GenerateSeriesMindmap`, prompt rendering, export rendering
- **Integration:** `tests/backend/integration/llm/` — extend existing `test_mindmap_and_knowledge_cards.py` with series mindmap tests
- **Frontend:** `tests/frontend/features/workspace/ui/` — test new/updated views
