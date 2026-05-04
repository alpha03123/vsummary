# Series Scope RAG 具体改造与验收方案

## 1. 文档目标

本文不再讨论“为什么要改”，而是只回答下面这些实现问题：

1. 具体改哪些代码
2. 每个文件改完后职责变成什么
3. 理想中间产物 JSON 长什么样
4. 如何把这些中间产物打出来调试
5. 如何判断“实际输出”和“理想输出”足够一致
6. 如何验收，而不是只靠主观感觉

本文默认以 `series scope` 为主，`video scope` 暂不跟着一起大改。

---

## 2. 总体实施原则

### 2.1 目标结构

最终目标不是修补当前：

- `SeriesPlanner`
- `selected_videos`
- `selection_mode`
- `subplans`
- `target_video_ids`
- `execute_summary / execute_video_graph / execute_video_workflow`

而是收敛成：

1. `Series Catalog`
2. `Series Synopsis`
3. `SeriesQueryProcessor`
4. `Unified Retrieval`
5. `Answer Synthesis`

运行时理想调用链：

```text
用户问题
-> SeriesQueryProcessor
-> UnifiedRetrieval.search()
-> SeriesAnswerSynthesizer
-> 最终回答
```

### 2.2 实施顺序

实施顺序必须遵循：

1. 先把资产层和调试能力补齐
2. 再引入新查询合同
3. 再替换 graph 主路径
4. 最后清理旧 planner / subplans 协议

原因：

1. 先有可观测性，后有重构
2. 先能对比中间产物，再谈“体验是否变好”

---

## 3. 需要改动的文件清单

### 3.1 现有文件需要修改

1. `src/backend/video_summary/infrastructure/filesystem_video_workspace.py`
2. `src/backend/video_summary/library/ports.py`
3. `src/backend/video_summary/library/usecases/summary_generation.py`
4. `src/backend/agent_graph/query/models.py`
5. `src/backend/agent_graph/runtime/graph.py`
6. `src/backend/agent_graph/runtime/nodes.py`
7. `src/backend/agent_graph/evidence/retrieval.py`
8. `src/backend/agent_graph/query/series_aggregator.py`
9. `src/backend/api/bootstrap.py`
10. `src/backend/api/routes/agent.py`
11. `scripts/analysis/run_speed_profile.py`

### 3.2 建议新增文件

1. `src/backend/video_summary/library/usecases/series_synopsis_generation.py`
2. `src/backend/agent_graph/query/series_query_processor.py`
3. `src/backend/agent_graph/query/series_answer_synthesizer.py`
4. `src/backend/agent_graph/evidence/document_schema.py`
5. `src/backend/agent_graph/evidence/index_builder.py`
6. `scripts/analysis/run_series_scope_debug_trace.py`
7. `scripts/regression/check_series_scope_contracts.py`
8. `tests/agent/test_series_scope_contracts.py`
9. `tests/fixtures/series_scope/overview.expected.json`
10. `tests/fixtures/series_scope/concept.expected.json`
11. `tests/fixtures/series_scope/locate.expected.json`

---

## 4. 每个改动点的具体职责

### 4.1 `filesystem_video_workspace.py`

当前职责：

1. 读取 video summary
2. 读取 transcript
3. 读取 notes / cards
4. 读取 workspace tool 状态

需要新增的职责：

1. 读取 `series_catalog`
2. 读取 `series_synopsis`
3. 保存 `series_synopsis`
4. 标记 `series_synopsis` 是否过期

建议新增的方法：

```python
def get_series_catalog(self, series_id: str) -> dict[str, object] | None: ...
def get_series_synopsis(self, series_id: str) -> dict[str, object] | None: ...
def save_series_synopsis(self, series_id: str, payload: dict[str, object]) -> None: ...
def mark_series_synopsis_stale(self, series_id: str) -> None: ...
```

建议落盘位置：

- `workspace/<series_id>/series_catalog.json`
- `workspace/<series_id>/series_overview.json`

说明：

