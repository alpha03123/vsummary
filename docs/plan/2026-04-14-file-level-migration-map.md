# File-Level Migration Map

## 目的

本文是 `legacy main` 到 `codex/langgraph-refactor` 的文件/模块级迁移清单。

它回答四个问题：

1. `legacy main` 的每个关键模块应该迁到 worktree 哪里
2. 该模块应当 `保留 / 重写 / 删除`
3. 应由哪种技术栈替代其中的重复轮子
4. 哪些业务能力必须保留为自研资产，不能被技术栈“抹平”

本文是后续实现迁移的直接操作清单，不是原则性讨论。

---

## 一、总原则

### 1. worktree 拥有架构主权

后续目录结构、运行机制、边界定义，全部以 worktree 为准。  
`legacy main` 只提供业务资产和验证资产。

### 2. 技术栈只替轮子，不替业务精髓

下列内容必须保留为业务资产：

- `video_graph` 的细粒度定位能力
- citation / slot / seek 结构
- `selected_videos / selection_mode / subplans / depth`
- `series/video` 的证据选择策略
- long-case / debug / profile 的验证护栏

### 3. 技术栈替代目标

- `LangGraph`：替代编排/runtime/session glue
- `DSPy`：替代大段 prompt 和 prompt 内隐逻辑
- `Trustcall`：替代 structured output repair / retry 胶水
- `LlamaIndex`：替代 retrieval orchestration / 文档拼装
- `LanceDB`：替代本地 evidence store / 检索底座
- `保留自研`：保留业务定位、citation、plan 语义、验证资产

---

## 二、目录级迁移映射

| Legacy Main | Worktree 去向 | 策略 | 技术栈替代 | 说明 |
|---|---|---|---|---|
| `src/backend/studio_assistant/` | `src/backend/agent_graph/` + 少量 `backend/agent/` 共享协议层 | `拆解重写` | `LangGraph` + `DSPy` + `保留自研` | 这是当前主业务内核，不能整体搬运，必须拆成 graph / programs / retrieval / service |
| `src/backend/agent/runtime/` | `src/backend/agent_graph/graph.py`、`nodes.py`、`service.py` | `删除并替代` | `LangGraph` | 运行时编排轮子不继续保留 |
| `src/backend/agent/session/` | `agent_graph/service.py` 临时兼容，后续下沉到 graph persistence | `部分保留，部分删除` | `LangGraph` + `保留自研` | 当前阶段保留 `FileAgentSessionStore` 兼容外部接口，最终由 graph persistence 收口 |
| `src/backend/agent/memory/` | `agent_graph/state.py` + `memory update node` | `大部分删除` | `LangGraph` + `DSPy` | 仅保留必要上下文协议；状态推进逻辑不再自制 |
| `src/backend/agent/validation/` | `agent_graph/programs.py` 输出约束 + Trustcall adapter + 少量业务校验 | `大幅删除` | `Trustcall` + `保留自研` | 通用修 JSON/修 schema 的胶水应清退，业务约束保留 |
| `src/backend/agent/tools/` | `agent_graph/action_dispatcher.py` + 现有工具实现 | `大体保留` | `保留自研` | 这些是业务动作适配器，不是主要冗余点 |
| `src/backend/agent/schemas/` | 继续保留；部分新增 graph 专用 schema 于 `agent_graph/models.py` | `保留并收缩` | `保留自研` | 对外协议层仍然需要 |
| `src/backend/agent/infrastructure/` | 继续保留，部分复用到 graph service bootstrap | `保留` | `保留自研` | `ChatGateway`、`ContextLoader` 等不必重造 |
| `src/backend/api/` | worktree 当前 `api/bootstrap.py` / `api/app.py` | `保留并继续收口` | `保留自研` | API 是交付层，不应被新技术栈接管 |
| `src/backend/video_summary/` | 基本原样保留 | `保留` | `保留自研` | 内容主域不是本次替换对象 |
| `scripts/` 中 trace/profile/long-case | worktree 对应 `scripts/` | `优先迁移` | `保留自研` | 这是验证资产，必须先迁 |
| `tests/test_studio_assistant_*` | worktree `tests/test_agent_graph_*` + 新回归测试 | `拆分迁移` | `保留自研` | 旧测试语义不能丢，但要映射到新 graph |

