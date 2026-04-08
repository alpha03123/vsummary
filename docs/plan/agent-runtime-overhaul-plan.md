# Agent Runtime 大换血计划

## 1. 文档目的

本文不是问题清单复述，而是下一阶段后端重构的执行蓝图。

目标有三件事：

1. 把系统从 `planner-first` 的弱自治 Agent 拉回到“视频知识工作台”主业务。
2. 在不砍产品能力的前提下，去掉过度智能化、过度协议化、过度循环化的复杂度。
3. 建立“每做完一项功能就脚本化回归”的工作流，尽量不再依赖手动打开网页验证。

本文覆盖以下范围：

- `video_summary` / `agent` / `api` 三个子系统的重新分工
- LLM provider 层重构，允许引入 `LiteLLM`
- Agent 主循环重构
- 工具分层与 runtime state 下沉
- 自动化验证与真实模型回归脚本体系

当前执行进度单独记录在 [agent-runtime-progress.md](/E:/gittools/self/video_include/docs/plan/agent-runtime-progress.md)。

## 2. 重构总原则

### 2.1 产品优先于框架

项目本质是：

- 本地优先
- BYOK
- 交互式视频学习与总结工具

不是：

- 通用自治 Agent 框架
- 通用多工具工作流引擎
- 为了“显得智能”而构建的 planner 系统

### 2.2 保留能力，砍掉错误复杂度

本次重构不砍这些能力：

- 总结 `series`
- 总结 `video`
- 打开概况 / 导图 / 知识卡片 / 笔记
- 视频定位与时间跳转
- 基于 transcript / summary 的问答
- 保存学习笔记

本次重构重点砍这些复杂度：

- 强制 `<<PLAN>>` 文本规划协议
- Planner / Responder 两次模型调用
- 多轮 planner-first 主循环
- 内部状态工具化
- prompt 层补 runtime 洞
- 把简单命令强行包装成 Agent tool chain

### 2.3 代码决定流程，模型负责理解与表达

后续系统必须遵守的边界：

- 代码负责：
  - 路由用户请求类型
  - 决定证据读取路径
  - 维护会话与运行时状态
  - 控制并发、批量、失败策略
- 模型负责：
  - 理解用户意图
  - 从证据中归纳、比较、解释
  - 输出自然语言回答

### 2.4 兼容性与先进能力同时保留

不能只押注一个 provider 协议。

目标支持三类后端：

1. `OpenAI-compatible chat completions`
2. `OpenAI Responses API`
3. `Anthropic Messages / native tool use`

因此：

- `LiteLLM` 只作为 provider 兼容层
- runtime 不绑定单一厂商协议
- 原生 tool calling 是先进路径
- 文本 fallback 是兼容路径，不再作为核心主干

## 3. 目标架构

## 3.1 子系统重分工

### `video_summary`

继续作为内容主域，负责：

- 视频转写
- 结构化 summary
- mindmap / cards / notes 等工作区产物
- workspace 查询能力

### `studio_assistant`

替代现在过度膨胀的 `agent` 主循环，负责：

- 请求分类
- 证据读取编排
- UI 动作编排
- LLM 调用与 provider 适配
- 会话状态
- 流式事件输出

### `api`

保持 composition root，不承载业务判断。

## 3.2 新的请求通道

后续所有交互统一落入三条通道之一：

### Command Lane

处理这类请求：

- 打开知识卡片
- 打开概况
- 打开导图
- 打开笔记
- 跳转视频时间
- 保存笔记

特点：

- 代码优先路由
- 不经过 planner
- 如需模型，只做轻量意图归一化

### Evidence QA Lane

处理这类请求：

- 这个系列讲了哪些主题
- 这个视频主要讲了什么
- 视频原话里怎么说的
- 某概念在哪个视频、哪个时间点提到

特点：

- 代码先决定读 summary 还是 transcript
- 模型只在证据收集后做聚合回答

### Generation Lane

处理这类请求：

- 生成 summary
- 生成 mindmap
- 生成 cards

特点：

- 走确定性生成流程
- 不走 planner-first 对话链路

## 3.3 Runtime 分层目标

建议目录方向：

