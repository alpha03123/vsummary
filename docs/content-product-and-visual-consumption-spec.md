# 内容产物定位与视觉消费规格

## 目标

重新确定视频内容产物的产品地位，并约束多模态帧消费和 AI 笔记图片标记的行为。

本规格不直接修改现有制品名称。实施时允许进行一次明确迁移，但不得把用户可编辑的 Markdown 反向作为时间锚点、视觉证据或 RAG 的事实来源。

## 产品定位

当前名称与用户实际使用方式不一致：时间轴概况更像“可跳转的整理逐字稿”，AI 笔记更像用户期待的完整 AI 总结。

目标关系如下：

```text
原始媒体
  -> transcript.cleaned.json       原始逐字稿
  -> AI 整理逐字稿                  章节、时间轴、转写整理与定位索引
  -> AI Summary                    面向阅读的完整多模态总结与视觉证据
  -> personal notes                用户自己的可编辑笔记
```

| 当前产物 | 目标定位 | 是否可编辑 | 系统职责 |
| --- | --- | --- | --- |
| `transcript.cleaned.json` | 原始逐字稿 | 否 | 语音内容的基础来源 |
| 当前 `summary.json` / 概况页 | AI 整理逐字稿 / 时间轴索引 | 否 | 章节、转写整理、seek、章节展示图 |
| 当前 `source="agent"` 的 AI 笔记 | AI Summary | 是 | 完整归纳、重写、学习/复习用正文 |
| `source="manual"` 笔记 | 个人笔记 | 是 | 用户自由记录 |

因此，后续产品文案应将当前“AI 概括”调整为“AI 整理逐字稿”，将 AI 生成长笔记调整为“AI 总结”。结构化逐字稿索引仍是系统事实源；AI Summary 的编辑不回写它。

## 卡片与生成权：唯一 AI 概括，独立个人笔记

AI Summary 不能继续作为 `notes.json` 列表中任意多条 `source="agent"` 笔记之一。它是视频的唯一主总结，产品层级与当前“AI 概括”相同；个人笔记是另一种用户制品，两者必须拆成两个一级卡片。

```text
视频工具区
├─ AI 概括（唯一）
│  ├─ 未生成：生成 AI 概括
│  ├─ 生成中：独立进度 / 可取消
│  ├─ 已生成：查看、编辑、重新生成、导出
│  └─ 数据：唯一 ai_summary 制品
│
├─ AI 整理逐字稿（原 AI 概括）
│  ├─ 已生成：查看章节、逐字稿整理、章节小封面、seek
│  └─ 未生成：提示“请前往 AI 概括生成”，点击只跳转 AI 概括卡
│
└─ 个人笔记（多条）
   ├─ 手工新建、编辑、删除
   └─ 数据：notes.json 中 source="manual" 的记录
```

### 唯一 AI 概括的生成与重生成

“生成 AI 概括”与“重新生成 AI 概括”是唯一 AI 概括卡的职责，继承当前 AI 概括生成入口的产品地位：

```text
点击 AI 概括卡的生成 / 重新生成
  -> 启动同一轮编排
       A. AI 整理逐字稿（文本、章节、章节小封面时间）
       B. 唯一 AI 概括（转写 + 视频帧池、Markdown + evidence）
```

- A 与 B 并发生成，但前端分别显示子任务状态；
- AI 整理逐字稿不得再有“生成 AI 概括”或“重新生成 AI 概括”按钮；
- 逐字稿缺失时只提供跳转按钮，例如“前往 AI 概括生成”；
- 重新生成 B 必须以原子替换方式覆盖唯一 `ai_summary` 制品，而不是追加第二条 AI 笔记；
- 重生成 B 不删除、不修改任何个人笔记；
- 用户编辑 AI 概括正文后仍可重新生成，重新生成将明确替换该唯一 AI 概括正文；
- `visual.evidence` 属于 B 的生成结果，用户编辑 Markdown 不回写或伪造视觉 evidence；重新生成 B 时一起替换。

### 数据模型与迁移

目标数据归属：

