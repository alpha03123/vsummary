# Legacy Main And Worktree Code Reading

## 目的

本文不是设计稿复述，而是基于当前仓库真实代码、脚本、测试入口做的一次阅读结论。

目标只有两个：

1. 在开始迁移实现前，先确认 `legacy main` 现在到底是怎么跑的
2. 确认 `codex/langgraph-refactor` worktree 当前实际落地到什么程度，哪些地方已经实现，哪些仍停留在半成品

后续所有 cutover / 去冗余 / 技术栈替代，都应以本文描述的真实现状为准，而不是以理想化想象为准。

## 一、legacy main 的真实主链

### 1. 默认问答入口

当前 `main` 默认 `/api/agent/chat` 与 `/api/agent/chat/stream` 接的是 `StudioAssistantService`，不是旧 graph 主链。

真实入口链路：

- `src/backend/api/bootstrap.py`
- `src/backend/studio_assistant/factory.py`
- `src/backend/studio_assistant/service.py`

### 2. 实际执行流程

`StudioAssistantService.run_with_context(...)` 的流程非常固定：

1. 读取 `AgentContext`
2. 从 `session_store` 读取快照
3. `scope_router.build_plan(...)`
4. `scope_router.execute(...)`
5. `aggregator.answer(...)`
6. 组装 `citations`
7. 持久化会话

也就是说，`legacy main` 当前本质是：

`context -> planner -> executor -> aggregator -> citations -> persist`

### 3. `series` 与 `video` 的边界

`scope_router` 不是意图分类器，而是 scope 分发器：

- `series` -> `StructuredSeriesPlanner` + `SeriesExecutor`
- `video` -> `VideoScopePlanner` + `VideoExecutor`

这里最关键的现实结论是：

- 当前 `main` 已经不再依赖旧 `understand / locate / action / meta_state` 这套主决策 taxonomy
- 当前业务核心是 `SeriesExecutionPlan` 里的：
  - `selected_videos`
  - `selection_mode`
  - `subplans`
  - `depth`

### 4. `depth` 才是当前主链真正的执行语义

`legacy main` 当前的主执行深度是：

- `series_meta`
- `summary`
- `video_graph`

其中：

- `series_meta`：只读系列元信息
- `summary`：跨视频浅层聚合
- `video_graph`：单视频内部细粒度定位和解释

这意味着：

当前主链最值得保留的不是“分类标签”，而是“按证据深度规划”的做法。

### 5. `video_graph` 是当前 main 最有价值的业务能力之一

`video_graph.py` 不是 graph 框架，而是单视频细粒度证据定位器。

它实际做了：

1. transcript 读取
2. query 拆 slot
3. lexical term 匹配
4. reranker semantic score
5. 融合排序
6. 输出：
   - `best_match`
   - `slots`
   - `video_seek`
   - transcript citation 所需片段

这个能力不是重复轮子，属于必须迁移的业务资产。

## 二、legacy main 里的 debug / trace / profile / long-case 到底是什么

### 1. `debug_trace` 不是全局调试模式，而是问答链的中间态采样

`StudioAssistantService.run_with_context(..., debug_trace=...)` 会把中间态塞进外部 dict：

- `planner`
- `video_planner`
- `video_graph`
- `execution_results`
- `tool_results`
- `aggregator`
- `assistant_message`
- `citations`

这说明：

- `debug_trace` 是问答链级别的结构化调试输出
- 它不是配置文件里 `[debug].mode` 的同义词

### 2. 配置里的 `[debug].mode` 目前主要服务离线生成流程

`config/settings.toml` 里的：

```toml
[debug]
mode = true
```

在当前主线里，明确用到它的地方主要是 `video_summary_workflow.py`。

当生成 summary 时，如果 debug mode 开启，会用 `DebugFileProgressReporter` 把阶段事件写入 `debug.log`。

也就是说：

- `debug.mode` 当前主要是**离线内容生成调试开关**
- 不是在线问答链的统一调试总开关

### 3. `run_runtime_trace.py` 是在线问答事件流时序追踪脚本

它实际做的是：

- 调 `service.stream_with_context(...)`
- 记录事件顺序和相对时间
- 输出：
  - `thinking_*`
  - `tool_*`
  - `answer_*`
  - 首个工具开始时间
  - 总耗时

所以它回答的问题是：

**“一轮请求在运行时层面实际发生了什么顺序和时序？”**

### 4. `run_provider_trace.py` 是模型调用分布脚本