```text
src/backend/studio_assistant/
├─ application/
│  ├─ lanes/
│  │  ├─ command_lane.py
│  │  ├─ evidence_qa_lane.py
│  │  └─ generation_lane.py
│  ├─ runtime/
│  │  ├─ assistant_runtime.py
│  │  ├─ tool_loop.py
│  │  └─ stream_events.py
│  ├─ usecases/
│  │  ├─ route_user_request.py
│  │  ├─ answer_series_question.py
│  │  ├─ answer_video_question.py
│  │  └─ execute_ui_command.py
│  └─ ports/
│     ├─ llm_driver.py
│     ├─ evidence_reader.py
│     └─ session_store.py
├─ domain/
│  ├─ request_kind.py
│  ├─ evidence_policy.py
│  ├─ session_state.py
│  └─ command_models.py
├─ infrastructure/
│  ├─ llm/
│  │  ├─ litellm_chat_driver.py
│  │  ├─ openai_responses_driver.py
│  │  └─ anthropic_messages_driver.py
│  ├─ readers/
│  └─ sessions/
└─ testing/
   ├─ fakes/
   └─ scripts/
```

说明：

- 不必一次迁完目录，但迁移方向必须朝这个形状收敛
- `agent` 可先保留兼容壳，内部逐步迁到 `studio_assistant`

## 4. 14 条问题对应的改造计划

下面按问题编号给出：

- 问题
- 改造目标
- 主要动作
- 预期收益
- 验证方式

### 1. `P0` 产品重心偏向通用 Agent 编排器

#### 改造目标

把复杂度中心从 `agent` 拉回 `video_summary + studio_assistant` 的业务协作。

#### 主要动作

- 重写架构文档，明确 `studio_assistant` 只是交互编排层
- 后续所有新功能先判断属于哪条业务通道，再决定是否需要模型
- 禁止再用“为了让 planner 学会”作为新增复杂度理由

#### 预期收益

- 降低架构扩张方向错误
- 新增功能更容易落到业务层
- 降低“框架化自我膨胀”

#### 验证方式

- 新增文档审查清单
- 每个新功能 PR 必须标注所属 lane
- 代码目录中不再继续扩充 planner/validation/protocol 型模块

### 2. `P0` 强制 `<<PLAN>>` 文本规划协议

#### 改造目标

移除 `<<PLAN>>` 作为主路径协议，只保留为临时兼容 fallback。

#### 主要动作

- 新增 `AssistantRuntime` 主入口
- 新路径不再依赖 `prompt.py` 中的 `PLANNER_SENTINEL`
- 旧 planner 路径迁移到 `legacy/` 或 `fallback/`

#### 预期收益

- 减少格式错误带来的失败
- 提前触发工具执行
- 缩短首工具启动时间

#### 验证方式

- 新增脚本 `scripts/run_runtime_trace.py`
- 输出：首个工具开始时间、工具链总耗时、是否出现 `<<PLAN>>`
- 目标：新链路中不再出现 `<<PLAN>>`

### 3. `P0` Planner / Responder 两次模型调用

#### 改造目标

把主链路改成单一 assistant/tool continuation，而不是先 planner 再 responder。

#### 主要动作

- 新 runtime 中将“工具调用”和“最终回答”统一到同一个 conversation loop
- 删除“执行完工具后再专门 responder 一次”的主路径

#### 预期收益

- 降低延迟
- 降低 token 成本
- 降低事实重表述损耗

#### 验证方式

- 新增脚本 `scripts/run_provider_trace.py`
- 记录一轮用户请求到底触发了几次模型调用
- 目标：简单命令型请求只允许 0 到 1 次；常规问答链路显著少于旧实现

### 4. `P0` 主循环按轮规划，而不是按工具事件推进

#### 改造目标

改成 event-driven runtime loop。

#### 主要动作

- 用 `while conversation_not_finished` 替代 `for _round in range(MAX_PLANNING_ROUNDS)`
- 基于事件推进：
  - assistant text
  - tool calls
  - tool results
  - final answer

#### 预期收益

- 避免“一个工具，一次思考”的体感
- 去掉大量人造最大轮数失败

#### 验证方式

- 新增脚本 `scripts/run_stream_timeline.py`
- 输出事件时间线：
  - 用户提问
  - 首 token
  - 首 tool_started
  - tool_completed
  - answer_completed
- 比较旧链路与新链路时间线

