# Series Scope RAG SPEC

## 1. 文档目的

本文是 `series scope` 重构的技术规格说明书。  
后续代码改动应严格以本文为合同，不以口头理解为准。

---

## 2. 设计目标

将当前 `series scope` 链路从：

```text
planner
-> selected_videos / subplans
-> execute_summary / execute_video_graph / execute_video_workflow
-> series_aggregator
```

收敛为：

```text
SeriesQueryProcessor
-> UnifiedRetrieval
-> SeriesAnswerSynthesizer
```

核心要求：

1. 查询理解只做 query understanding，不编排执行图
2. summary / transcript 进入统一检索体系
3. overview 问题拥有 series 级高层语料
4. 回答只基于已召回证据进行组织

---

## 2.1 基线系列语义假设

为了让数据流、fixture 和验收标准足够具体，本文默认以当前仓库里的 `series_id=1` 作为基线样本系列。

基于现有 `summary.json`，这个系列目前可近似理解成 4 个主题簇：

1. **趋势与核心理念**
   - `1-1 多Agent融合自主决策，AI发展的必然趋势`
   - `1-3-3 初识LLMOps，为什么需要LLMOps【itjc8.com】`
2. **环境与前置准备**
   - `1-2 准备工作：安装ApiFox`
   - `1-3 准备工作：配置阿里大模型广场的ApiKey`
   - `1-4 准备工作：百度地图API秘钥(AK)`
   - `1-5 准备工作：安装Nacos 3`
3. **框架导读**
   - `1-6 仿Manus能自主决策的框架：Jmanus`
   - `1-7 具备ReAct核心能力的框架：AgentScope`
4. **运行形态与自主代理能力**
   - 由 `1-1` 中关于聊天模式、Copilot、Agent、Agentic AI 的章节承担

后文所有“理想中间产物”和“验收 fixture”都以这一基线假设为例。

---

## 3. 涉及模块与文件树

### 3.1 修改文件

```text
src/backend/video_summary/infrastructure/filesystem_video_workspace.py
src/backend/video_summary/library/ports.py
src/backend/video_summary/library/usecases/summary_generation.py
src/backend/agent_graph/query/models.py
src/backend/agent_graph/runtime/graph.py
src/backend/agent_graph/runtime/nodes.py
src/backend/agent_graph/evidence/retrieval.py
src/backend/agent_graph/query/series_aggregator.py
src/backend/api/bootstrap.py
src/backend/api/routes/agent.py
scripts/analysis/run_speed_profile.py
```

### 3.2 新增文件

```text
src/backend/video_summary/library/usecases/series_synopsis_generation.py
src/backend/agent_graph/query/series_query_processor.py
src/backend/agent_graph/query/series_answer_synthesizer.py
src/backend/agent_graph/evidence/document_schema.py
src/backend/agent_graph/evidence/index_builder.py
scripts/analysis/run_series_scope_debug_trace.py
scripts/regression/check_series_scope_contracts.py
tests/agent/test_series_scope_contracts.py
tests/fixtures/series_scope/overview.expected.json
tests/fixtures/series_scope/concept.expected.json
tests/fixtures/series_scope/locate.expected.json
```

---

## 4. 资产层设计

## 4.1 Series Catalog

### 目标

提供一个只包含轻量目录信息的系列级资产，用于：

1. 查询理解
2. retrieval 过滤与增强
3. answer 组织辅助