1. `series_catalog.json` 可以在读取时动态拼，也可以缓存落盘
2. `series_overview.json` 应视为正式资产，建议落盘
3. `chapter_titles` 必须从 `chapters[*].title` 派生，不单独让模型生成

### 4.2 `series_synopsis_generation.py`

新增一个真正的 series synopsis 生成 use case。

职责：

1. 读取全系列轻量 summary 资产
2. 生成 `series_overview.json`
3. 不读取 transcript 大段正文
4. 保持输出稳定、结构化、可检索

建议输入：

```json
{
  "series_id": "1",
  "videos": [
    {
      "video_id": "1-1 ...",
      "title": "...",
      "one_sentence_summary": "...",
      "chapter_titles": ["...", "..."],
      "processed": true
    }
  ]
}
```

建议输出：

```json
{
  "series_id": "1",
  "series_title": "1",
  "version": 1,
  "synopsis": {
    "one_sentence_overview": "...",
    "main_storyline": "...",
    "topic_groups": [],
    "learning_path": [],
    "video_briefs": []
  },
  "stale": false,
  "updated_at": "2026-05-02T12:00:00Z"
}
```

### 4.3 `query/models.py`

当前模型过于围绕旧 graph 执行合同：

- `SelectionMode`
- `ExecutionDepth`
- `QuerySubplan`
- `StructuredQueryPlan`

建议保留旧模型给过渡期使用，但新增新合同模型：

```python
class SeriesQueryUnderstanding(BaseModel):
    normalized_query: str
    subqueries: list[str]
    filters: dict[str, object]
    retrieval_hints: RetrievalHints

class RetrievalHints(BaseModel):
    prefer_source_types: list[str]
    allow_source_types: list[str]
    need_exact_quote: bool = False
    need_timeline: bool = False
    need_procedure_continuity: bool = False
    top_k: int = 8

class RetrievalHit(BaseModel):
    evidence_id: str
    doc_id: str
    series_id: str
    video_id: str | None
    source_type: str
    source_family: str
    title: str
    chapter_title: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    score: float
    text: str

class SeriesAnswerPayload(BaseModel):
    answer: str
    citations: list[dict[str, object]]
    used_source_types: list[str]
```

### 4.4 `series_query_processor.py`

新增轻量 Query Processor，替代当前重型 `SeriesPlanner`。

职责：

1. 输入用户问题、对话历史、series catalog
2. 输出 `SeriesQueryUnderstanding`
3. 不输出 `selected_videos`
4. 不输出 `subplans`
5. 不输出 `target_video_ids`
6. 不编排执行图

建议 prompt 目标：

1. 重写 query
2. 必要时拆 subqueries
3. 给 retrieval hints
4. 对 overview / concept / locate / workflow 给出轻量检索偏好

不再做：

1. 遍历全系列读 enriched summary
2. 让模型决定执行节点
3. 让模型直接做视频筛选协议

### 4.5 `runtime/graph.py`

当前 graph 节点过多：

- `build_plan`
- `advance_subplan`
- `execute_summary`
- `execute_video_graph`
- `execute_video_rag`
- `execute_video_workflow`
- `answer`

建议改成：

1. `understand_query`
2. `retrieve_evidence`
3. `answer`
4. `finalize`
5. `update_memory`

也就是：

```text
START
-> understand_query
-> retrieve_evidence
-> answer
-> finalize
-> update_memory
-> END
```

过渡期可以保留旧节点实现，但不要再给 `series scope` 走旧分支。

### 4.6 `runtime/nodes.py`

当前这里最大的问题是：所有 state 都围绕 `query_plan/subplans/current_subplan` 在转。

需要调整为新 state：

```python
{
  "query_understanding": {...},
  "retrieval_request": {...},
  "retrieval_results": {...},
  "answer_payload": {...}
}
```

建议新增或替换节点：

1. `build_understand_query_node`
2. `build_retrieve_evidence_node`
3. `build_answer_node`

建议删除对下列字段的依赖：

1. `current_subplan_index`
2. `current_subplan`
3. `query_plan.subplans`
4. `query_plan.selected_videos`