| 制品 | 数量 | 建议存储 | 是否可编辑 |
| --- | ---: | --- | --- |
| AI 整理逐字稿 | 每视频唯一 | 过渡期继续 `summary.json` / `summary.md` | 否 |
| AI 概括 | 每视频唯一 | 新增 `ai_summary.json` / `ai_summary.md` | 是，仅编辑 Markdown |
| 个人笔记 | 每视频多条 | `notes.json`，只保存 `source="manual"` | 是 |
| 视觉证据 | 每视频唯一、随 AI 概括重生成替换 | `visual.evidence.json` | 否 |

`ai_summary.json` 至少包含：

```json
{
  "title": "AI 概括标题",
  "markdown": "可编辑的 AI 概括 Markdown，含 [[IMG:mm:ss]] 标记",
  "generated_at": "ISO-8601 时间",
  "source_outline_version": "对应 A 的生成版本"
}
```

现有 `source="agent"` 笔记需要一次明确迁移：每视频至多选定一条最近的 AI 笔记写入 `ai_summary`；其余 agent 历史记录可在迁移时提示用户处理，不能静默混入个人笔记列表。迁移完成后，新的个人笔记写接口只允许 `source="manual"`；AI 概括只能走专用生成/编辑/重生成接口。

### API 与 UI 边界

目标 API 不复用“笔记列表”的 CRUD 语义：

```text
GET  /api/videos/{series_id}/{video_id}/ai-summary
POST /api/videos/{series_id}/{video_id}/ai-summary/generate
PUT  /api/videos/{series_id}/{video_id}/ai-summary
GET  /api/videos/{series_id}/{video_id}/ai-summary/export

GET/POST/PUT/DELETE /api/videos/{series_id}/{video_id}/notes
  -> 仅个人笔记
```

AI 概括与个人笔记必须使用不同前端卡片、不同 loading 状态和不同导出动作；不得用“列表首项是 AI 笔记”的隐式约定识别唯一主总结。

### RAG 边界

- `summary_global` / `summary_chapter` 继续来自 A，承担章节、时间与 seek 引用；
- `visual_frame` 继续来自 B，承担画面事实与具体时间引用；
- AI 概括正文可作为独立 `ai_summary` 文档索引，不再伪装为普通 `note`；
- 个人笔记继续使用 `note` 文档索引；
- 删除或重生成 AI 概括后，必须原子更新 `ai_summary`、`visual_frame` 和对应 RAG 文档，不能遗留旧总结或旧视觉 evidence。

## 目标执行图：并发生成两种产物

当前串行链路是：转写 → 文本概况 → 章节截图 → 视觉增强概况 → AI 笔记。它使真正的长文总结被放在最后，也把视觉理解重复分散到多个下游任务。

目标链路改为：

```text
原始媒体
  -> 转写
  -> 立即并发两条准备/生成链
       ├─ A. AI 整理逐字稿
       │    输入：原始转写
       │    输出：章节、章节时间范围、整理后的章节文字、章节展示图时间
       │    -> 系统按每章时间抽章节小封面
       │
       └─ B. 视频帧池 -> AI Summary（原 AI 笔记）
            输入：原始转写 + 共享视频帧池的九宫格图
            输出：完整 AI 总结 Markdown、视觉 evidence、笔记图片标记
```

A 不依赖帧池，应在转写完成后立刻开始；B 仅在帧池准备完成后开始。二者互不等待：

- A 失败不取消 B；B 失败不取消 A。
- A 完成后，系统按其每章展示图时间抽取章节展示帧；这些图服务时间轴逐字稿页面，不是 B 的视觉输入来源。
- B 完成后，写入 AI Summary、`visual.evidence.json` 和 `[[IMG:mm:ss]]` 标记；笔记插图按标记时间单独抽取。
- 仅 B 产生 `visual.evidence.json`，因此 RAG 的视觉事实有且只有一个权威来源，避免两个模型对同一画面写出冲突描述。

### A 是现有文本概况能力的直接继承

A 不需要重新发明，也不需要多模态输入。它对应当前链路中 `LiteLLMCompletionSummarizer.summarize(...)` 的文本阶段：

