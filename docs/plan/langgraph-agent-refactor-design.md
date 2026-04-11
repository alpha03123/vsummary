# LangGraph Agent Refactor Design

## 背景

当前后端 agent 已经演化出一整层自定义平台能力，主要集中在：

- `src/backend/agent/runtime`
- `src/backend/agent/session`
- `src/backend/agent/memory`
- `src/backend/agent/validation`
- `src/backend/agent/context`

这些目录里混合了以下职责：

- agent workflow 编排
- 工具调用循环
- 结构化输出修复
- 会话持久化与恢复
- memory / evidence cache
- retrieval 路由
- prompt 契约与 planner 修复

结果是每次新增一个能力，都需要同时改多层抽象，导致系统持续复杂化，并且在 runtime/platform 层重复造轮子。

本次重构的目标，不是继续优化当前自定义 runtime，而是用成熟框架收编平台职责，只保留业务逻辑。

## 重构目标

本次重构只聚焦 **后端 agent**，不重做前端，也不重做视频转写/摘要离线流程。

目标如下：

1. 用 `LangGraph` 取代当前自定义 agent runtime 编排。
2. 第一阶段即引入 `DSPy`，优先替换大段 prompt，改成 `Signature + Module` 形式的程序化节点。
3. 用现成 retrieval / storage 能力取代自定义 evidence orchestration。
4. 用现成 structured tool calling / validation 能力减少 schema repair 代码。
5. 把当前后端 agent 收敛成少量高内聚模块，避免继续碎片化扩张。
6. 第一阶段构建统一的 `video + series` 问答 graph，不再把两类 scope 维护成两套 runtime。
7. 第一阶段优先覆盖：
   - `video summary`
   - `video locate`
   - `video meta_state`
   - `series summary`
   - `series-concept-location`
   - `series-relationship`

## 不在本次范围内

- 前端 UI 改版
- 视频转写模型替换
- 导图/卡片生成工作流重写
- 一次性替换全量 API 路由
- 第一阶段迁移动作类工作流（如 `save_note`、`open_*`、`generate_*`）

## 现状模块重组

当前仓库按目录看很碎，但从职责上看，本质只有 5 个模块：

### 1. Application Shell

目录：

- `src/backend/api`
- `src/backend/app`
- `src/backend/presentation`
- `src/frontend`

职责：

- HTTP API
- 页面/UI
- 依赖装配

### 2. Content Asset Layer

目录：

- `src/backend/video_summary/domain`
- `src/backend/video_summary/library`
- `src/backend/video_summary/usecases`
- `src/backend/video_summary/infrastructure/filesystem_video_workspace.py`

职责：

- 视频、summary、transcript、notes、mindmap、knowledge cards 的读写
- workspace 目录结构

### 3. Offline Content Pipeline

目录：

- `src/backend/video_summary/generation`
- `src/backend/video_summary/infrastructure/*summarizer*`
- `src/backend/video_summary/infrastructure/*transcriber*`
- `src/backend/video_summary/infrastructure/mindmap_workflow.py`
- `src/backend/video_summary/infrastructure/rule_based_knowledge_card_generator.py`

职责：

- 转写
- 摘要
- 导图
- 卡片

### 4. Online Agent Platform

目录：

- `src/backend/agent/runtime`
- `src/backend/agent/tools`
- `src/backend/agent/validation`
- `src/backend/agent/session`
- `src/backend/agent/memory`
- `src/backend/agent/context`

职责：

- 编排
- tool loop
- planner
- validation
- session
- memory
- evidence routing

这是最需要重构的部分。

### 5. Shared Infrastructure

目录：

- `src/backend/shared`
- `src/backend/agent/infrastructure`

职责：

- LLM gateway
- settings
- provider adapter

## 重构后的目标架构

重构后只保留 4 个核心层：

### 1. API / UI

职责不变：

- 对外 HTTP 接口
- 前端页面

### 2. Content Pipeline

继续负责：

- transcript / summary / chapter / notes 等原始与派生产物

不负责：

- 在线问答时的检索编排

### 3. Retrieval Layer

新增独立层，职责是：

- 从 summary / chapter / transcript 构建 document
- 建索引
- 搜索
- 局部上下文扩写

推荐技术：

- `LlamaIndex` 负责 indexing / retrieval pipeline
- `LanceDB` 负责本地嵌入式存储

### 4. Agent Graph

这是新后端 agent 核心。

职责：

- query classification
- compare split
- retrieve evidence
- meta state read
- answer synthesis
- optional action dispatch

推荐技术：

- `LangGraph`
- `DSPy`

