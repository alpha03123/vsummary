# Main Freeze And Worktree Cutover Plan

## 背景

当前根工作区 `main` 已经积累了较多重复平台层、自定义 runtime 胶水与多处冗余抽象。  
未来主线不应继续在 `main` 上“边清理边生长”，而应改为：

- 冻结当前 `main`，作为 `legacy` 基线
- 让 `codex/langgraph-refactor` worktree 成为未来主线
- 从 `main` 只迁移业务精髓，不迁移旧平台形状

本次 cutover 的最高目标是：

1. 去冗余
2. 去重复造轮子
3. 提升可读性与边界清晰度
4. 允许实现细节与 `legacy main` 不同
5. 只要求 long case / debug 输出合理、可解释、可回归

## 已执行的冻结动作

- 已创建冻结分支：`legacy/main-baseline-2026-04-14`
- 已导出根工作区未提交改动补丁：
  - `E:/gittools/self/video_include/temp/migration-snapshots/main-salvage-2026-04-14.patch`

约束：

- 根工作区 `main` 不再继续承担新架构开发
- 后续实现工作默认只在 `codex/langgraph-refactor` worktree 中进行

## 核心迁移原则

### 1. worktree 拥有架构主权

新系统以 `codex/langgraph-refactor` 的目标架构为准。  
`main` 只作为能力来源，不再作为架构蓝本。

### 2. 迁移能力，不迁移包袱

应迁移：

- `video_graph` 的细粒度定位与打分思路
- citation / slot / seek 的证据表达
- `series/video` 问答中的真实 evidence 使用策略
- `selected_videos` / `subplans` / `depth` 这些业务规划语义
- long case / debug / perf 的验证资产

不应迁移：

- 自定义 runtime 外壳
- 自定义 session / memory / validation repair 胶水
- planner-first / responder-first 遗留路径
- 为旧平台抽象服务的目录形状
- 过时的 `understand / locate / meta_state / action` 旧意图 taxonomy

### 3. 优先用成熟技术替代重复轮子

一旦官方文档或成熟能力能覆盖当前自制机制，应优先删减而不是保留双轨。

## 技术栈替代映射

### LangGraph

用于替代：

- 自定义 workflow 编排
- tool loop glue
- 大部分 session orchestration
- 大部分 memory/state 推进
- graph 外壳式 runtime 代码

目标替换对象：

- `src/backend/agent/runtime/*`
- `src/backend/agent/session/*` 中承担编排的部分
- `src/backend/agent/memory/*` 中承担状态推进的部分

保留边界：

- 不替代 `video_graph` 的业务细定位算法
- 不替代 citation schema
- 不替代业务 planning object

### DSPy

用于替代：

- 大段 prompt 字符串
- prompt 中隐式埋着的分类/拆分/回答逻辑
- 手写 LM 程序化节点

目标替换对象：

- `planner.py` 中的规划 prompt
- `video_planner.py` 中的 summary/transcript 决策 prompt
- `aggregator.py` 中的回答合成 prompt

约束：

- 不复活旧 `understand / locate` 分类体系
- 输出结构应贴近新系统业务对象，例如：
  - `selected_videos`
  - `subplans`
  - `depth`
  - `needs_pinpoint_evidence`

### Trustcall

用于替代：

- structured output repair
- schema retry glue
- tool args 修复
- “模型先吐错，再手写补丁修正”的重试逻辑

目标替换对象：

- `src/backend/agent/validation/*`
- planner 的 contract repair / retry glue
- 任何“补一轮提示词修 JSON”的通用修补逻辑

保留边界：

- 业务约束校验保留
- 业务正确性判断不交给 Trustcall

### LlamaIndex

用于替代：

- retrieval orchestration
- 文档拼装
- summary/chapter/transcript 的统一 ingestion / retrieval pipeline
- query pipeline 组织

目标替换对象：

- 分散在代码里的 evidence document 拼装
- 自定义 source routing 胶水
- 手工维护的 summary/transcript/chapter 多源检索流程

保留边界：

- 召回由 LlamaIndex 负责
- 最后一跳 pinpoint / rerank 仍可由业务侧 `video_graph` 负责

### LanceDB

用于替代：

- 自定义本地 evidence store
- 基于文件遍历的 ad-hoc 检索底座
- 未来若继续生长出的轻量向量库轮子

存储对象建议：

- transcript chunks
- summary blocks
- chapter nodes
- note fragments

关键 metadata：

- `series_id`
- `video_id`
- `source_type`
- `chapter_id`
- `start_seconds`
- `end_seconds`

## 必须保留的验证资产

迁移优先级最高的不是业务代码，而是验证护栏。

必须先收口到 worktree：

1. 核心 long case
2. debug case
3. 性能基准
4. 关键业务样本集

判断标准：

- 不要求与 `legacy main` 文案逐字一致
- 要求：
  - 证据使用合理
  - debug 输出可解释
  - long case 不明显退化
  - 关键定位请求能稳定给出 citation / seek 信息

## 分阶段迁移顺序

### Phase 0：冻结与护栏

- 保持 `legacy/main-baseline-2026-04-14` 不动
- 把 long/debug/perf case 显式迁入 worktree
- 定义 cutover gate

### Phase 1：新架构接入但不切流

- 在 worktree 中建立新 graph 主路径
- 保持 API 兼容壳
- 允许旧系统作为对照组存在

### Phase 2：迁移业务精髓

优先顺序：

1. `video_graph`
2. citation schema
3. `series/video` evidence 策略
4. planner 的 `selected_videos / subplans / carry_forward` 经验

### Phase 3：删除重复轮子

在新路径通过 long/debug/perf gate 后，逐步删除：

- 旧 runtime glue
- 旧 session orchestration
- 旧 validation repair
- 与旧 planner-first 强耦合的辅助模块

### Phase 4：切换主线

- 让 worktree 架构成为默认主线
- 根工作区 `main` 不再承载旧系统继续演化

## Cutover Gate

只有满足以下条件，worktree 才能接管：

1. `video summary` 路径稳定
2. `video locate` 路径稳定
3. `series summary` 路径稳定
4. `series relationship` 路径稳定
5. long case 输出合理
6. debug 输出可解释
7. 关键 perf 不显著劣化
8. 新系统代码层次少于旧系统

## 决策准绳

今后所有迁移决策都按以下顺序判断：

1. 是否能删掉一层抽象？
2. 是否能用成熟技术栈替掉当前自制轮子？
3. 是否保留了业务精髓？
4. 是否提升了代码可读性？
5. 是否保持了 long/debug case 的合理性？

如果答案是否，则不应迁移该实现形状。