```text
原始转写
  -> 文本 LLM
  -> chapters[]
       - id
       - title
       - start_seconds / end_seconds
       - summary / key_points
       - image_timestamp_seconds（每章代表时刻）
  -> 系统 _attach_chapter_screenshots
  -> 每章章节小封面
```

`image_timestamp_seconds` 是 A 的硬输出契约：

- 每个章节必须且只能输出一个 `image_timestamp_seconds`，不得为 `null`；
- 时间必须落在该章节的 `start_seconds` 与 `end_seconds` 区间内；
- 它只表示“这一章最适合作为小封面的时间点”，不表示模型已经看过该帧；
- 系统而非模型负责按该时间抽取 JPEG、生成文件名和访问 URL，并绑定回同一章节；
- 媒体没有视频流或 ffmpeg 单帧抽取失败是唯一允许该章节最终没有小封面的例外。

换言之，A 使用文本和转写来决定“这一章封面截哪一刻”，不是让系统取章节中点，也不是让视觉模型替它选图。

目标变更只包括：

- A 的产品名从“AI 概括”调整为“AI 整理逐字稿”；
- A 继续由文本模型决定每章 `image_timestamp_seconds`，系统继续校验该时间落在章节区间并抽章节小封面；
- 移除 A 后面的 `LiteLLMVisualSummaryEnricher`，A 不再读取或生产多模态视觉证据；
- 视觉理解和 `visual.evidence` 的责任完整迁移给 B。

因此 A 的章节、seek、章节小封面语义可以保持不变，且能与 B 真正并发。

### 并发后的唯一汇合点

A 与 B 的**模型调用**绝不互相等待。两者都返回后，系统只有一个不调用模型的后处理：用 A 的章节时间和章节展示图时间校验 B 的 `[[IMG:mm:ss]]` 标记。

```text
A 返回章节 / 章节展示图时间
B 返回 AI Summary Markdown / visual evidence / 图片标记
  -> 纯代码校验：时长、图片数量、同章避让
  -> 保存最终 AI Summary，并按有效标记抽取展示图
```

若 B 先完成，系统可先保存其正文和视觉 evidence；待 A 完成后再补做标记避让与图片物化。若 A 失败，则 B 的有效、未超时长图片标记照常保留，不应用“同章避让”规则。

这不是把可编辑的 Markdown 当系统源数据。B 应返回一个结构化响应，至少包含：

```json
{
  "markdown": "可编辑的 AI Summary Markdown，含 [[IMG:mm:ss]] 标记",
  "visual_evidence": {
    "frames": [
      { "frame_id": "pool-grid-03/tile-05", "timestamp_seconds": 84.2, "text": "可脱离图片理解的画面事实" }
    ]
  }
}
```

系统把 Markdown 保存为可编辑 AI Summary；把 `visual_evidence` 独立保存为不可由编辑反向污染的 RAG 证据制品。

## `summary.json` 迁移边界与依赖清单

当前 `summary.json` 虽然名称是 summary，实际已是 A 的结构化时间轴索引。它的直接消费者包括：

| 消费面 | 当前依赖 | 第一阶段处理 |
| --- | --- | --- |
| 视频处理状态与工具解锁 | `summary.json` 是否存在、`core_problem` | 保持不变 |
| 概况页面与章节 seek | `chapters`、时间、截图文件名 | 保持不变，仅改页面文案 |
| 概况 Markdown 编辑与导出 | `summary.md` / `summary.json` | 保持不变，仅改导出/页面文案 |
| RAG | `summary_global`、`summary_chapter` 文档 | 继续由 A 生产，保持现有 citation / seek 契约 |
| Agent 视频上下文 | `get_video_summary()` | 保持不变 |
| 系列目录、系列导图与系列概述 | `VideoSummaryDTO` | 保持不变 |
| 单视频导图和知识卡片 | `summary_data` | 保持不变 |
| AI Summary 章节参考、图片避让 | A 的章节与小封面时间 | 保持不变 |

第一阶段的最小影响策略：