## 推荐开源库与职责映射

### LangGraph

用于替代：

- `assistant_runtime.py`
- `planner.py`
- `tool_loop.py`
- 大部分 `session/*`
- 大部分 `memory/*`

使用方式：

- 用 graph state 管理当前上下文
- 用 checkpoint/persistence 管理会话恢复
- 用 graph nodes 表达 query lifecycle

### DSPy

用于替代：

- `series_evidence_selector.py` 中的大段分类 prompt
- `series_locator.py` 中 compare splitter 的大段 prompt
- `routed_answerer.py` 中的自然语言回答合成 prompt
- 后续可扩展到 `note_drafter.py` 等“结构化输入 -> 结构化/自然输出”的节点

使用方式：

- 用 `Signature` 定义输入输出结构
- 用 `Predict` / `ChainOfThought` 替代手写 prompt 字符串
- 用 `Module` 组织多步推理逻辑，而不是把策略散落在 runtime 文件中

约束：

- `DSPy` 负责“节点内部的 LM 程序化”
- `LangGraph` 负责“节点之间的流程编排”
- 不允许用 `DSPy` 再包出第二套 runtime/orchestration

### LlamaIndex

用于替代：

- 自定义 evidence routing
- 自定义 chunking / document orchestration

使用方式：

- 建立统一 document schema
- summary/chapter/transcript 统一纳入 index pipeline
- graph 中只调用 retrieval service，不再自己拼 evidence 文档

### LanceDB

用于替代：

- 自定义轻量 evidence store

使用方式：

- 存 summary/chapter/transcript chunk documents
- 支持 hybrid / vector / full-text 检索演进

### Trustcall

用于替代：

- 一部分自定义 structured output repair
- 一部分 tool args repair / validation retry

使用方式：

- 对 classification
- compare split
- action parameter extraction

做结构化输出稳定化

### 暂不采用

- `Haystack`
  原因：与 `LlamaIndex` 职责重叠，第一阶段不应同时引入两个 retrieval 框架。

- `PydanticAI`
  原因：思路有价值，但如果已经引入 `LangGraph + DSPy + Trustcall`，第一阶段没有必要再叠第四套 agent 框架。

## 新的后端 agent 模块划分

建议在 `src/backend/agent` 下逐步收敛为：

- `graph/`
  - LangGraph graph 定义
  - state schema
  - node composition

- `nodes/`
  - classify query
  - compare split
  - retrieve evidence
  - read meta state
  - synthesize answer
  - action dispatch

- `programs/`
  - DSPy signatures
  - DSPy modules
  - classification program
  - compare split program
  - answer synthesis program

- `retrieval/`
  - document builder
  - index adapter
  - search service
  - context expansion

- `adapters/`
  - llm provider
  - trustcall adapter
  - workspace adapter

- `schemas/`
  - node input/output schema
  - retrieval document schema

其余旧目录逐步瘦身或废弃：

- `runtime/` -> 仅保留过渡兼容层，最终大部分删除
- `session/` -> 由 LangGraph persistence 替代
- `memory/` -> 由 LangGraph memory / store 替代
- `validation/` -> 仅保留业务级校验，不再承担 planner/tool loop 修复
- `context/` -> 收缩为 workspace 上下文装配，而不是平台层状态管理

## LangGraph 图设计

第一阶段 graph 覆盖统一的 `video + series` 问答主链路。

### Graph State

建议 state 包含：

- `session_id`
- `scope_type`
- `series_id`
- `video_id`
- `user_message`
- `query_plan`
- `retrieval_queries`
- `retrieval_results`
- `meta_state`
- `answer`
- `error`

### Nodes

#### 1. `load_context`

职责：

- 从 workspace 装载 base context
- 确认 series/video scope

#### 2. `classify_query`

职责：

- 结构化输出：
  - `goal = understand | locate | compare | meta_state`
  - `target_source = summary | transcript | all`
  - `context_need = chunk | continuous`

说明：

- 不允许本地关键词硬编码。
- 由 `DSPy Signature + Module` 完成。

#### 3. `split_compare`

职责：

- compare 才进入
- 输出 atomic concepts

说明：

- 不允许本地字面拆分逻辑。
- 由 `DSPy Signature + Module` 完成。

#### 4. `retrieve_evidence`

职责：

- 根据分类结果调用 retrieval service
- 支持：
  - video summary retrieval
  - video transcript retrieval
  - series summary/chapter retrieval
  - series transcript retrieval
  - all retrieval
  - local context expansion

#### 5. `read_meta_state`

职责：