### Schema

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
        "2023年：聊天模式与大号搜索引擎"
      ],
      "processed": true,
      "tags": []
    }
  ],
  "updated_at": "2026-05-02T12:00:00Z"
}
```

### 规则

1. `one_sentence_summary` 直接取自 video summary 真实字段
2. `chapter_titles` 必须由 `chapters[*].title` 派生
3. 不包含 transcript segment 正文
4. 不包含 planner 所需的历史执行字段
5. `series_catalog.json` 是代码派生资产，不走模型生成

## 4.2 Series Synopsis

### 目标

提供一个 series 级高层摘要资产，作为 overview 问题的高层证据。

### Schema

```json
{
  "series_id": "1",
  "series_title": "1",
  "version": 1,
  "synopsis": {
    "overview": "本系列围绕多智能体协作、Agent 框架选型、依赖准备与典型框架实战展开。",
    "topic_groups": [
      {
        "topic": "趋势与核心理念",
        "video_ids": ["1-1 多Agent融合自主决策，AI发展的必然趋势"],
        "description": "解释 AI 从聊天、Copilot 到 Agent、多 Agent 协作的演进路径。"
      },
      {
        "topic": "环境与前置准备",
        "video_ids": [
          "1-2 准备工作：安装ApiFox",
          "1-3 准备工作：配置阿里大模型广场的ApiKey",
          "1-4 准备工作：百度地图API秘钥(AK)",
          "1-5 准备工作：安装Nacos 3"
        ],
        "description": "覆盖工具安装、密钥申请、地图 AK 配置和 Nacos 3 安装。"
      },
      {
        "topic": "框架导读",
        "video_ids": [
          "1-6 仿Manus能自主决策的框架：Jmanus",
          "1-7 具备ReAct核心能力的框架：AgentScope"
        ],
        "description": "介绍 JManus 和 AgentScope 两类多智能体框架及其差异。"
      }
    ],
    "learning_path": [
      "先看趋势与核心理念",
      "再完成环境与前置准备",
      "最后进入框架导读"
    ]
  },
  "stale": false,
  "updated_at": "2026-05-02T12:00:00Z"
}
```

### 规则

1. synopsis 基于轻量 summary 资产生成，不直接吞全量 transcript
2. synopsis 不应成为 series 问答可用性的硬前提
3. synopsis 过期时仍允许系统用旧 synopsis + 最新 summary 回答
4. `overview` 是唯一的系列总述字段
5. 不再保留 `main_storyline`
6. 不再保留 `video_briefs`
7. `topic_groups[*].description` 只负责解释该主题组，不重复承担整个系列总述

## 4.3 长期知识记忆更新

本项目中的长期知识记忆包括：

1. `summary.json`
2. `transcript.cleaned.json`
3. `series_catalog.json`
4. `series_overview.json`
5. unified retrieval index / RAG 数据库

这些资产不属于 session 对话记忆，不通过对话 graph 的 memory 节点更新。

更新规则：

1. 单视频 `summary` 成功生成后，视为该视频对应的长期知识记忆已更新
2. 单视频 `summary` 成功生成后，必须触发所属 series 的 `series_catalog.json` 重建
3. 单视频 `summary` 成功生成后，必须触发所属 series 的 `series_overview.json` 重建
4. 单视频 `summary` 成功生成后，必须触发所属 series 的 unified retrieval index 刷新
5. 查询链路只消费长期知识记忆，不承担知识记忆构建职责
6. `series_catalog.json` / `series_overview.json` / unified retrieval index 的刷新允许异步执行
7. 异步刷新失败不能阻塞问答主链路，只能记录状态并等待重试

---

## 5. 数据流与状态管理

## 5.1 运行时状态

新链路下，`series scope` 的核心状态只保留：

```json
{
  "query_understanding": {},
  "retrieval_request": {},
  "retrieval_results": {},
  "answer_payload": {}
}
```

不再让主链路依赖：

```json
{
  "selected_videos": [],
  "selection_mode": "fresh",
  "subplans": [],
  "target_video_ids": []
}
```

## 5.1.1 Session 短期记忆

`series scope` 仍然保留 session 内短期记忆，但它不属于 RAG 知识记忆。

短期记忆保存内容：

1. 当前 session 内全部 `user_message`
2. 当前 session 内全部 `assistant_message`
3. 必要的 tool outputs / turn 结果元信息
4. `history_summary` 或等价压缩结果

规则：

1. session 内 turn 记录默认完整持久化，不采用“只保留前 N 轮”策略
2. 只有接近上下文上限时，才对送入模型的历史上下文执行压缩
3. 压缩的是上下文表示，不是底层 turn 存储本身
4. RAG 命中的知识正文、transcript chunk、summary 文本不写回 session memory

## 5.1.2 Runtime Graph 主路径

`series scope` 的目标 graph 主路径应收敛为：

```mermaid
flowchart LR
    A[用户提问] --> B[understand_query]
    B --> C[retrieve_evidence]
    C --> D[synthesize_answer]
    D --> E[finalize]
    E --> F[update_session_memory]