---

## 三、关键文件级迁移

## 3.1 `studio_assistant` 主链

### `src/backend/studio_assistant/service.py`

- Worktree 去向：
  - `src/backend/agent_graph/service.py`
  - 部分事件流语义继续保留在 API 交付层
- 策略：`重写`
- 技术栈替代：
  - 编排由 `LangGraph`
  - 会话推进由 `LangGraph state/persistence` 逐步替代
  - `保留自研`：turn result 语义、对外 stream 语义

保留点：

- 一轮请求的输入/输出契约
- SSE 事件语义
- 与前端兼容的 `AgentTurnResult`

删除点：

- 手写 orchestration 主链

### `src/backend/studio_assistant/scope_router.py`

- Worktree 去向：
  - `src/backend/agent_graph/graph.py`
  - `src/backend/agent_graph/nodes.py`
- 策略：`重写`
- 技术栈替代：`LangGraph`

保留点：

- `series` 与 `video` 是两类 scope，不是两套产品

删除点：

- 手写 scope dispatch glue

### `src/backend/studio_assistant/planner.py`

- Worktree 去向：
  - `src/backend/agent_graph/programs.py`
  - 后续建议新增：`src/backend/agent_graph/planning.py`
- 策略：`业务语义保留，输出形状重写`
- 技术栈替代：
  - `DSPy` 替 prompt
  - `Trustcall` 替结构修复
  - `保留自研`：`selected_videos / selection_mode / subplans / depth`

必须保留：

- `selected_videos`
- `carry_forward`
- `subplans`
- `depth`
- candidate/fallback 经验

必须删除：

- 手写 contract retry loop
- 将 prompt 当业务逻辑本体的做法

### `src/backend/studio_assistant/video_planner.py`

- Worktree 去向：
  - `src/backend/agent_graph/programs.py`
  - `src/backend/agent_graph/nodes.py`
- 策略：`重写`
- 技术栈替代：
  - `DSPy`
  - `Trustcall`

必须保留：

- “只靠 summary 能否回答”
- “是否需要下沉 transcript/video_graph”

必须删除：

- 老的 `understand / locate` 固定意图思路作为主业务模型

### `src/backend/studio_assistant/series_executor.py`

- Worktree 去向：
  - `src/backend/agent_graph/nodes.py`
  - retrieval / pinpoint 由专门节点替代
- 策略：`拆解重写`
- 技术栈替代：
  - `LangGraph` 编排
  - `LlamaIndex` 召回
  - `保留自研`：按深度执行的业务语义

必须保留：

- `series_meta / summary / video_graph` 三档深度的业务含义

### `src/backend/studio_assistant/video_executor.py`

- Worktree 去向：
  - `src/backend/agent_graph/nodes.py`
- 策略：`拆解重写`
- 技术栈替代：
  - `LangGraph`
  - `LlamaIndex`
  - `保留自研`

必须保留：

- video scope 下 summary / pinpoint 的选择逻辑

### `src/backend/studio_assistant/video_graph.py`

- Worktree 去向：
  - 短期：保留为独立业务模块，接入 `agent_graph/nodes.py`
  - 中期建议：`src/backend/agent_graph/pinpoint.py` 或 `src/backend/agent_graph/video_graph.py`
- 策略：`保留业务算法，接口重写`
- 技术栈替代：
  - 召回前半段可由 `LlamaIndex + LanceDB` 提供候选
  - 最后一跳精排 / slot / seek 继续 `保留自研`

必须保留：

- query slot 拆分
- lexical + semantic 融合
- best match / slots
- `video_seek`
- transcript citation 原始依据

不能被技术栈替掉：

