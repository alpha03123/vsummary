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

## Complete File Manifest

### New files (5)

| # | File | Layer |
|---|------|-------|
| 1 | `src/backend/video_summary/generation/prompts/series_mindmap.py` | generation |
| 2 | `src/backend/video_summary/generation/usecases/generate_series_mindmap.py` | generation |
| 3 | `src/backend/video_summary/infrastructure/litellm_series_mindmap_generator.py` | infrastructure |
| 4 | `src/backend/video_summary/infrastructure/series_mindmap_workflow.py` | infrastructure |
| 5 | `src/backend/video_summary/library/usecases/series_mindmap_generation.py` | library |
| 6 | `src/frontend/src/features/workspace/ui/views/WorkspaceSeriesMindmapView.jsx` | frontend |

### Modified files (36)

| # | File | Change |
|---|-------|--------|
| **Change 1: transcript injection** |||
| 1 | `infrastructure/prompts/mindmap.py` | Add `{transcript_text}` placeholder |
| 2 | `generation/ports.py` | `MindmapGenerator.generate()` adds `transcript_text: str = ""` |
| 3 | `generation/usecases/generate_mindmap.py` | Pass through `transcript_text` |
| 4 | `infrastructure/litellm_mindmap_generator.py` | `build_mindmap_prompt()` accepts/injects transcript |
| 5 | `infrastructure/mindmap_workflow.py` | `run()` adds `transcript_text` param |
| 6 | `library/ports.py` | `VideoMindmapGenerator.run()` adds `transcript_text` param |
| 7 | `infrastructure/library_generation_adapters.py` | Pass through |
| 8 | `library/usecases/mindmap_generation.py` | Read transcript from workspace, pass downstream |
| **Change 2: regenerate button** |||
| 9 | `ui/views/WorkspaceMindmapView.jsx` | Add regenerate button in generated state |
| **Change 3: export button** |||
| 10 | `api/routes/videos.py` | New `GET .../mindmap/export?format=md` endpoint |
| 11 | `ui/views/WorkspaceMindmapView.jsx` | Add export download button |
| **Change 4: series mindmap (backend)** |||
| 12 | `generation/ports.py` | New `SeriesMindmapGenerator` Protocol |
| 13 | `generation/usecases/__init__.py` | Export `GenerateSeriesMindmap` |
| 14 | `generation/prompts/__init__.py` | Export `SERIES_MINDMAP_PROMPT_TEMPLATE` |
| 15 | `infrastructure/prompts/__init__.py` | Add series mindmap prompt export |
| 16 | `infrastructure/application_builders.py` | `build_series_mindmap_application()` |
| 17 | `library/ports.py` | New series `SeriesMindmapGenerator` Protocol |
| 18 | `infrastructure/library_generation_adapters.py` | `WorkspaceBackedSeriesMindmapGenerator` |
| 19 | `library/usecases/__init__.py` | Export `GenerateSeriesMindmapFromLibrary` |
| 20 | `api/bootstrap.py` | Wire series mindmap use-case into container |
| 21 | `api/container.py` | Add `generate_series_mindmap` field |
| 22 | `api/routes/series.py` | `GET/POST /api/series/{sid}/mindmap` + export |
| 23 | `tools/mindmap.py` | Add `OPEN_SERIES_MINDMAP` + `GENERATE_SERIES_MINDMAP` tool defs |
| 24 | `tools/catalog.py` | Register new tools in `UI_ACTION_TOOL_DEFINITIONS` |
| 25 | `tools/__init__.py` | Export new tool executors |
| **Change 4: series mindmap (frontend)** |||
| 26 | `workspaceState.js` | Series mindmap state + selectedNodeId |
| 27 | `workspaceReducer.js` | Series mindmap actions (load/clear/generate) |
| 28 | `workspaceApi.js` | `loadSeriesMindmap()` / `generateSeriesMindmap()` |
| 29 | `workspaceContentActions.js` | `onGenerateSeriesMindmap` action |
| 30 | `useWorkspaceController.js` | Wire up series mindmap in controller |
| 31 | `useWorkspaceDataEffects.js` | Load series mindmap on tool select |
| 32 | `workspacePageModel.js` | Pass series mindmap to shell |
| 33 | `WorkspaceReadingPane.jsx` | Series toolbar mindmap item + view routing |
| 34 | `workspaceChatActions.js` | Handle `open_series_mindmap` / `generate_series_mindmap` payloads |
| 35 | `workspaceChatRuntime.js` | Trace step for series mindmap tools |
| 36 | `workspaceToolMeta.js` | Series mindmap tool meta definition |

### NOT modified (boundaries preserved)