```

其中：

1. `update_session_memory` 只负责更新短期会话记忆
2. `update_session_memory` 不负责更新长期知识记忆
3. 长期知识记忆刷新走 summary 生成后的资产管线，而不是问答收尾节点
4. `synthesize_answer` 是 `SeriesAnswerSynthesizer` 的 graph 节点语义，不再回退到旧 `SeriesAggregator` 主路径

## 5.2 Query Understanding 合同

```json
{
  "normalized_query": "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
  "subqueries": [
    "这个系列主要讲哪些主题",
    "这个系列的学习顺序是什么"
  ],
  "filters": {
    "series_id": "1"
  }
}
```

### 规则

1. Query Processor 不输出 `selected_videos`
2. Query Processor 不输出 `subplans`
3. Query Processor 不输出 `target_video_ids`
4. Query Processor 只指导 retrieval，不编排 graph
5. Query Processor 只输出：
   - `normalized_query`
   - `subqueries`
   - `filters`
6. 默认不输出 `task_type`
7. 默认不输出 `retrieval_hints`
8. 默认采用统一混合检索，由 retrieval + rerank 决定证据排序

## 5.3 Retrieval Hit 合同

```json
{
  "evidence_id": "e1",
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
```

### `source_type` 枚举定义

内部统一证据标签仅允许：

1. `series_synopsis`
2. `summary_global`
3. `summary_chapter`
4. `transcript_chunk`
5. `note`
6. `knowledge_card`

不再使用含糊的：

1. `summary`
2. `chapter`

说明：

1. `source_type` 是内部证据标签，主要服务于调试、排障和粗粒度观察
2. 它不直接服务业务，不应成为对最终体验的硬门槛
3. 验收时可以参考它看“系统大致依赖了哪类证据”，但不应对具体组合过度苛刻

## 5.4 Answer Payload 合同

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
    }
  ],
  "used_source_types": [
    "series_synopsis",
    "summary_global"
  ]
}
```

### 规则

1. `answer` 是自然语言，可有措辞波动
2. `used_source_types` 可作为内部观测信息，帮助理解回答主要依赖了哪些证据类型
3. 不暴露 `doc_id`、`score`、内部 matched 字段

---

## 6. API Contracts

## 6.1 对外 HTTP 接口

本次重构默认不新增面向用户的主问答 HTTP 接口，只保持现有接口语义稳定。

### `POST /api/agent/chat`

#### Request

```json
{
  "session_id": "series|1|series-home|manual-test",
  "message": "这个系列讲了啥",
  "context": {
    "scope_type": "series",
    "series_id": "1",
    "series_title": "1",
    "video_id": null,
    "video_title": null,
    "selected_tool": "series-home"
  }
}
```

#### 200 Response

```json
{
  "assistant_message": "这个系列主要分三块：……",
  "scope_type": "series",
  "reason": "...",
  "tool_results": [],
  "citations": []
}
```

#### 503 Response

```json
{
  "detail": "Agent runtime failed"
}
```

### `POST /api/agent/chat/stream`

#### Request

与 `/api/agent/chat` 相同。

#### 200 Response

SSE 流，不变。

### `POST /api/agent/context/usage`

保持不变。

### `POST /api/agent/session/recover`

保持不变。

### `POST /api/agent/session/clear`

保持不变。

## 6.2 内部合同

本次重构的真正关键是内部合同，必须按以下顺序稳定输出：

1. `SeriesQueryUnderstanding`
2. `RetrievalRequest`
3. `RetrievalHit[]`
4. `SeriesAnswerPayload`

---

## 7. 边缘情况与异常处理

这一节必须视为强约束，不允许“后续再补”。

### 7.1 Synopsis 不存在

策略：

1. 不报错
2. 直接回退到 unified retrieval
3. 后台异步创建 synopsis

### 7.2 Synopsis 过期

策略：

1. 允许继续使用旧 synopsis
2. 补充最新 summary 资产
3. 必要时 transcript 继续参与检索

### 7.3 Summary 缺失

策略：

1. catalog 中该视频 `processed=false`
2. 不参与高层 summary 资产构建
3. 如果 transcript 存在，仍允许进入 unified retrieval

### 7.4 Transcript 缺失

策略：

1. overview 问题仍可回答
2. concept / locate 问题允许降级为 summary 级回答
3. 若问题显式需要原话或定位，应明确说明证据粒度不足

### 7.5 Retrieval 无命中

策略：

1. 不返回空字符串
2. answer 层返回简短、明确的“当前未找到足够证据”
3. debug trace 中必须记录 zero-hit

### 7.5.1 默认检索策略

默认策略是：

1. 统一混合检索
2. 不在 query understanding 阶段先验写死问题类型
3. 不在 query understanding 阶段先验写死 `source_type` 优先级
4. 不在 query understanding 阶段输出检索控制 hint
5. 让 hybrid retrieval + rerank 决定最终证据顺序

只有极少数硬场景，才允许 retrieval 内部增加 source 级约束，例如：

1. 用户明确要求原话
2. 用户明确要求时间点
3. 用户明确要求连续流程还原

即便如此，这类 source 约束也属于 retrieval 内部策略，不应成为默认的 query understanding 输出合同。

### 7.6 旧链路字段残留

策略：

1. 新链路 debug trace 若仍频繁出现 `subplans/selected_videos/target_video_ids`，说明迁移尚未收敛
2. 这类字段应作为迁移完成度检查项，而不是对单次问答体验的硬失败条件

### 7.7 自然语言答案波动

策略：

1. 不以最终文本全等作为主验收方式
2. 业务体验验收优先于内部字段比对
3. 结构合同、证据命中、关键字段只作为辅助检查

---

## 8. 技术约束

### 8.1 必须遵守

1. 不能继续强化 `SeriesPlanner`，只能逐步替换它
2. 不能再往新链路里引入新的 `subplans` 协议
3. 不能把 `chapter_titles` 设计成模型重复输出字段
4. 不能把索引构建继续放在用户首问链路里
5. 不能用“最终回答看起来差不多”代替结构验收
6. 不能把 `source_type` 先验优先级写死成默认 query understanding 合同
7. 不能把 `task_type` 写成默认 query understanding 合同
8. 不能把检索控制 hint 写成默认 query understanding 合同

### 8.2 当前仓库约束

1. 保持现有 FastAPI 对外接口兼容
2. 保持现有 workspace 目录结构可兼容迁移
3. 允许新增 `series_overview.json` 与 `series_catalog.json`
4. 禁止引入新的第三方上传式黑盒 RAG SDK 来整体替代现有实现

---

## 9. 调试与可观测性要求

必须新增可观测性，而不是只保留日志。

## 9.1 目标 `debug_trace` 字段

必须能输出：

1. `graph_input`
2. `series_query_processor`
3. `retrieval_request`
4. `retrieval_response`
5. `answer_synthesis`
6. `graph_result`

如果需要观察 memory 行为，允许在 `graph_result` 或专门的 session trace 中看到：

1. 本轮是否更新了 `update_session_memory`
2. 本轮是否触发了历史压缩

但不要求把长期知识记忆刷新过程塞进对话 trace。

## 9.2 禁止只输出旧 debug 字段

以下字段若仍是主字段，说明重构未完成：

1. `series_planner`
2. `series_planner_attempts`
3. `current_subplan`

## 9.3 调试脚本要求

必须提供：

1. 单次 trace 脚本
2. 合同检查脚本
3. pytest 回归测试

## 9.4 如何获取中间产物

必须通过脚本直接拿到，而不是只看日志。

### 脚本一：生成实际 trace

建议脚本：

```text
python scripts/analysis/run_series_scope_debug_trace.py --case overview --save
python scripts/analysis/run_series_scope_debug_trace.py --case concept --save
python scripts/analysis/run_series_scope_debug_trace.py --case locate --save
```

建议输出目录：

```text
temp/series-scope-traces/
  overview.actual.json
  concept.actual.json
  locate.actual.json
```

每个 `.actual.json` 至少包含：

```json
{
  "case": "overview",
  "session_id": "series|1|series-home|trace-overview",
  "message": "这个系列讲了啥",
  "assistant_message": "...",
  "debug_trace": {
    "graph_input": {},
    "series_query_processor": {},
    "retrieval_request": {},
    "retrieval_response": {},
    "answer_synthesis": {},
    "graph_result": {}
  }
}
```

### 脚本二：对比实际 trace 与理想 fixture

建议脚本：

```text
python scripts/regression/check_series_scope_contracts.py --case overview
python scripts/regression/check_series_scope_contracts.py --case concept
python scripts/regression/check_series_scope_contracts.py --case locate
```

建议读取：

```text
tests/fixtures/series_scope/overview.expected.json
tests/fixtures/series_scope/concept.expected.json
tests/fixtures/series_scope/locate.expected.json
```

输出建议：

```json
{
  "case": "overview",
  "passed": true,
  "diffs": [],
  "checks": [
    {
      "name": "must_have_trace_keys",
      "passed": true
    },
    {
      "name": "trace_is_structurally_complete",
      "passed": true
    }
  ]
}
```

### 9.5 diff 比较规则

`check_series_scope_contracts.py` 不能做“整份 JSON 全等”，而必须按分层规则比较：

#### 严格相等

这些字段必须全等：

1. `series_query_processor.output.filters.series_id`
2. `must_have_trace_keys`
3. `must_not_have_trace_keys`

#### 集合包含

这些字段采用“至少包含”规则：

1. `answer_synthesis.output.used_source_types`

#### 证据命中包含

这些字段采用“hits 至少命中某些对象”规则：

1. 某个 `source_type`
2. 某个 `video_id`
3. 某个 `chapter_title`

#### 文本弱约束

这些字段只做关键词包含，不做全等：

1. `answer_synthesis.output.answer`
2. `graph_result.assistant_message`

### 9.6 建议的 diff 输出格式

如果不通过，建议输出：

```json
{
  "case": "locate",
  "passed": false,
  "diffs": [
    {
      "path": "series_query_processor.output.filters.series_id",
      "expected": "1",
      "actual": "2"
    },
    {
      "path": "retrieval_response.hits",
      "expected_observation": "should usually contain evidence from video 1-5 about Nacos 3",
      "actual": [
        {
          "video_id": "1-1 多Agent融合自主决策，AI发展的必然趋势",
          "source_type": "summary_global"
        }
      ]
    }
  ]
}
```

### 9.7 当前推荐的 Query Understanding 最小合同

为了贴近最佳实践，当前推荐的最小合同就是：

```json
{
  "normalized_query": "定位系列中提到 Nacos 3 的视频、章节和大致位置",
  "subqueries": [
    "Nacos 3",
    "安装 Nacos 3",
    "Nacos 3 端口"
  ],
  "filters": {
    "series_id": "1"
  }
}
```

也就是说：

1. 不输出 `task_type`
2. 不输出 `retrieval_hints`
3. 只保留 query rewrite、decomposition、metadata filter

---

## 10. 验收标准

## 10.1 结构验收

结构验收的定位是：

1. 防止链路明显跑偏
2. 保证调试信息足够可用
3. 不取代业务体验验收

建议满足：

1. `query_understanding` schema 合法
2. `retrieval_hits` schema 合法
3. `answer_payload` schema 合法
4. 新链路不再主依赖 `selected_videos/subplans/target_video_ids`

## 10.1.1 验收不是“文本全等”，而是“理想中间产物 vs 实际中间产物”

本项目后续验收建议采用：

1. **理想 trace fixture**
2. **实际 trace 输出**
3. **结构化 diff 检查**

而不是只看最终回答好不好看。

验收对象不是单一 `assistant_message`，而是下面 5 层中间产物：

1. `series_query_processor.output`
2. `retrieval_request`
3. `retrieval_response.hits`
4. `answer_synthesis.output`
5. `graph_result.assistant_message`

其中：

1. 前 4 层是主要排障对象
2. 第 5 层是最终用户体验对象

## 10.1.2 理想 fixture 的写法

fixture 不能只存一份“期望回答文本”，必须存：

```json
{
  "case": "overview",
  "input": {
    "session_id": "series|1|series-home|trace-overview",
    "message": "这个系列讲了啥"
  },
  "assertions": {
    "must_have_trace_keys": [
      "graph_input",
      "series_query_processor",
      "retrieval_request",
      "retrieval_response",
      "answer_synthesis",
      "graph_result"
    ],
    "must_not_have_trace_keys": [
      "series_planner",
      "series_planner_attempts",
      "current_subplan",
      "task_type",
      "retrieval_hints"
    ],
    "path_equals": {
      "series_query_processor.output.filters.series_id": "1"
    },
    "path_contains_values": {
      "answer_synthesis.output.used_source_types": [
        "series_synopsis"
      ]
    },
    "hits_must_contain": [
      {
        "source_type": "series_synopsis"
      },
      {
        "video_id": "1-1 多Agent融合自主决策，AI发展的必然趋势"
      },
      {
        "video_id": "1-6 仿Manus能自主决策的框架：Jmanus"
      },
      {
        "video_id": "1-7 具备ReAct核心能力的框架：AgentScope"
      }
    ],
    "answer_must_contain": [
      "多智能体",
      "环境准备",
      "JManus",
      "AgentScope"
    ]
  }
}
```

说明：

1. `path_equals` 用于严格字段
2. `path_contains_values` 用于集合字段
3. `hits_must_contain` 用于粗粒度证据观察
4. `answer_must_contain` 只做弱约束，不做整句全等

## 10.2 行为验收

### overview

问题：

- `这个系列讲了啥`

业务上理想应满足：

1. 命中 `series_synopsis`
2. 回答体现主题分组或学习脉络

### overview 的理想节点流向

```text
understand_query
-> retrieve_evidence
-> answer
-> finalize
-> update_session_memory
```

### overview 的理想中间产物

#### A. `series_query_processor.output`

```json
{
  "normalized_query": "这个系列主要讲哪些主题，以及推荐的学习顺序是什么？",
  "subqueries": [
    "这个系列主要讲哪些主题",
    "这个系列的学习顺序是什么"
  ],
  "filters": {
    "series_id": "1"
  }
}
```

#### B. `retrieval_response.hits`

理想上通常会包含：

```json
[
  { "source_type": "series_synopsis" },
  { "video_id": "1-1 多Agent融合自主决策，AI发展的必然趋势" },
  { "video_id": "1-6 仿Manus能自主决策的框架：Jmanus" },
  { "video_id": "1-7 具备ReAct核心能力的框架：AgentScope" }
]
```

#### C. `answer_synthesis.output`

回答中通常应体现：

1. 这个系列不只是一堆零散视频
2. 存在“趋势/理念”“环境准备”“框架导读”这类结构化分组
3. 推荐用户按一定学习顺序看
4. 即使存在 transcript 命中，也不影响高层 summary / synopsis 成为主要证据

### concept

问题：

- `Copilot 模式是啥`

业务上理想应满足：

1. 命中 `summary` 和/或 `transcript`
2. 回答包含定义与上下文

### concept 的理想节点流向

```text
understand_query
-> retrieve_evidence
-> answer
-> finalize
-> update_session_memory
```

### concept 的理想中间产物

#### A. `series_query_processor.output`

```json
{
  "normalized_query": "Copilot 模式的定义、作用，以及它在本系列中的上下文",
  "subqueries": [
    "Copilot 模式是什么",
    "Copilot 模式和 Agent 模式有什么区别"
  ],
  "filters": {
    "series_id": "1"
  }
}
```

#### B. `retrieval_response.hits`

理想上通常会包含以下命中之一：

```json
[
  {
    "video_id": "1-1 多Agent融合自主决策，AI发展的必然趋势",
    "source_type": "summary_chapter",
    "chapter_title": "2024年：Copilot模式与副驾驶角色"
  },
  {
    "video_id": "1-1 多Agent融合自主决策，AI发展的必然趋势",
    "source_type": "transcript_chunk"
  }
]
```

#### C. `answer_synthesis.output`

回答中通常应体现：

1. Copilot 是“副驾驶”而不是全自动代理
2. 它处于聊天模式与 Agent 模式之间
3. 人仍然需要主导整体结构或调试

### locate

问题：

- `哪一节讲过 Nacos 3`

业务上理想应满足：

1. 命中 `summary_chapter` 或 `transcript_chunk`
2. 回答给出视频标题和大致位置

### locate 的理想节点流向

```text
understand_query
-> retrieve_evidence
-> answer
-> finalize
-> update_session_memory
```

### locate 的理想中间产物

#### A. `series_query_processor.output`

```json
{
  "normalized_query": "定位系列中提到 Nacos 3 的视频、章节和大致位置",
  "subqueries": [
    "Nacos 3",
    "安装 Nacos 3",
    "Nacos 3 端口"
  ],
  "filters": {
    "series_id": "1"
  }
}
```

#### B. `retrieval_response.hits`

理想上通常会包含：

```json
[
  {
    "video_id": "1-5 准备工作：安装Nacos 3",
    "source_type": "summary_chapter",
    "chapter_title": "端口说明与新特性"
  },
  {
    "video_id": "1-5 准备工作：安装Nacos 3",
    "source_type": "transcript_chunk"
  }
]
```

#### C. `answer_synthesis.output`

回答中通常应体现：

1. 是在 `1-5 准备工作：安装Nacos 3` 这节
2. 是安装/端口说明相关部分
3. 至少给出“大致位置”或“章节含义”

## 10.3 业务体验优先原则

最终是否通过，优先看：

1. 用户问法是否被自然回答
2. 回答是否有足够证据感
3. 定位类问题是否真的定位到了
4. concept / overview 问题是否不再显得过浅

只有当业务体验明显异常时，才回头深入看 trace 和内部字段。

## 10.4 性能验收

建议满足：

1. 首问不再承担“全量索引首次构建”的交互成本
2. 至少可以通过调试脚本证明，查询链路与索引构建链路已拆开

---

## 11. 审核重点

你审核这份 SPEC 时，建议重点看：

1. 文件范围是否合理
2. 新运行合同是否足够清晰
3. API 契约是否和当前接口兼容
4. 边缘情况是否写漏
5. 技术约束是否足够硬

如果 SPEC 拍板，后续 TASKS 只负责把它拆成执行步骤，不再改方向。