- 这个模块的业务价值不是“检索”，而是“最后一跳细定位”

### `src/backend/studio_assistant/aggregator.py`

- Worktree 去向：
  - `src/backend/agent_graph/programs.py`
  - `src/backend/agent_graph/nodes.py`
  - citation 相关建议后续单拆：`src/backend/agent_graph/citations.py`
- 策略：`拆解重写`
- 技术栈替代：
  - `DSPy` 替回答合成 prompt
  - `保留自研`：citation schema、summary/transcript citation 组装

必须保留：

- citation 装配能力
- transcript / summary 两类证据如何映射到 citation
- deterministic curate 思路

必须删除：

- 回答逻辑依赖大段 prompt 的实现方式

---

## 3.2 `agent` 平台层

### `src/backend/agent/runtime/*`

- Worktree 去向：
  - `src/backend/agent_graph/graph.py`
  - `src/backend/agent_graph/nodes.py`
  - `src/backend/agent_graph/service.py`
- 策略：`删除`
- 技术栈替代：`LangGraph`

说明：

- 这是本次最主要的“重复轮子”清退区
- 不允许把它再包装成新的 graph 外 runtime

### `src/backend/agent/session/store.py`

- Worktree 去向：
  - 短期保留
  - 中期收口到 graph persistence
- 策略：`阶段性保留`
- 技术栈替代：
  - 短期 `保留自研`
  - 中期 `LangGraph persistence`

说明：

- 现在它承担兼容作用，不能立刻删
- 但不应继续长出更多平台逻辑

### `src/backend/agent/session/models.py`

- Worktree 去向：
  - 保留现有协议，逐步精简
- 策略：`保留`
- 技术栈替代：`保留自研`

说明：

- 历史消息、会话快照是外部兼容协议，不是重复轮子本身

### `src/backend/agent/memory/context.py`

- Worktree 去向：
  - 保留 `AgentContext`
  - graph state 另存于 `agent_graph/state.py`
- 策略：`部分保留`
- 技术栈替代：
  - `AgentContext` 保留自研
  - 会话级 state 推进由 `LangGraph`

说明：

- `AgentContext` 仍然是 API 与业务上下文边界对象
- 但 runtime 内状态推进不再依赖它承担所有职责

### `src/backend/agent/memory/store.py`

- Worktree 去向：
  - graph persistence / state store
- 策略：`删除主职责`
- 技术栈替代：`LangGraph`

### `src/backend/agent/context/*`

- Worktree 去向：
  - 预算/压缩中必要部分保留
  - runtime 状态管理部分删除
- 策略：`拆分保留`
- 技术栈替代：
  - 上下文预算：`保留自研`
  - 状态推进：`LangGraph`

说明：

- `AgentContextBudgetService` 现在仍有价值
- 但不能继续绑定旧 runtime 形状

### `src/backend/agent/validation/*`

- Worktree 去向：
  - `Trustcall` adapter
  - 少量业务级 guard
- 策略：`大幅删除`
- 技术栈替代：`Trustcall`

必须保留：

- scope 合法性
- 业务动作合法性

必须删除：

- 通用 schema repair
- planner/tool loop 的结构修补胶水

### `src/backend/agent/tools/*`

- Worktree 去向：
  - 继续保留为 action dispatcher 依赖
- 策略：`保留`
- 技术栈替代：`保留自研`

说明：

- 这些是业务动作执行器，不是主要冗余点

### `src/backend/agent/schemas/action_plan.py`

- Worktree 去向：
  - 保留对外协议
  - graph 内部不要继续沿用旧 planner-first 语义
- 策略：`保留并收缩`
- 技术栈替代：`保留自研`

说明：

- 对外 API 仍需要 `AgentTurnResult`
- 但 graph 内部 state/planning object 不必强行复用旧 `AgentActionPlan`

### `src/backend/agent/schemas/tool_calls.py`

- Worktree 去向：
  - 继续保留
- 策略：`保留`
- 技术栈替代：`保留自研`

