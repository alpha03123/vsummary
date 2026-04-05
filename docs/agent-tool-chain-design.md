# Agent 多步 Tool Chain 设计

本文设计一套适用于当前 Studio 的 Agent 多步工具链方案。

设计目标不是做通用自治 Agent，而是：

- 继续保持 thin tool
- 支持少量高价值多步链路
- 让前端 React 明确承接 UI 状态变化
- 不破坏现有 `video_summary` / `agent` / `api` 的边界

## 1. 设计结论

当前项目不优先引入 fat tool。

优先方案是：

> thin tool + 受控的多步 tool chain + React 承接界面状态变化

这意味着：

- 工具继续保持单一职责
- Planner 可以规划多个步骤
- Executor 受控执行这些步骤
- 前端消费步骤结果并推进 UI
- 不做无限循环式自治 Agent

## 2. 为什么不先做 fat tool

fat tool 在当前项目里有几个明显问题：

1. 容易把业务查询、生成动作、UI 跳转、状态切换混成一个黑盒
2. 不利于测试，很难定位失败到底发生在哪一步
3. 会让 `agent` 直接承担过多工作流细节，污染当前边界
4. 与 Studio 现有“工具页 + 状态切换 + 前端承接动作”的产品结构不匹配

例如一个 fat tool：

- `summarize_current_series_and_open_best_video_and_seek`

它会同时掺杂：

- 系列聚合
- 视频选择
- 片段定位
- 页面切换
- 视频跳转

这是一个典型不适合当前架构的工具。

## 3. 为什么 thin tool + tool chain 更适合

当前系统已经具备几个天然前提：

1. Agent 已经能返回多个 `tool_results`
2. 前端已经按顺序遍历 `tool_results` 并执行动作
3. 工具大多是清晰的小动作
4. Studio 本身就是明显的状态驱动界面

所以现在最自然的演进不是“做更胖的工具”，而是“让 Planner 输出受控的步骤序列”。

## 4. 设计原则

### 4.1 工具保持 thin

每个工具只做一件事，例如：

- 列视频
- 读 summary
- 检索 transcript
- 打开某个工具页
- 生成导图
- 保存笔记

工具不负责封装整条工作流。

### 4.2 工具链保持有限步

不要允许无限规划和无限执行。

建议约束：

- 默认最多 3 步
- 上限最多 5 步
- 任何一步失败后停止链路
- 不允许 Planner 在同一轮内递归追加新计划

### 4.3 UI 状态变化由前端承接

以下行为优先由 React 承接：

- `selected_tool` 切换
- 视频 `seek_seconds`
- 触发 summary / mindmap 生成
- 保存笔记
- 展示 loading / progress / error

Agent 后端只返回结构化动作，不直接承担整条 UI 工作流。

### 4.4 工具链适合信息聚合，不适合长时自治

适合自动串行执行的场景：

- 查询 series 下视频
- 读取若干视频 summary
- transcript lookup
- 结果聚合回答

不适合自动无限推进的场景：

- 大量跨视频生成
- 多轮失败重试
- 复杂长任务编排
- 依赖用户确认的分支决策

## 5. 工具分层建议

## 5.1 第一层：UI 原子工具

这些工具主要负责 Studio 状态变化：

- `open_series_home`
- `open_overview`
- `open_mindmap`
- `open_knowledge_cards`
- `open_notes`
- `open_video`
- `video_seek`
- `save_note`
- `generate_overview`
- `generate_mindmap`

特点：

- 单一职责
- 返回 payload
- 由前端解释并执行

## 5.2 第二层：信息型业务工具

这些工具用于支持复杂问答和多步聚合：

- `transcript_lookup`
- `list_series_videos`
- `get_video_summary`
- `get_video_tools`
- `get_video_notes`
- `get_video_knowledge_cards`

注意：

- 这些工具目前并未全部实现
- 这是下一阶段最值得补的一层

这层工具不负责跳页面，只负责返回结构化信息。

## 5.3 暂不引入第三层：超 fat workflow tool

暂不推荐引入类似下面这种工具：

- `summarize_series`
- `locate_topic_and_open_best_video`
- `review_series_and_save_notes`

不是说这些能力永远不做，而是先用 tool chain 表达它们，等需求稳定后再判断是否值得沉淀为聚合工具。

## 6. 协议演进方案

当前的 `AgentActionPlan` 是单个意图 + 多个 `tool_calls`：

- `intent_type`
- `scope_type`
- `tool_calls`

这已经能承载“多步调用”的雏形，但表达力还不够明确。

建议演进为“步骤化计划”。

### 6.1 目标结构

建议新增一层 step，而不是继续把所有动作平铺在 `tool_calls` 中。

示意：

```python
class AgentPlanStep(BaseModel):
    id: str
    kind: Literal["tool_call", "respond"]
    tool_call: ToolCall | None = None
    depends_on: list[str] = Field(default_factory=list)
    continue_on_error: bool = False


class AgentActionPlan(BaseModel):
    intent_type: IntentType
    scope_type: ScopeType
    assistant_message: str = ""
    steps: list[AgentPlanStep] = Field(default_factory=list)
    reason: str = ""
    out_of_scope_reason: str = ""
```