### 4.7 `evidence/retrieval.py`

当前方向是对的，因为已经在做 unified index。  
但需要改 4 件事：

1. document schema 标准化
2. 把 `series_synopsis` 纳入索引
3. 把 index build 生命周期前移
4. 调试信息显式输出

建议新的 `source_type` 固定为：

- `series_synopsis`
- `summary_global`
- `summary_chapter`
- `transcript_chunk`
- `note`
- `knowledge_card`

建议把当前：

- `summary`
- `chapter`

替换为更明确的：

- `summary_global`
- `summary_chapter`

建议新增两个对象：

1. `build_documents_for_series()`
2. `build_or_refresh_workspace_index()`

并把“查询时建索引”迁移到：

- summary 更新后
- note / card 更新后
- synopsis 更新后

### 4.8 `series_aggregator.py`

建议不要继续沿用当前“吃 execution_results + query_plan”的接口。

建议新增 `SeriesAnswerSynthesizer`，职责只保留：

1. 输入 `user_query`
2. 输入 `query_understanding`
3. 输入 `retrieval_hits`
4. 输出 `SeriesAnswerPayload`

当前 `SeriesAggregator` 可以：

1. 过渡期保留
2. 仅用于兼容旧流量
3. 不再作为新链路的核心对象

### 4.9 `api/bootstrap.py`

需要把 wiring 改掉。

当前 wiring：

1. 注入 `SeriesPlanner`
2. 注入 `SeriesRetrievalService`
3. 注入 `SeriesAggregator`
4. graph 走旧节点集合

改造后应注入：

1. `SeriesQueryProcessor`
2. `SeriesRetrievalService`
3. `SeriesAnswerSynthesizer`
4. `SeriesSynopsisGenerator`

并且要提供一个显式入口：

```python
invalidate_agent_workspace_indexes()
refresh_agent_workspace_indexes()
refresh_series_synopsis(series_id: str)
```

### 4.10 `api/routes/agent.py`

当前只在 stream 路由下打 debug trace 日志，而且 debug trace 结构偏旧。

需要增强两点：

1. 非 stream 路径也允许显式打开 debug trace
2. debug trace 输出改成围绕新合同

建议支持两种调试方式：

1. 保留 debug log
2. 新增脚本直接落本地 JSON trace 文件

---

## 5. 理想中间产物

### 5.1 `series_catalog.json`

```json
{
  "series_id": "1",
  "series_title": "1",
  "videos": [
    {
      "video_id": "1-1 多Agent融合自主决策，AI发展的必然趋势",
      "title": "1-1 多Agent融合自主决策，AI发展的必然趋势",
      "one_sentence_summary": "视频梳理了AI从聊天模式到Copilot、再到Agent及多Agent协同的演进趋势，指出学习多智能体融合自主决策是应对技术快速迭代的核心方向。",
      "chapter_titles": [
        "AI发展迅速，如何选择不被淘汰的技术",
        "2023年：聊天模式与大号搜索引擎",
        "2024年：Copilot模式与副驾驶角色"
      ],
      "processed": true,
      "tags": []
    }
  ],
  "updated_at": "2026-05-02T12:00:00Z"
}
```

说明：

1. `one_sentence_summary` 来自 summary 资产真实字段
2. `chapter_titles` 来自 `chapters[*].title` 派生
3. `tags` 可以先为空，后续再加

### 5.2 `series_overview.json`

```json
{
  "series_id": "1",
  "series_title": "1",
  "version": 1,
  "synopsis": {
    "one_sentence_overview": "本系列围绕多智能体协作、Agent 框架选型、依赖准备与典型框架实战展开。",
    "main_storyline": "先讲 AI 从聊天模式到 Agentic AI 的演进，再完成环境准备，最后进入 JManus 与 AgentScope 的框架导读。",
    "topic_groups": [
      {
        "topic": "趋势与核心理念",
        "video_ids": [
          "1-1 多Agent融合自主决策，AI发展的必然趋势"
        ],
        "summary": "解释 AI 从聊天、Copilot 到 Agent、多 Agent 协作的演进路径。"
      }
    ],
    "learning_path": [
      "先建立趋势认知",
      "再完成依赖准备",
      "最后理解具体框架"
    ],
    "video_briefs": [
      {
        "video_id": "1-7 具备ReAct核心能力的框架：AgentScope",
        "brief": "介绍 AgentScope 的 ReAct 思维模式、生产级安全沙箱和人工介入机制。"
      }
    ]
  },
  "stale": false,
  "updated_at": "2026-05-02T12:00:00Z"
}
```