- `backend/agent/` — unchanged; new tools only add `ToolDefinition` dataclasses in `tools/`
- `backend/agent_graph/` — unchanged; `VideoActionPlanner` whitelist stays `OPEN_NOTES/SAVE_NOTE/VIDEO_SEEK`
- `backend/video_summary/domain/` — unchanged
- `backend/shared/` — unchanged

---

## Acceptance Criteria & Test Cases

### Change 1: Transcript Injection

**Acceptance Criteria:**

| AC# | Condition |
|-----|-----------|
| AC1.1 | `build_mindmap_prompt()` accepts `transcript_text` param, output includes transcript text (truncated to first 3000 chars) |
| AC1.2 | Empty string passed: prompt contains `转写文本：` with empty suffix, does not crash |
| AC1.3 | `MindmapGenerator.generate()` port signature includes `transcript_text: str = ""`, backward compatible |
| AC1.4 | `GenerateVideoMindmapFromLibrary.run()` auto-reads `workspace.get_video_transcript()` and passes transcript |
| AC1.5 | When video has no transcript (`get_video_transcript` returns `None`), passes empty string, flow continues |
| AC1.6 | `MindmapNodePayload` schema unchanged; existing `mindmap.json` files remain readable |
| AC1.7 | Transcript >10000 chars truncated to first 3000 chars; does not overflow context window |

**Test Cases:**

```
tests/backend/unit/mindmap/test_mindmap_prompt.py
  ├── test_prompt_includes_transcript_text
  │     transcript_text="这是一段转写文本" → output contains the text
  ├── test_prompt_handles_empty_transcript
  │     transcript_text="" → no crash, "转写文本：" section empty
  ├── test_prompt_truncates_long_transcript
  │     10000-char transcript → transcript portion in prompt ≤ 3000 chars
  ├── test_prompt_still_includes_summary_and_title
  │     Verify title/duration/summary placeholders still render correctly

tests/backend/unit/mindmap/test_generate_mindmap.py
  ├── test_generate_mindmap_passes_transcript_to_generator
  │     FakeMindmapGenerator → verify transcript_text correctly passed
  ├── test_generate_mindmap_reads_transcript_from_workspace
  │     FakeWorkspace → verify get_video_transcript() is called

tests/backend/integration/llm/test_mindmap_and_knowledge_cards.py
  └── (extend existing MindmapPromptTests)
       test_prompt_includes_transcript_placeholder
```

---

### Change 2: Regenerate Button

**Acceptance Criteria:**

| AC# | Condition |
|-----|-----------|
| AC2.1 | Regenerate button visible when `tools.mindmap.generated === true` |
| AC2.2 | Regenerate button hidden when `tools.mindmap.generated === false` (show original "生成思维导图" button instead) |
| AC2.3 | Click triggers `onGenerateMindmap`; loading state shown (shimmer or button spinner) |
| AC2.4 | Button disabled while generating to prevent double-click |
| AC2.5 | On success, mindmap auto-refreshes to new content |
| AC2.6 | On failure, error message shown, existing mindmap preserved (not overwritten) |

**Test Cases:**

```
tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
  ├── test_shows_regenerate_button_when_mindmap_generated
  │     tools.mindmap.generated=true → button present
  ├── test_hides_regenerate_button_when_mindmap_not_generated
  │     tools.mindmap.generated=false → button absent
  ├── test_regenerate_button_disabled_while_generating
  │     isGeneratingMindmapSelectedVideo=true → button disabled
  ├── test_regenerate_calls_onGenerateMindmap
  │     Click button → onGenerateMindmap called once
  ├── test_existing_mindmap_preserved_on_generation_error
  │     onGenerateMindmap rejects → mindmap data unchanged
```

---

### Change 3: Export Button

**Acceptance Criteria:**

| AC# | Condition |
|-----|-----------|
| AC3.1 | Export download button visible when mindmap is generated |
| AC3.2 | Export button hidden when mindmap not generated |
| AC3.3 | `GET /api/videos/{sid}/{vid}/mindmap/export?format=md` returns `Content-Type: text/markdown; charset=utf-8` |
| AC3.4 | Response includes `Content-Disposition: attachment; filename="{title}-mindmap.md"` |
| AC3.5 | Markdown content is nested list matching `mindmap.json` tree structure |
| AC3.6 | Returns 404 when mindmap not found |
| AC3.7 | Only `format=md` supported; other formats return 400 |

**Test Cases:**