```text
磁盘文件：继续使用 summary.json / summary.md
领域端口：继续使用 VideoSummaryDTO / get_video_summary()
RAG source_type：继续使用 summary_global / summary_chapter
产品文案：改为 AI 整理逐字稿
```

也就是说，第一阶段仅调整**产品地位和生成编排**，不做物理文件重命名，不把 `summary.json` 替换成 AI Summary，不改变既有 RAG/citation/schema/API 契约。这样章节定位、Agent、导图、卡片、系列聚合和导出无需同时重构，程序可以稳定运行。

AI Summary 在第一阶段继续保存为独立的可编辑 AI 笔记记录。它不得覆盖 `summary.json`，不得取代 `summary_global` / `summary_chapter` 的 RAG 来源。若未来要把它提升为独立一级制品，应新增明确的 `ai_summary` 制品与引用契约，再单独迁移；不能复用或污染 A 的结构化索引。

### RAG 归属

RAG 在第一阶段有三种互补来源：

```text
summary_global / summary_chapter  <- A：章节、时间范围、可 seek 的时间轴事实
visual_frame                     <- B：共享帧池产出的视觉 evidence
note                             <- B：可编辑 AI Summary 或个人笔记正文
```

- A 仍是时间定位和章节引用的权威来源；
- B 的 `visual_frame` 是画面事实的权威来源；
- B 的 Markdown 作为 `note` 可检索，但编辑后的内容不应被提升为视觉或章节事实；
- 现有 citation 逻辑继续按 `summary_*` 跳章节、按 `visual_frame` 跳具体视频时间，避免因产品改名损失跳转能力。

### 调用数与成本

当自动 AI Summary 启用时，目标是两次主要 LLM 调用：

| 调用 | 是否多模态 | 产物 |
| --- | --- | --- |
| A. AI 整理逐字稿 | 否 | 时间轴、章节、章节展示图时间 |
| B. AI Summary | 是 | 长文总结、视觉 evidence、笔记图片标记 |

当前“文本概况 + 视觉增强概况 + AI 笔记”是三段模型工作；目标架构将视觉理解集中到 B，避免概况视觉增强和笔记视觉理解重复。

若用户未开启自动 AI Summary，A 仍可独立生成；用户手动点击 AI Summary 时复用已经建立的视频帧池。不得为同一视频再次建立相同参数的帧池。

## 共享视频帧池

视频帧池是给 AI Summary 进行整体视频理解的共享输入，不是章节展示图，也不是笔记最终插图。

```text
视频
  -> 原始候选帧（按时长均匀抽取）
  -> 相邻重复画面过滤
  -> 按时间顺序拼成 3 x 3 九宫格
  -> 最多 B 张九宫格图送给 AI Summary
```

### 预算定义

唯一用户可配的视觉输入预算是：

```text
max_visual_input_images = B
```

它表示**实际发送给视觉模型的九宫格图片数**，不是原始帧数，也不是展示图片数。每张九宫格默认容纳 9 个带时间戳的原始帧：

```text
原始帧目标数 = B x 9
```

示例，`B = 10`：

| 视频时长 | 原始候选抽帧间隔 | 原始帧上限 | 实际视觉输入 |
| --- | ---: | ---: | ---: |
| 180 秒 | 约 2 秒 | 90 | 最多 10 张九宫格 |
| 1,800 秒 | 约 20 秒 | 90 | 最多 10 张九宫格 |
| 60 秒 | 最小 1 秒间隔 | 60 | 7 张九宫格，最后一张不完整 |
| 20 秒 | 最小 1 秒间隔 | 20 | 3 张九宫格，最后一张不完整 |

具体算法：

```python
tiles_per_image = 9
target_raw_frames = max_visual_input_images * tiles_per_image
interval_seconds = max(1.0, duration_seconds / target_raw_frames)
candidate_timestamps = evenly_spaced(0, duration_seconds, interval_seconds)
candidate_timestamps = candidate_timestamps[:target_raw_frames]
```

规则：