### 5.3 `query_understanding`

以问题“这个系列讲了啥”为例：

```json
{
  "normalized_query": "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
  "subqueries": [
    "这个系列主要讲哪些主题",
    "这个系列的学习顺序是什么"
  ],
  "filters": {
    "series_id": "1"
  },
  "retrieval_hints": {
    "prefer_source_types": [
      "series_synopsis",
      "summary_global",
      "summary_chapter"
    ],
    "allow_source_types": [
      "series_synopsis",
      "summary_global",
      "summary_chapter",
      "transcript_chunk"
    ],
    "need_exact_quote": false,
    "need_timeline": false,
    "need_procedure_continuity": false,
    "top_k": 8
  }
}
```

### 5.4 `retrieval_request`

```json
{
  "query": "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
  "subqueries": [
    "这个系列主要讲哪些主题",
    "这个系列的学习顺序是什么"
  ],
  "filters": {
    "series_id": "1"
  },
  "source_policy": {
    "prefer_source_types": [
      "series_synopsis",
      "summary_global",
      "summary_chapter"
    ],
    "allow_source_types": [
      "series_synopsis",
      "summary_global",
      "summary_chapter",
      "transcript_chunk"
    ]
  },
  "retrieval_options": {
    "hybrid": true,
    "rerank": true,
    "top_k": 8
  }
}
```

### 5.5 `retrieval_hits`

```json
{
  "query": "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
  "hits": [
    {
      "evidence_id": "e1",
      "doc_id": "series:1:synopsis",
      "series_id": "1",
      "video_id": null,
      "source_type": "series_synopsis",
      "source_family": "summary",
      "title": "1 - 系列总览",
      "chapter_title": null,
      "start_seconds": null,
      "end_seconds": null,
      "score": 0.97,
      "text": "本系列围绕多智能体协作、Agent 框架选型、依赖准备与典型框架实战展开。"
    },
    {
      "evidence_id": "e2",
      "doc_id": "series:1:video:1-1:summary_global",
      "series_id": "1",
      "video_id": "1-1 多Agent融合自主决策，AI发展的必然趋势",
      "source_type": "summary_global",
      "source_family": "summary",
      "title": "1-1 多Agent融合自主决策，AI发展的必然趋势",
      "chapter_title": null,
      "start_seconds": null,
      "end_seconds": null,
      "score": 0.93,
      "text": "视频梳理了AI从聊天模式到Copilot、再到Agent及多Agent协同的演进趋势。"
    }
  ],
  "diagnostics": {
    "candidate_count": 24,
    "reranked_count": 8,
    "returned_count": 2
  }
}
```

### 5.6 `answer_payload`

```json
{
  "answer": "这个系列主要分三块：第一块是 AI 从聊天模式、Copilot 到 Agentic AI 的演进；第二块是课程依赖准备；第三块是 JManus 和 AgentScope 这类多智能体框架导读。",
  "citations": [
    {
      "evidence_id": "e1",
      "video_id": null,
      "title": "1 - 系列总览",
      "chapter_title": null,
      "start_seconds": null,
      "end_seconds": null
    },
    {
      "evidence_id": "e2",
      "video_id": "1-1 多Agent融合自主决策，AI发展的必然趋势",
      "title": "1-1 多Agent融合自主决策，AI发展的必然趋势",
      "chapter_title": null,
      "start_seconds": null,
      "end_seconds": null
    }
  ],
  "used_source_types": [
    "series_synopsis",
    "summary_global"
  ]
}
```