它通过 tracing gateway 记录 provider 调用，输出：

- 总模型调用次数
- 每类调用数量
- 每次调用的 kind / mode / duration

所以它回答的问题是：

**“一轮请求到底打了几次模型、各是什么类型？”**

### 5. `run_speed_profile.py` 是细粒度性能剖析脚本

它不是简单计总时长，而是 monkey patch service 内部关键方法，采 span：

- `planner.create_plan`
- `aggregator.answer`
- `series_executor.execute`
- `video_graph.execute`
- `session_store.*`
- LLM API 调用

所以它回答的问题是：

**“一轮请求慢在哪里，planner 慢还是 retrieval 慢还是 LLM 慢？”**

这套脚本非常重要，因为它提供了未来 cutover 的 perf 护栏。

### 6. `run_new_arch_long_tests.py` 是真实样本长测回归脚本

它定义了 6 条高价值真实长测试：

- 系列筛选
- 单视频深定位
- 跨轮继承
- 单视频深理解
- 混合深度
- 跨 series 聚合

它不是单测，而是：

- 真模型
- 真 workspace
- 真 transcript / summary
- 真会话

所以它回答的问题是：

**“新实现有没有保住核心业务能力，而不是只保住 API 形式？”**

## 三、legacy main 的测试资产是什么形状

### 1. 核心后端单测围绕 `studio_assistant`

当前主线最关键的一批后端单测是：

- `tests/test_studio_assistant_planner.py`
- `tests/test_studio_assistant_video_planner.py`
- `tests/test_studio_assistant_video_graph.py`
- `tests/test_studio_assistant_aggregator.py`
- `tests/test_studio_assistant_series_service.py`
- `tests/test_api_studio_assistant.py`

这说明现在真正的业务核心已经收敛到 `studio_assistant`，而不是旧 runtime。

### 2. API 测试验证的是对外契约

`test_api_studio_assistant.py` 验证的重点是：

- `/api/agent/chat`
- `/api/agent/chat/stream`
- context override 是否正确接入
- SSE 事件形状

它并不关心内部用什么框架，而关心：

- 返回是否合理
- scope 是否正确
- tool_results / citations 是否存在

## 四、worktree 当前真实落地到了什么程度

### 1. worktree 已经有真实 `agent_graph` 代码，不只是文档

当前 `codex/langgraph-refactor` 并不只是想法，已经落了：

- `src/backend/agent_graph/state.py`
- `src/backend/agent_graph/models.py`
- `src/backend/agent_graph/programs.py`
- `src/backend/agent_graph/retrieval.py`
- `src/backend/agent_graph/nodes.py`
- `src/backend/agent_graph/graph.py`
- `src/backend/agent_graph/service.py`

### 2. worktree 的编排已经由 LangGraph 接管

`graph.py` 里已经用 `StateGraph` 组了真实节点图：

- `decompose`
- `advance_task`
- `classify`
- `split_compare`
- `retrieve`
- `read_meta_state`
- `dispatch_action`
- `answer`
- `finalize`
- `update_memory`

这不是概念图，而是已经 compile 的 graph。

### 3. worktree 当前仍然保留旧 taxonomy

虽然 `main` 已经偏向 `selected_videos / subplans / depth`，
但 worktree 现在的 `SeriesQueryDecision` 仍然是：

- `goal`
- `target_source`
- `context_need`
- `action_name`

而 `goal` 仍包含：

- `understand`
- `locate`
- `compare`
- `meta_state`
- `action`

这说明：

- worktree 的图框架已经在
- 但业务规划语义还停留在旧分类器思路

这是后续必须修正的地方。

### 4. worktree 的 retrieval 已经真实接入 `LlamaIndex + LanceDB`

`retrieval.py` 当前已经不是 placeholder，而是：

- 用 `Document`
- 用 `VectorStoreIndex`
- 用 `LanceDBVectorStore`
- 从 summary/chapter/transcript 构建 documents
- 按 metadata filters 检索

这意味着：

- retrieval 底座已经开始替代自定义 evidence orchestration
- 但它当前更偏“统一召回层”，还没有完全吸收 `video_graph` 的最后一跳业务语义

### 5. worktree 的 graph service 已经接到 API bootstrap

`worktree` 的 `api/bootstrap.py` 已经把默认 `get_agent_service()` 指向 `AgentGraphService`。

也就是说在 worktree 世界里：