### 5. `P0` 批量能力做在 prompt / 校验层，不在 runtime 层

#### 改造目标

把“批量”改成 runtime policy，把“并发”改成 executor 能力。

#### 主要动作

- 定义工具元信息：
  - `read_only`
  - `concurrency_safe`
  - `interactive_side_effect`
- executor 按元信息决定：
  - 并发
  - 串行
  - 是否允许合并同轮执行

#### 预期收益

- 系列类问题明显加速
- 减少提示词里“鼓励批量”这种低效修修补补

#### 验证方式

- 新增脚本 `scripts/run_series_batch_probe.py`
- 对比：
  - 串行读取 6 个 summary 的总耗时
  - 并发读取 6 个 summary 的总耗时

### 6. `P0` 内部运行态暴露成模型工具

#### 改造目标

把 `candidate_buffer`、`inspection_stage`、`inspected_video_ids` 收回 runtime/session state。

#### 主要动作

- 删除模型可见的：
  - `view_series_candidates`
  - `add_series_candidates`
  - `replace_series_candidates`
  - `remove_series_candidates`
  - `clear_series_candidates`
- 由 runtime 内部维护候选集
- 系列级证据选择由代码完成

#### 预期收益

- 模型工具面缩小
- token 浪费减少
- 准确度与可维护性提升

#### 验证方式

- 单测验证 runtime state 演进
- 真实模型脚本中不再出现上述工具名
- 新增脚本 `scripts/run_tool_surface_audit.py`

### 7. `P1` 证据获取路径过度交给模型决定

#### 改造目标

建立确定性的 evidence policy。

#### 主要动作

- 定义请求分类：
  - 主题/概括类 -> 优先 summary
  - 原话/逐字/时间点类 -> transcript
  - 页面打开类 -> command
- series 问题默认代码流：
  - list videos
  - collect summaries
  - aggregate
- video 原话问题默认代码流：
  - read transcript
  - locate relevant segments
  - answer

#### 预期收益

- 降低随机性
- 降低重复查与误查
- 高频问题结果更稳定

#### 验证方式

- 新增脚本 `scripts/run_evidence_policy_cases.py`
- 用固定 case 打印：
  - chosen lane
  - chosen evidence source
  - tool trace
  - final answer

### 8. `P1` Provider 抽象停在最低公约数

#### 改造目标

引入 `LiteLLM`，但只放在 provider adapter 层，不让它接管业务 runtime。

#### 主要动作

- 新增 LLM port：
  - `ConversationDriver`
  - `NativeToolCallingDriver`
  - `TextCompletionFallbackDriver`
- 用 `LiteLLM` 实现 OpenAI-compatible chat 驱动
- 为原生协议预留独立 driver：
  - OpenAI Responses
  - Anthropic Messages

#### 预期收益

- 保持国产模型兼容
- 不锁死在 `openai` SDK 和 `chat.completions`
- 先进路径与兼容路径并存

#### 验证方式

- 新增脚本 `scripts/run_provider_matrix.py`
- 按 provider 维度输出：
  - text-only
  - command lane
  - evidence lane
  - native tool calling availability

### 9. `P1` 工具面混杂三种不同性质

#### 改造目标

拆分工具平面。

#### 主要动作

- 业务读取工具
  - `get_video_summary`
  - `get_video_tools`
  - `get_video_transcript`
  - `list_series_videos`
- UI 动作工具
  - `open_*`
  - `video_seek`
  - `save_note`
- 内部运行态
  - 不再暴露给模型

#### 预期收益

- prompt 更轻
- 模型更容易选对
- 系统边界清晰

#### 验证方式

- 新增脚本 `scripts/run_tool_catalog_dump.py`
- 审核模型可见工具列表不再包含内部状态工具

### 10. `P1` Prompt 过重且每轮重建

#### 改造目标

把 prompt 缩成稳定前缀 + 轻量动态后缀。

#### 主要动作

- 固定系统指令稳定化
- 工具说明最小化
- 动态上下文只保留当前 lane 需要的信息
- 为 provider adapter 预留 cache key

#### 预期收益

- 降低 token 成本
- 提高缓存命中率
- 减少协议噪音

#### 验证方式

- 新增脚本 `scripts/run_prompt_size_report.py`
- 输出每类请求的 prompt token 估算
- 目标：系列与视频链路 prompt 明显缩小