---

## 6. 目标 `debug_trace` 结构

### 6.1 当前 debug trace 的问题

当前已经有：

- `graph_input`
- `graph_result`
- `series_planner`
- `series_planner_attempts`
- `series_aggregator`
- `pinpoint`
- `tool_results`
- `citations`

但对新链路来说，这些字段不够直接，仍然过于贴旧 graph。

### 6.2 改造后的目标结构

```json
{
  "graph_input": {
    "session_id": "series|1|series-home|debug-overview",
    "scope_type": "series",
    "series_id": "1",
    "video_id": "",
    "user_message": "这个系列讲了啥"
  },
  "series_query_processor": {
    "catalog_snapshot": {
      "series_id": "1",
      "video_count": 8
    },
    "input": {
      "user_message": "这个系列讲了啥"
    },
    "output": {
      "normalized_query": "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
      "subqueries": [
        "这个系列主要讲哪些主题",
        "这个系列的学习顺序是什么"
      ],
      "filters": {
        "series_id": "1"
      },
      "retrieval_hints": {
        "prefer_source_types": [
          "series_synopsis",
          "summary_global",
          "summary_chapter"
        ],
        "allow_source_types": [
          "series_synopsis",
          "summary_global",
          "summary_chapter",
          "transcript_chunk"
        ],
        "need_exact_quote": false,
        "need_timeline": false,
        "need_procedure_continuity": false,
        "top_k": 8
      }
    }
  },
  "retrieval_request": {
    "query": "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
    "filters": {
      "series_id": "1"
    }
  },
  "retrieval_response": {
    "returned_count": 5,
    "hits": [
      {
        "evidence_id": "e1",
        "source_type": "series_synopsis",
        "video_id": null
      }
    ]
  },
  "answer_synthesis": {
    "input": {
      "user_query": "这个系列讲了啥",
      "evidence_count": 5
    },
    "output": {
      "answer": "....",
      "used_source_types": [
        "series_synopsis",
        "summary_global"
      ]
    }
  },
  "graph_result": {
    "assistant_message": "...."
  }
}
```

### 6.3 必须新增的 debug 字段

1. `series_query_processor`
2. `retrieval_request`
3. `retrieval_response`
4. `answer_synthesis`

### 6.4 需要逐步下掉的旧字段

1. `series_planner`
2. `series_planner_attempts`
3. `current_subplan`
4. 任何以 `selected_videos/subplans/target_video_ids` 为核心的 debug 输出

---

## 7. 调试脚本与验收脚本

### 7.1 `scripts/analysis/run_series_scope_debug_trace.py`

目标：

1. 单次运行 series scope 问题
2. 直接生成完整 `debug_trace`
3. 保存到 `temp/series-scope-traces/`

建议支持参数：

```text
--case overview
--case concept
--case locate
--save
```

建议输出结构：

```json
{
  "case": "overview",
  "session_id": "series|1|series-home|trace-overview",
  "message": "这个系列讲了啥",
  "assistant_message": "...",
  "debug_trace": {
    "...": "..."
  }
}
```

### 7.2 `scripts/regression/check_series_scope_contracts.py`

目标：

1. 读取 `debug_trace`
2. 对比理想合同
3. 给出结构验收结果

必须检查：

1. `query_understanding` schema 是否齐全
2. `retrieval_hits` 中是否出现预期的 `source_type`
3. `answer_payload.used_source_types` 是否符合预期
4. 是否还残留旧字段

输出建议：

```json
{
  "case": "overview",
  "passed": true,
  "checks": [
    {
      "name": "query_understanding_schema",
      "passed": true
    },
    {
      "name": "retrieval_prefers_series_synopsis",
      "passed": true
    },
    {
      "name": "no_legacy_subplans",
      "passed": true
    }
  ]
}
```

---

## 8. 验收标准

### 8.1 资产层验收

#### A. `series_catalog.json`

必须满足：