第一阶段可以更保守一些，不必立刻引入 DAG，只做顺序 steps：

```python
class AgentPlanStep(BaseModel):
    id: str
    tool_call: ToolCall
```

然后约定：

- steps 按顺序执行
- 不做并行
- 不做动态增量计划

### 6.2 为什么不用继续平铺 `tool_calls`

继续平铺也能用，但会有几个问题：

- 无法表达哪一步是为了哪一步服务
- 不方便加入执行元数据
- 后续难以控制失败策略
- 不方便前端展示链路过程

step 模型会更稳。

## 7. 执行模型

建议执行模型非常克制：

1. Planner 输出顺序 steps
2. Executor 逐步执行
3. 每步生成 `step_result`
4. 所有结果汇总给 responder
5. 前端只消费最终 `tool_results` 或 `step_results`

### 7.1 不做的事

当前阶段明确不做：

- 执行到一半重新调用 Planner
- 工具结果反哺后继续自动规划新步骤
- while-loop 自治执行
- 任意步数链路

### 7.2 失败策略

当前建议：

- 任一步失败则停止
- 将失败写入响应
- 由 responder 告知用户哪一步失败
- 需要时由用户发起下一轮

这比自动恢复更符合当前 Studio 的可控性。

## 8. 响应模型建议

当前 `AgentChatResponse` 只有：

- `assistant_message`
- `intent_type`
- `scope_type`
- `reason`
- `tool_results`

建议后续扩展为：

```python
class ToolStepResultResponse(BaseModel):
    step_id: str
    tool_name: str
    status: str
    payload: dict[str, object]


class AgentChatResponse(BaseModel):
    assistant_message: str
    intent_type: str
    scope_type: str
    reason: str
    out_of_scope_reason: str
    tool_results: list[ToolExecutionResultResponse]
    step_results: list[ToolStepResultResponse] = []
```

这样前端可以：

- 保持兼容旧 `tool_results`
- 新页面中展示“本轮 Agent 做了哪些步骤”

## 9. 前后端职责划分

### 9.1 后端 Agent 负责

- 解析用户意图
- 规划步骤
- 执行信息型工具
- 输出 UI 动作 payload
- 组织最终回答

### 9.2 前端 React 负责

- 切换工具页
- 触发生成接口
- 拉取进度
- 保存笔记
- 播放器跳转
- 呈现链路状态和错误

一句话说：

> 后端负责“决定做什么”，前端负责“把动作落到界面上”。

## 10. 高价值链路

以下链路最适合优先支持。

### 10.1 总结当前系列

目标：

- 聚合当前 series 下多个视频的 summary，生成系列级回答

链路：

1. `list_series_videos`
2. 对每个视频调用 `get_video_summary`
3. responder 聚合输出

注意：

- 如果某些视频没有 summary，可在回答里显式说明
- 不必自动触发所有缺失视频的生成

### 10.2 找当前系列里哪里讲过某个概念

链路：

1. `list_series_videos`
2. 遍历已有 summary 或 transcript 索引
3. 返回候选视频和时间点
4. 如用户明确要求，再下一轮执行 `open_video` / `video_seek`

### 10.3 帮我找到当前视频某个片段并跳过去

链路：

1. `transcript_lookup`
2. `video_seek`

这是最典型、最值钱的两步链。

### 10.4 帮我把这段内容记成笔记

链路：

1. 必要时先 `transcript_lookup`
2. `save_note`
3. `open_notes`

### 10.5 如果没有导图就生成并打开

链路：

1. 检查当前上下文 `mindmap.generated`
2. 如未生成，执行 `generate_mindmap`
3. 执行 `open_mindmap`

## 11. 第一阶段落地建议

第一阶段不要一次做太大，只做最小可用升级。

建议顺序：

1. 保持现有 tool schema 不变
2. 允许 Planner 在同一轮返回多个 `tool_calls`
3. 明确约束执行顺序为串行
4. 限制单轮最多 3 步
5. 先补 2 到 3 个信息型工具

最先补的工具建议：

1. `list_series_videos`
2. `get_video_summary`
3. `get_video_tools`

这样立刻就能支撑：

- 系列级总结
- 系列级定位
- 生成前状态判断

## 12. 第二阶段落地建议

当第一阶段稳定后，再做：

1. `step_results`
2. 前端链路可视化
3. 更细的失败状态
4. 少量 step 级元数据

此时再判断是否要从 `tool_calls` 演进到 `steps`。

## 13. 明确不做的事情

为了保持架构洁净，当前阶段不做：

- 通用无限步 Agent loop
- 自动 retry orchestration
- 黑盒 fat tool
- 后端直接接管前端 UI 生命周期
- Planner 执行到一半再次重规划

## 14. 一句话总结

当前项目最适合的 Agent 演进路线是：

> 保持 thin tool，不做 fat tool；通过有限步 tool chain 组合出复杂能力，并让 React 明确承接 UI 状态变化。

这样既能支持“总结当前系列”这类复杂需求，又不会把 `agent` 变成失控的自治黑盒。