### 11. `P1` 流式体验围绕规划过程设计

#### 改造目标

把流式事件从“展示思考”改成“展示执行”。

#### 主要动作

- 新事件模型围绕：
  - `assistant_started`
  - `assistant_delta`
  - `tool_started`
  - `tool_completed`
  - `answer_started`
  - `answer_delta`
  - `answer_completed`
- `thinking_*` 事件降级或只保留在 debug 模式

#### 预期收益

- 体感更快
- UI 更像真正的工作流执行
- 减少“AI 一直在想”的焦虑

#### 验证方式

- 新增脚本 `scripts/run_stream_event_regression.py`
- 输出事件顺序与耗时摘要

### 12. `P1` 关键行为藏在 prompt 里，导致手工回归昂贵

#### 改造目标

建立三层自动化回归。

#### 主要动作

第一层：单元测试

- lane 路由
- evidence policy
- runtime state
- provider adapter

第二层：集成脚本

- 不调用真实模型
- 用 fake driver 跑完整链路

第三层：真实模型回归脚本

- 参考 `scripts/run_agent_manual_cases.py`
- 但每项重构都新增针对性脚本
- 脚本输出结构化 trace，便于自动读取后由 AI 自己判读

#### 预期收益

- 尽量减少网页手点
- 每次改造都能本地脚本先跑
- 真实模型验证更可复用

#### 验证方式

- 重构完成后新增统一入口 `scripts/run_assistant_regressions.py`
- 支持：
  - `--fake`
  - `--live`
  - `--providers`
  - `--cases`

### 13. `P1` 文档说不做复杂自治 Agent，实现却滑向弱自治循环

#### 改造目标

让文档与实现重新对齐。

#### 主要动作

- 重写 `docs/architecture.md`
- 重写 `docs/agent-tool-chain-design.md`
- 把“thin tool + controlled chain”修正为“lane + runtime + deterministic evidence policy”

#### 预期收益

- 后续决策边界清晰
- 降低设计漂移

#### 验证方式

- 文档审查
- 新目录结构与文档描述一致

### 14. `P2` 当前 Agent 更擅长解释，不擅长快速完成任务

#### 改造目标

把系统优化目标从“解释链路”改成“尽快拿证据并完成任务”。

#### 主要动作

- 以“首个有效工具启动时间”为核心性能指标
- 以“总模型调用次数”作为复杂度指标
- 以“重复读取率”作为质量指标
- 以“每类请求平均工具数”作为工作流健康指标

#### 预期收益

- 体感速度提升
- 真实任务完成效率提升
- 降低绕路与重复

#### 验证方式

- 新增脚本 `scripts/run_assistant_bench.py`
- 输出：
  - first_tool_ms
  - total_duration_ms
  - llm_call_count
  - tool_count
  - duplicate_tool_reads

## 5. 分阶段实施顺序

不能 14 项同时开工，必须按依赖顺序推进。

## Phase 0：基线冻结与脚本基建

### 目标

先能稳定复现当前行为，再做大改。

### 任务

- 保留现有 `run_agent_manual_cases.py` 和 `run_agent_series_reply.py`
- 新建回归脚本基础库：
  - trace 保存
  - provider 选择
  - fake/live 切换
  - 结果快照输出

### 完成标准

- 能对同一 case 输出统一格式的：
  - 事件流
  - 工具轨迹
  - 最终回答
  - 耗时

## Phase 1：重新立边界

### 目标

先把“谁负责什么”改正，不急着上原生 tool loop。

### 任务

- 设计 `studio_assistant` 新层
- 定义三条 lane
- 把内部状态从工具定义中抽离
- 文档先同步

### 完成标准

- 新代码不再新增 planner-first 路径
- 新能力必须归属到某一条 lane

## Phase 2：Provider 层重构

### 目标

接 `LiteLLM`，建立 provider adapter。

### 任务

- 新增 provider port
- 用 `LiteLLM` 实现 chat fallback driver
- 保留现有 openai 兼容路径直到迁移完成

### 完成标准

- 系统可以通过统一 adapter 跑不同 OpenAI-compatible 模型

## Phase 3：单一 Runtime Loop

### 目标

建立新的 assistant runtime 主干。

### 任务