- 默认主链已经是 graph
- `DSPy program + LlamaIndex retrieval + LangGraph service` 已经串起来

### 6. worktree 当前 stream/debug 还比较薄

`AgentGraphService.stream_with_context(...)` 当前只发非常薄的一组事件：

- `thinking_started`
- `thinking_completed`
- `tool_completed`
- `answer_started`
- `answer_completed`

而且 `thinking_completed` 还是固定文案：

- `graph 已生成结构化决策`

这说明当前 worktree 在可观测性上明显弱于 legacy main：

- 没有等价的 `debug_trace`
- 没有等价的 profile span 采样
- 还没有完整保留旧系统可解释性

## 五、worktree 的测试资产是什么形状

### 1. graph 级单测已经很多

worktree 的测试重心是：

- `test_agent_graph_scaffold.py`
- `test_agent_graph_programs.py`
- `test_agent_graph_retrieval.py`
- `test_agent_graph_series_flow.py`
- `test_agent_graph_video_flow.py`
- `test_agent_graph_actions.py`
- `test_agent_graph_memory.py`
- `test_agent_graph_memory_flow.py`
- `test_agent_graph_service.py`

这说明 worktree 的优势是：

- graph 骨架
- 程序化节点
- retrieval 接口
- memory flow

都已经有测试护栏。

### 2. 但它的长测/性能护栏还没和新 graph 完全对齐

worktree 仍保留：

- `run_runtime_trace.py`
- `run_provider_trace.py`
- `run_agent_manual_cases.py`

但没有等价的：

- `run_speed_profile.py`
- `run_new_arch_long_tests.py`

至少当前 worktree 脚本集里没有与 legacy main 对等的性能与长测闭环。

这是非常关键的 gap。

## 六、两边对比后的结论

### 1. `legacy main` 的强项

- 真实业务语义更成熟
- `series/video` 主链更贴近当前产品实际
- `video_graph` 细定位能力已经可用
- citation / seek / debug_trace 更完整
- long tests / runtime trace / provider trace / speed profile 护栏较全

### 2. `legacy main` 的弱项

- 平台层与业务层边界不够清爽
- 自定义编排 / 调试 / 会话 glue 偏多
- 很多能力是“能跑”，但形状不够收敛
- 随着继续加功能，复杂度会继续长

### 3. `worktree` 的强项

- graph 编排已经显式化
- `DSPy` 程序层已经真实落地
- `LlamaIndex + LanceDB` retrieval 已有实现
- graph 相关单测较完整
- API composition root 已经开始朝新栈迁移

### 4. `worktree` 的弱项

- 业务语义仍被旧 `understand/locate/...` taxonomy 绑住
- 没有完整吸收 `legacy main` 的 `video_graph` 业务精髓
- graph service 的可观测性仍然偏薄
- 缺失和 legacy main 对等的：
  - speed profile
  - long-case regression
  - 更细的 debug trace

## 七、对后续迁移的直接指导

### 1. 不应该把 `legacy main` 反向重构成 worktree

性价比低。

因为 worktree 已经有：

- graph
- DSPy
- retrieval
- graph service

再回头在 main 上重做一遍，只会继续把旧平台包袱裹进来。

### 2. 也不能让 worktree 直接粗暴接管

因为它现在还缺：

- 长测护栏
- 性能护栏
- 更强的 debug / trace
- `video_graph` 级业务细定位能力的保真迁移

### 3. 正确迁法

应按这个顺序：

1. 保留 `legacy main` 作为只读业务对照组
2. 先把 legacy 的验证资产迁到 worktree：
   - long tests
   - provider trace
   - runtime trace
   - speed profile
3. 再把 legacy 的业务精髓迁到 worktree：
   - `video_graph`
   - citation schema
   - `selected_videos / subplans / depth`
4. 最后删除重复轮子

### 4. 一个重要判断

worktree 现在最需要的不是继续增加 graph 节点，而是：

- 用更贴近业务的 planning object 取代旧 `understand/locate` taxonomy
- 用 legacy 的真实长测和 profile 脚本把新链路钉住
- 在 graph service 层补足 debug / trace / perf 可观测性

## 八、当前建议

在开始实现迁移前，下一份文档应该进一步细化为：

1. legacy main 的文件级能力清单
2. worktree 的文件级替代清单
3. 哪些直接删
4. 哪些必须迁
5. 哪些测试脚本必须先补齐

只有完成这一步，后续“用成熟技术替轮子”才不会变成再次造轮子。