```
tests/backend/unit/mindmap/test_mindmap_export.py
  ├── test_export_renders_nested_markdown_list
  │     3-level MindmapNodePayload input → correct Markdown indentation
  ├── test_export_handles_single_root_node
  │     Root with no children → single line output
  ├── test_export_handles_empty_children
  │     children=[] → no crash
  ├── test_export_includes_node_summary
  │     Node summary non-empty → rendered as nested content

tests/backend/integration/api/test_mindmap_api.py
  ├── test_export_returns_markdown_content_type
  ├── test_export_returns_404_when_mindmap_not_found
  ├── test_export_returns_400_for_unsupported_format

tests/frontend/features/workspace/ui/WorkspaceMindmapView.test.jsx
  ├── test_shows_export_button_when_mindmap_generated
  ├── test_hides_export_button_when_mindmap_not_generated
```

---

### Change 4: Series-Level Mindmap

**Acceptance Criteria:**

| AC# | Condition |
|-----|-----------|
| AC4.1 | Series context toolbar shows "思维导图" tool item |
| AC4.2 | Tool status `available` when at least one video in series has summary |
| AC4.3 | Tool status `blocked` when no video in series has summary |
| AC4.4 | `POST /api/series/{sid}/mindmap/generate` collects all video summaries + series_catalog, calls LLM |
| AC4.5 | Artifact written to `workspace/{series_id}/mindmap.json`, schema `MindmapNodePayload` |
| AC4.6 | Root node `title` = series title; `children` organized by knowledge topic (not by video episode) |
| AC4.7 | After generation, `GET /api/series/{sid}/mindmap` returns full tree |
| AC4.8 | Generated mindmap view has regenerate + export buttons (same behavior as single-video) |
| AC4.9 | `GET /api/series/{sid}/mindmap/export?format=md` exports series mindmap |
| AC4.10 | Agent can trigger via `OPEN_SERIES_MINDMAP` / `GENERATE_SERIES_MINDMAP` tools in series scope |

**Edge Cases & Error Handling:**

| Scenario | Expected Behavior |
|----------|-------------------|
| Series has no videos | Tool status=blocked; generate API returns 400 "系列无视频" |
| Series has videos but none have summary | Tool status=blocked; generate API returns 400 "系列下没有已生成概况的视频" |
| `series_catalog.json` missing | Degrade gracefully: use only video summaries, omit catalog section from prompt |
| Series has 50+ videos (large summaries) | Each video summary truncated to `one_sentence_summary + chapter_titles`; raw chapters not included |
| Concurrent generation of same series | Second request returns 409 "该系列导图正在生成中" |
| Series deleted after mindmap generated | GET returns 404 |
| Some videos have summary, some don't | Only videos with summary are included; partial generation proceeds |

**Test Cases:**

```
tests/backend/unit/mindmap/test_series_mindmap_prompt.py
  ├── test_prompt_includes_series_catalog
  ├── test_prompt_includes_video_summaries
  ├── test_prompt_truncates_large_summaries
  │     50 video summaries → each truncated to core fields
  ├── test_prompt_falls_back_without_catalog
  │     catalog=None → prompt omits catalog section but does not crash

tests/backend/unit/mindmap/test_generate_series_mindmap.py
  ├── test_collects_all_video_summaries
  │     FakeWorkspace returns 3 summaries → all passed to generator
  ├── test_skips_videos_without_summary
  │     3 videos, 1 summary=None → only 2 used
  ├── test_returns_none_when_no_summaries
  │     All summaries=None → returns None
  ├── test_reads_series_catalog
  │     Verify get_series_catalog() is called

tests/backend/unit/mindmap/test_series_mindmap_export.py
  ├── test_export_series_mindmap_markdown
  │     Verify nested Markdown list output correct

tests/backend/integration/api/test_series_mindmap_api.py
  ├── test_generate_series_mindmap_requires_summaries
  │     No summaries → 400
  ├── test_generate_series_mindmap_creates_artifact
  │     Normal generation → mindmap.json exists
  ├── test_get_series_mindmap_returns_tree
  │     GET → returns valid MindmapNodePayload structure
  ├── test_get_series_mindmap_404_when_not_generated
  ├── test_export_series_mindmap
  ├── test_concurrent_generation_returns_409

tests/frontend/features/workspace/ui/WorkspaceSeriesMindmapView.test.jsx
  ├── test_shows_generate_button_when_available
  ├── test_shows_blocked_state_when_no_summaries
  ├── test_regenerate_and_export_buttons_work
  ├── test_mindmap_canvas_renders_tree

tests/backend/architecture/
  └── Existing import-linter tests automatically cover new files
```

---

### Explicitly Excluded from Testing

- **Real LLM call tests** — Use `FakeGateway` for logic paths; no new tests that call real LLM (cost/time)
- **Agent end-to-end tests** — Existing `OPEN_MINDMAP`/`GENERATE_MINDMAP` patterns already tested; new tools add only `ToolDefinition` entries following identical path
- **Performance/stress tests** — 50+ video series scenarios validated via logic truncation tests only, no real load testing