- 去掉强制 planner-first 主循环
- 去掉主路径 responder 二次调用
- 改成 assistant/tool continuation

### 完成标准

- 简单命令不再经过 planner
- 常规问答的模型调用次数下降

## Phase 4：证据工作流确定化

### 目标

把系列 / 视频问答的证据读取逻辑从 prompt 拉回代码。

### 任务

- summary-first policy
- transcript-first policy
- 系列聚合固定流程
- transcript 全文读取与片段定位

### 完成标准

- 高频 case 不再依赖模型反复决定读什么

## Phase 5：流式与并发优化

### 目标

让体验变快、变直接。

### 任务

- 新流式事件协议
- 只读工具并发
- prompt 缩减
- cache key 预留

### 完成标准

- 工具更早启动
- 系列总结类 case 总耗时明显下降

## Phase 6：删除遗留主路径

### 目标

彻底关掉旧 planner-first 主路径。

### 任务

- 旧 planner/responder 迁入 legacy 或删除
- 删除 `<<PLAN>>` 主依赖
- 测试与文档收口

### 完成标准

- 新 runtime 成为唯一默认路径

## 6. 自动化验证体系

本次重构必须坚持：

> 任何一个阶段完成后，都要先跑脚本，再考虑网页手测。

## 6.1 测试层次

### A. 单元测试

放在 `tests/`：

- lane 路由
- evidence policy
- provider adapter
- runtime state
- tool metadata / concurrency policy

### B. 集成脚本

放在 `scripts/`：

- 不依赖真实模型
- 直接运行 runtime
- 打印完整 trace

### C. 真实模型回归脚本

放在 `scripts/`：

- 类似 `run_agent_manual_cases.py`
- 每类能力一组 case
- 输出结构化结果，供后续自动读取与人工抽查

## 6.2 需要新增的脚本

建议新增：

- `scripts/run_assistant_regressions.py`
- `scripts/run_runtime_trace.py`
- `scripts/run_stream_timeline.py`
- `scripts/run_provider_matrix.py`
- `scripts/run_series_batch_probe.py`
- `scripts/run_evidence_policy_cases.py`
- `scripts/run_tool_catalog_dump.py`
- `scripts/run_prompt_size_report.py`
- `scripts/run_stream_event_regression.py`
- `scripts/run_assistant_bench.py`

## 6.3 脚本输出要求

所有脚本统一输出：

- case id
- provider
- lane
- raw event order
- tool trace
- final answer
- timing summary
- notes

这样后续可以：

- 脚本跑完
- AI 直接读脚本输出
- 判断行为是否合理
- 再继续迭代

不需要每次都手动开网页看。

## 7. 里程碑验收

## 里程碑 A：Lane 架构落地

标志：

- 简单命令类请求不再经过 planner

## 里程碑 B：LiteLLM 接入

标志：

- OpenAI-compatible provider 统一从 adapter 入口进入

## 里程碑 C：新 Runtime Loop 落地

标志：

- `<<PLAN>>` 不再是默认主路径

## 里程碑 D：系列 / 视频证据流稳定

标志：

- 系列主题、学习路径、角色对比、视频原话、视频定位这几类 case 可以通过脚本稳定回归

## 里程碑 E：旧主路径退役

标志：

- 旧 planner/responder 主链路删除或彻底降级到 legacy fallback

## 8. 执行约束

### 必须做

- 每阶段先补回归脚本，再大改主链路
- 每个 PR 限定清晰边界，不要一次横切所有目录
- 保持 `video_summary` 主域清晰，不要把它再吸进 runtime

### 禁止做

- 继续往 prompt 里堆规则补 runtime 漏洞
- 再新增内部状态型模型工具
- 为兼容旧实现而长期保留双重主路径
- 把 `LiteLLM` 当成业务框架

## 9. 下一步建议

按执行顺序，下一轮实际开工建议是：

1. 建 `docs/plan` 下的脚本与阶段计划索引
2. 搭建统一回归脚本基座
3. 设计 `studio_assistant` 的 lane / runtime / provider port
4. 引入 `LiteLLM`
5. 再开始拆 planner-first 主循环

一句话总结：

> 这次不是“继续修 planner”，而是“把系统从 planner-first 拉回业务工作台，然后用 runtime 重建正确的智能化边界”。