- video scope 下读取工具状态
- series scope 下读取结构化系列状态（若有）
- 不走 transcript / RAG

#### 6. `synthesize_answer`

职责：

- 根据 evidence 组织最终自然语言回答

说明：

- 由 `DSPy Module` 生成最终答案，替代大段 answer prompt。

#### 7. `dispatch_action`

第二阶段引入。

职责：

- open_overview
- open_notes
- save_note
- video_seek

## 路由策略

第一阶段固定为：

- `video + understand -> retrieve(video summary) -> synthesize`
- `video + locate -> retrieve(video transcript) -> synthesize`
- `video + meta_state -> read_meta_state -> synthesize`
- `series + understand -> retrieve(series summary/chapter) -> synthesize`
- `series + locate -> retrieve(series transcript or all) -> synthesize`
- `series + compare -> split_compare -> retrieve(series all, multi-query) -> synthesize`
- `series + meta_state -> read_meta_state`

这里最重要的原则：

- **graph 负责编排**
- **retrieval service 负责检索**
- **DSPy program 负责分类 / 拆分 / 回答**

不要再把这些职责揉回单文件 runtime。

## 第一阶段迁移范围

只迁移：

- video + series 问答主链路

覆盖用例：

- `video summary`
- `video locate`
- `video tool status`
- `series summary`
- `series-concept-location`
- `series-relationship`

保留旧链路：

- open / generate / save_note 动作
- 导图/卡片/笔记侧逻辑

## 第一阶段交付物

### 交付物 1：Graph Skeleton

- LangGraph graph 初始化
- state schema
- 5 个最小节点：
  - load_context
  - classify
  - split_compare
  - retrieve
  - read_meta_state
  - answer

### 交付物 1.5：DSPy Programs

- `classify_query` 的 `Signature + Module`
- `split_compare` 的 `Signature + Module`
- `synthesize_answer` 的 `Signature + Module`
- 替换对应旧 prompt 常量

### 交付物 2：Retrieval Service

- 基于 workspace 构建 document schema
- summary/chapter/transcript chunk ingest
- LanceDB index
- LlamaIndex retrieval adapter

### 交付物 3：Compatibility API

- 保持现有 API 层入口不变
- `AgentService` 先做适配壳
- 旧前端/脚本可继续调用

## 迁移策略

### Step 1

保留旧系统，旁路接入新 graph：

- 新 graph 不替换旧 runtime
- 仅在单独 feature flag 或独立 service 下运行

### Step 2

用主观 case 验证新 graph：

- `video quote / locate`
- `video tool status`
- `series-concept-location`
- `series-relationship`

### Step 3

在 API 层把 video + series 问答切到新 graph

### Step 4

移除旧的问答 runtime：

- `video_query_policy.py`
- `video_evidence_selector.py`
- `video_seek_locator.py`
- `series_query_policy.py`
- `series_evidence_selector.py`
- `series_locator.py`
- `assistant_runtime.py` 中对应问答编排逻辑
- 与之绑定的旧 runtime glue

## 要避免的错误

1. 不要把 LangGraph 引入后，又在 graph 外面再包一层自定义 runtime。
2. 不要同时引入两套 retrieval 框架。
3. 不要第一阶段就迁 action / note / generate 全部链路。
4. 不要再写本地文字硬编码分类器。
5. 不要把 retrieval 细节塞回 graph 节点里。

## 推荐依赖

第一阶段建议新增：

- `langgraph`
- `langchain-core`
- `dspy`
- `llama-index`
- `lancedb`
- `trustcall`

是否需要 `langchain-openai` 视 provider adapter 方案决定。

## 成功标准

满足以下条件才算第一阶段成功：

1. `video` 与 `series` 的核心问答场景都可在新 graph 路径跑通。
2. 不再依赖本地问句文字硬编码。
3. 分类 / compare 拆分 / 回答合成不再依赖大段手写 prompt。
4. 新的问答逻辑不再继续堆到 `agent/runtime`。
5. session / memory / orchestration 明显简化。
6. 新链路的代码量和抽象层数少于旧实现。

## 参考资料

- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph memory: https://docs.langchain.com/oss/python/langgraph/memory
- LangGraph supervisor: https://github.com/langchain-ai/langgraph-supervisor-py
- Trustcall: https://github.com/hinthornw/trustcall
- PydanticAI: https://ai.pydantic.dev/
- LlamaIndex: https://developers.llamaindex.ai/python/framework/
- Haystack: https://docs.haystack.deepset.ai/docs/intro
- LanceDB: https://docs.lancedb.com/
- DSPy: https://dspy.ai/