- 候选帧按时间升序；首帧和接近结尾的帧必须覆盖。
- 相邻候选帧内容相同或近似相同则去重，避免静态 PPT、片头或人物画面占满预算。
- 去重后不足 9 帧的尾组仍要生成一张不完整九宫格，空格保持空白；不得像旧 BiliNote 一样直接丢弃尾部画面。
- 每个 tile 必须叠加或携带真实时间戳，使模型的视觉 evidence 能回到原视频时间。
- 帧池按视频源身份和池参数缓存到工作区；同一视频、同一参数的并发请求复用同一份帧池。
- 九宫格仅用于模型输入，不在概况页或笔记正文直接展示。

### 三类图片严格分离

| 图片集合 | 来源 | 谁消费 | 是否展示 |
| --- | --- | --- | --- |
| 视频帧池九宫格 | 均匀采样、去重、九宫格拼图 | AI Summary；导图/卡片在显式 `frames` 档时复用同一池 | 否 |
| 整理逐字稿章节图 | A 返回的每章代表时间 | 时间轴逐字稿页面 | 每章一张 |
| AI Summary 插图 | Markdown 的 `[[IMG:mm:ss]]` | AI Summary / 用户笔记正文 | 按标记位置 |

三者可以恰好落在同一时间，但不得假定相同，也不得互相替代。

## 视觉消费原则

帧有三个不同去处：

1. 展示给用户：概况每章一张，笔记按正文标记按需抽取。
2. 注入下游模型：原图 `frames` 输入。
3. 生成可检索画面事实：`visual.evidence.json`。

`visual.evidence` 固定服务 RAG，也可作为下游低成本文本输入；它不是原图的替代品。

## 已记录问题 1：下游读图无配额

本节区分现有过渡实现和目标实现。现有代码暂时从章节展示图中选帧；目标实现必须改为消费“共享视频帧池”的九宫格输入。

### 现状

概况在 `generate_summary.py` 内部通过 `_select_visual_analysis_frames` 从章节展示帧中均匀选取 `max_visual_frames` 张；笔记、导图和卡片在 `frames` 输入档则读取全部章节图。

以 12 个章节、`max_visual_frames = 6` 为例：

| 产物 | 当前读取帧数 | 目标读取输入 |
| --- | ---: | ---: |
| 当前 AI 概括 | 6 张章节图 | 退化为 A，不读取视频帧池 |
| AI Summary / 笔记 | 12 张章节图 | 同一批 B 张九宫格 |
| 导图 | 12 张章节图 | 同一批 B 张九宫格（仅 `frames` 档） |
| 卡片 | 12 张章节图 | 同一批 B 张九宫格（仅 `frames` 档） |

### 修复契约

把帧池构建和输入选择抽到公共模块，例如：

```text
video_summary/library/visual_frame_pool.py
```

公共 API：

```python
build_or_load_visual_frame_pool(video_source, max_visual_input_images) -> VisualFramePool
```

要求：

- `VisualFramePool` 包含原始 tile 帧、九宫格图片、每个 tile 的真实时间戳；
- 总九宫格图片数不超过 `max_visual_input_images`；
- 同一视频源身份和同一池参数必须命中同一缓存；
- 同样的输入和参数必须返回同样的九宫格集合；
- 不修改章节展示图集合，不负责任何产物的模型调用。

调用方必须统一使用此函数：

```text
AI Summary  build_or_load_visual_frame_pool(video, B).grid_images
导图        build_or_load_visual_frame_pool(video, B).grid_images  # 仅 frames 档
卡片        build_or_load_visual_frame_pool(video, B).grid_images  # 仅 frames 档
```

最终配置名应为 `max_visual_input_images`：它是每个启用 `frames` 输入的产物最多读取多少张**九宫格视觉输入图**。它不是原始帧数量，也不是章节或笔记展示图片数量。

现有 `max_visual_frames` 仅是过渡字段：当前代码中它限制章节图子集；迁移到帧池后应废弃或一次性迁移到 `max_visual_input_images`，不得让两个预算同时存在。

收益：

- 控制视觉 token 成本；
- 所有显式选择 `frames` 的下游基于同一组整体视频画面，避免笔记、导图、卡片各自读到不同界面状态；
- 将帧采样、去重、九宫格拼图和缓存收敛为一个可测试模块。