1. 每个 processed 视频都有一条记录
2. `one_sentence_summary` 非空
3. `chapter_titles == [chapter.title for chapter in chapters]`
4. 不包含 transcript 正文

#### B. `series_overview.json`

必须满足：

1. 文件存在
2. schema 合法
3. `topic_groups` 非空
4. `learning_path` 非空
5. `stale` 标记行为正确

### 8.2 运行时合同验收

#### A. Query Processor

必须满足：

1. 不再输出 `selected_videos`
2. 不再输出 `selection_mode`
3. 不再输出 `subplans`
4. 不再输出 `target_video_ids`
5. 输出 `normalized_query/subqueries/filters/retrieval_hints`

#### B. Retrieval

必须满足：

1. `source_type` 只来自白名单
2. overview case 至少命中一个 `series_synopsis`
3. locate case 至少命中一个 `transcript_chunk` 或 `summary_chapter`
4. concept/compare case 允许 `summary + transcript` 混合命中

#### C. Answer

必须满足：

1. `answer_payload` schema 合法
2. `used_source_types` 与实际引用一致
3. 不暴露 `doc_id/score/internal fields`
4. 对定位问题能返回视频标题和大致位置

### 8.3 行为层验收

#### 用例 1：overview

问题：

- `这个系列讲了啥`

必须满足：

1. `query_understanding.retrieval_hints.prefer_source_types` 第一优先包含 `series_synopsis`
2. 命中结果包含 `series_synopsis`
3. 回答提到主题分组或学习脉络

#### 用例 2：concept

问题：

- `Copilot 模式是啥`

必须满足：

1. 命中结果允许同时出现 `summary_global` 和 `transcript_chunk`
2. 回答不只给一句定义
3. 回答能说明其在系列中的上下文

#### 用例 3：locate

问题：

- `哪一节讲过 Nacos 3`

必须满足：

1. 命中 `summary_chapter` 或 `transcript_chunk`
2. 回答给出视频标题
3. 回答给出大致位置或章节含义

### 8.4 不能使用的错误验收方式

下面这些验收方式应明确禁止：

1. 只看最终回答“感觉差不多”
2. 要求最终自然语言 `answer` 与样例文本逐字全等
3. 只测 overview，不测 concept 和 locate
4. 只测成功链路，不测 debug trace 中间产物

原因：

1. 自然语言回答允许表述波动
2. 真正稳定的是结构合同和证据命中规律
3. 如果只做文本全等，会把正常的自然语言波动误判成失败

因此应采用：

1. **结构精确校验**
2. **关键字段精确校验**
3. **source_type / video_id / evidence 级别校验**
4. **回答文本的弱约束校验**

---

## 9. 分阶段实施顺序

### 阶段 1：先加资产与调试能力

先做：

1. `series_catalog.json`
2. `series_overview.json`
3. `run_series_scope_debug_trace.py`
4. `check_series_scope_contracts.py`

目标：

1. 先把理想中间产物打出来
2. 让“可观测性”先建立
3. 不先急着大拆 graph

### 阶段 2：引入 `SeriesQueryProcessor`

再做：

1. 新建 `series_query_processor.py`
2. 新增 query understanding model
3. series scope 改走新合同

### 阶段 3：收缩 graph

再做：

1. 下掉 `subplans`
2. 下掉 `selected_videos`
3. 下掉 `target_video_ids`
4. 合并为单一 retrieval 节点

### 阶段 4：回答层和验收闭环

最后做：

1. 新 answer synthesizer
2. 完整 contract test
3. 旧 planner / old graph 分支清理

---

## 10. 完成定义

只有同时满足以下条件，才能认为 series scope 重构完成：

1. `series_catalog.json` 与 `series_overview.json` 已落地
2. `SeriesQueryProcessor` 已替代 `SeriesPlanner` 成为新链路入口
3. series scope 不再依赖 `selected_videos / subplans / target_video_ids`
4. retrieval 已统一为单入口
5. `debug_trace` 已能稳定输出新合同中间产物
6. overview / concept / locate 三类用例都通过合同测试
7. 验收脚本不再依赖最终回答文本全等