说明：

- `ToolName`、`ToolExecutionResult` 仍是前后端协议

---

## 3.3 `api` 与 `video_summary`

### `src/backend/api/bootstrap.py`

- Worktree 去向：
  - 当前 worktree 自己的 `src/backend/api/bootstrap.py`
- 策略：`保留并继续收口`
- 技术栈替代：`保留自研`

说明：

- composition root 不应交给框架自动魔法
- 但内部组装目标从 `StudioAssistantService` 转为 `AgentGraphService`

### `src/backend/api/app.py`

- Worktree 去向：
  - 当前 worktree `src/backend/api/app.py`
- 策略：`保留`
- 技术栈替代：`保留自研`

说明：

- HTTP 交付层不是主要冗余点
- 但后续仍应继续按 router/handler 收口

### `src/backend/video_summary/*`

- Worktree 去向：
  - 原样保留
- 策略：`保留`
- 技术栈替代：`保留自研`

说明：

- 这是内容主域，不应因 graph 重构而被误伤

---

## 四、验证资产迁移

这些不应被技术栈替代，必须优先迁入 worktree。

### `scripts/run_runtime_trace.py`

- Worktree 去向：同名脚本继续保留并增强
- 策略：`保留并重写内部探针`
- 技术栈替代：`保留自研`

说明：

- graph 接管后，仍需要事件流时序观测

### `scripts/run_provider_trace.py`

- Worktree 去向：同名脚本继续保留
- 策略：`保留`
- 技术栈替代：`保留自研`

说明：

- 这是“到底打了几次模型”的护栏，不能丢

### `scripts/run_speed_profile.py`

- Worktree 去向：
  - 新增到 worktree
- 策略：`必须迁移并改写`
- 技术栈替代：`保留自研`

说明：

- 目前 worktree 缺这一块
- cutover 前必须补齐

### `scripts/run_new_arch_long_tests.py`

- Worktree 去向：
  - 新增到 worktree
- 策略：`必须迁移`
- 技术栈替代：`保留自研`

说明：

- 这是业务真回归，不是框架能力
- 必须成为 cutover gate

### `docs/manual-agent-tool-chain-test.md`

- Worktree 去向：
  - 保留并逐步更新到 graph 语义
- 策略：`保留并改写`
- 技术栈替代：`保留自研`

### `docs/plan/2026-04-11-new-architecture-long-tests.md`

- Worktree 去向：
  - 保留
- 策略：`保留`
- 技术栈替代：`保留自研`

说明：

- 这是产品能力护栏，不是实现细节文档

---

## 五、优先级排序

### P0：必须先做

1. 把验证资产迁入 worktree：
   - `run_speed_profile.py`
   - `run_new_arch_long_tests.py`
   - runtime/provider trace 对齐 graph
2. 明确 graph 路径下的 debug 输出机制
3. 把 `video_graph` 接成 graph 的可复用业务节点

### P1：核心业务迁移

1. `planner.py` 业务语义迁移
2. `aggregator.py` citation 迁移
3. summary / transcript evidence 策略迁移

### P2：平台层清退

1. `agent/runtime/*`
2. `agent/validation/*` 的通用 repair
3. `agent/memory/*` 的状态推进职责
4. `agent/session/*` 中多余的 orchestrator 逻辑

---

## 六、最终判断标准

如果一个 legacy 文件/模块满足以下条件之一，就不应原样迁：

1. 只是平台胶水
2. 其职责已被成熟技术栈完整覆盖
3. 它承载的是旧架构形状，而不是业务能力

如果一个 legacy 文件/模块满足以下条件之一，就必须保留其语义：

1. 它体现了真实业务规划经验
2. 它体现了真实证据定位能力
3. 它构成了回归/性能/调试护栏
4. 它定义了前后端契约

---

## 七、一句话执行策略

> 先迁验证资产，再迁业务资产，最后删除平台轮子；  
> 技术栈负责替轮子，自研代码负责保留业务精髓。