默认 `evidence` 输入不发送原图，不产生额外视觉 token；只有用户主动选择 `frames` 才产生对应产物的一次视觉调用。AI Summary 是默认的唯一帧池消费者；导图和卡片默认使用 `evidence`，避免重复视觉调用。

## 已记录问题 2：AI 路径错误删除超时长图片标记

### 现状

AI 笔记生成后的 `_constrain_ai_note_image_markers` 将“标记超出视频时长”和“超过自动图片上限”混在删除路径中。

这与手动笔记不一致：手动笔记会保留 `[[IMG:...]]`，前端会将超时长标记渲染成可读异常占位；AI 路径却提前删除了它，导致异常信息丢失。

同时，AI 标记若落在相邻章节之间的时间缝隙，当前也会因为找不到章节而被删除。章节间存在小缝隙属于时间轴数据现象，不应处罚用户或模型生成的时间标记。

### 修复契约

AI 标记后处理必须将三类结果分开：

```python
accepted  # 有效，保留并占 note_max_images 配额；保存时抽帧
kept      # 保留原文但不占配额；前端渲染为异常占位
removed   # 从 AI 输出中移除；记入轻提示统计
```

处理顺序：

```python
for marker in markers:
    # 1. 超时长：保留原文，不占自动图片名额。
    if marker.seconds > duration_seconds:
        kept.add(marker.position)
        continue

    # 2. 超过自动图片上限：删除，并计数。
    if len(accepted) >= note_max_images:
        removed.add(marker.position)
        continue

    chapter = find_chapter(marker.seconds)

    # 3. 无概况或落在章节缝隙：接受，不因索引缝隙删除。
    if chapter is None:
        accepted.add(marker.position)
        continue

    # 4. 与同章概况截图避让失败：删除，并计数。
    if violates_gap(marker, chapter):
        removed.add(marker.position)
        continue

    accepted.add(marker.position)
```

前端已有的异常渲染继续承担 `kept` 标记：

```text
此处插图不可用：[[IMG:xx]] 超出视频时长
```

`removed` 仅针对 AI 自动标记：超过 `note_max_images` 或违反同章避让规则时移除；生成完成后必须向用户给一条轻提示，例如“已忽略 2 个不符合插图规则的标记”。

手动笔记不应用自动图片数量上限和概况避让规则；其合法标记应原样保存，时长错误交给前端异常占位。

## 任务边界与 UI 状态

目标架构中 A 与 B 是同一轮用户触发的两个**并发子任务**，但 UI 必须维护独立状态：

```text
AI 整理逐字稿任务：完成即关闭其时间轴生成遮罩
AI Summary 任务：独立显示“正在生成 AI 总结”状态
导图 / 卡片任务：各自独立状态
```

不得因为 B、导图或卡片还在生成，就把 A 的时间轴逐字稿遮罩维持在“处理中”。失败只影响对应子任务和其制品。

过渡期中，现有自动笔记、导图和卡片虽仍由概况完成后启动，也必须作为独立后台任务，不得延长概况 SSE；目标架构实施后，自动 AI Summary 则迁移为与 A 同时启动。

## 验收测试

- 180 秒视频、`max_visual_input_images=10`：帧池最多生成 10 张九宫格图，约 90 个原始候选帧；AI Summary 读取该池。
- 60 秒或更短视频：按最小 1 秒间隔生成少于 10 张的九宫格图，尾组不丢弃。
- AI Summary、导图、卡片在 `frames` 输入下读取同一批帧池九宫格，不重复抽样或各自建立池。
- A 的章节展示图和 B 的帧池九宫格互不替代；A 每章一张展示图，B 的笔记插图按标记另行抽取。
- `evidence` 输入不发送图片；`none` 不发送图片和证据。
- AI 标记超时长：原文仍在，前端显示异常占位，且不占 `note_max_images`。
- AI 标记落在章节缝隙：保留并正常抽帧。
- AI 标记超过上限或违反避让：移除并显示轻提示计数。
- 手动笔记标记不受自动图片配额或避让规则限制。
- A 与 B 并发时，A 完成不等待 B；两个 UI 状态独立结束。
