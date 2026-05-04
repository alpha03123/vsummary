# Series Scope RAG TASKS

## 1. 文档目的

本文是执行拆解草案，不是最终技术合同。  
它假定 `INTENT` 和 `SPEC` 已经通过人工审核。

---

## 2. 执行原则

1. 每个阶段都必须能单独观察结果
2. 每个阶段都必须有对应验证
3. 先建立可观测性，再替换主链路
4. 这是一次去兼容的大重构，但实施顺序仍要分阶段可验证

---

## 3. Phase 1: 资产层与调试基础

- [x] 1.1 在 workspace 层新增 `series_catalog.json` 生成/读取能力
- [x] 1.2 将 `series_catalog.json` 明确为代码派生视图，不走模型生成
- [x] 1.3 约束 `one_sentence_summary` 直接复用现有 `summary.json` 字段
- [x] 1.4 约束 `chapter_titles` 只能由 `chapters[*].title` 派生
- [x] 1.5 约束 catalog 不挂载 transcript 正文或 `transcript_segments`
- [x] 1.6 在 workspace 层新增 `series_overview.json` 生成/读取能力
- [x] 1.7 将 `series_overview.json` 收缩为 `overview + topic_groups + learning_path`
- [x] 1.8 为 catalog / overview 增加 schema 验证测试
- [x] 1.9 新增 `run_series_scope_debug_trace.py`
- [x] 1.10 让调试脚本能输出 `graph_input`
- [x] 1.11 让调试脚本能落盘 trace JSON

阶段验收：

1. 能生成 `series_catalog.json`
2. 能生成 `series_overview.json`
3. `series_catalog.json` 不依赖额外模型输出
4. 能通过脚本拿到 trace 文件

---

## 4. Phase 2: 新查询合同

- [x] 2.1 在 `query/models.py` 新增 `SeriesQueryUnderstanding`
- [x] 2.2 新增 `RetrievalHit`
- [x] 2.3 新增 `SeriesAnswerPayload`
- [x] 2.4 新建 `series_query_processor.py`
- [x] 2.5 将 Query Understanding 合同收缩为 `normalized_query + subqueries + filters`
- [x] 2.6 明确 Query Processor 不产出任何 execution plan / source policy
- [x] 2.7 为 overview / concept / locate 各写 1 个合同测试
- [x] 2.8 在 debug trace 中输出 `series_query_processor`

阶段验收：

1. 新 Query Processor 已能输出 `normalized_query / subqueries / filters`
2. 不再输出 `selected_videos / subplans / target_video_ids`
3. 默认不输出 `task_type`
4. 默认不输出 `retrieval_hints`
5. 默认不输出任何 `prefer_source_types / allow_source_types`

---

## 5. Phase 3: Unified Retrieval 收口

- [x] 3.1 在 retrieval 层统一 `source_type`
- [x] 3.2 引入 `series_synopsis` 文档类型
- [x] 3.3 将 `summary` 重命名为 `summary_global`
- [x] 3.4 将 `chapter` 重命名为 `summary_chapter`
- [x] 3.5 新增 `document_schema.py`
- [x] 3.6 新增 `index_builder.py`
- [x] 3.7 将索引构建前移出用户查询链路
- [x] 3.8 约束 retrieval 不再按问题类型走特殊执行分支
- [x] 3.9 在视频 `summary` 成功生成后触发 `series_catalog.json` 重建
- [x] 3.10 在视频 `summary` 成功生成后触发 `series_overview.json` 重建
- [x] 3.11 在视频 `summary` 成功生成后触发 unified index 刷新
- [x] 3.11.1 上述长期知识记忆刷新允许异步执行
- [x] 3.11.2 异步刷新失败不能阻塞问答主链路
- [x] 3.12 在 debug trace 中输出 `retrieval_request`
- [x] 3.13 在 debug trace 中输出 `retrieval_response`

阶段验收：

1. overview case 能命中 `series_synopsis`
2. locate case 能命中 `summary_chapter` 或 `transcript_chunk`
3. 调试信息可见真实 hit 列表
4. overview / concept / locate 走同一条 unified retrieval 主路径
5. 查询时不再发生首问建索引

---

## 6. Phase 4: Answer Synthesis 收口

- [x] 4.1 新建 `series_answer_synthesizer.py`
- [x] 4.2 将 answer 层改为吃 `query_understanding + retrieval_hits`
- [x] 4.3 在 debug trace 中输出 `answer_synthesis`
- [x] 4.4 对 answer payload 做 schema 验证
- [x] 4.5 增加 “不暴露内部字段” 回归测试
- [x] 4.6 保持对外 HTTP 响应形状稳定，只在内部收缩合同

阶段验收：

1. `answer_payload.used_source_types` 可用于观察主要证据类型
2. 回答不再依赖旧 `query_plan`
3. 业务回答质量优先于内部标签精确性
4. 对外接口仍返回现有 `assistant_message / reason / tool_results / citations`

---

## 7. Phase 5: Graph 主路径替换

目标链路必须固定为：

```mermaid
flowchart LR
    A[用户提问] --> B[understand_query]
    B --> C[retrieve_evidence]
    C --> D[synthesize_answer]
    D --> E[finalize]
    E --> F[update_session_memory]
```

- [x] 5.1 在 `runtime/graph.py` 新增 `understand_query -> retrieve_evidence -> answer -> finalize -> update_session_memory` 主路径
- [x] 5.2 在 `runtime/nodes.py` 新增对应节点
- [x] 5.3 将 graph 收尾节点明确命名为 `update_session_memory`
- [x] 5.4 让 `update_session_memory` 持久化 session 内全部 `user/assistant` turn
- [x] 5.5 让 `update_session_memory` 仅在接近上下文上限时触发历史压缩
- [x] 5.6 禁止 `update_session_memory` 写入 RAG 命中的知识正文
- [x] 5.7 让 `series scope` 默认走新路径
- [x] 5.8 删除 `series scope` 对 `build_plan / advance_subplan / execute_* subplan` 的依赖
- [x] 5.9 删除 `SeriesPlanner` 作为 `series scope` 主入口
- [x] 5.10 删除 `SeriesAggregator` 作为 `series scope` 主答案入口
- [x] 5.11 增加“新链路不出现 legacy fields”测试

阶段验收：

1. `series scope` 已不再走 `subplans`
2. `series scope` 已不再依赖 `selected_videos / target_video_ids`
3. session 内短期记忆按完整 turn 持久化，超限时才压缩
4. 调试 trace 中 legacy 字段不再出现为主字段

---

## 8. Phase 6: 回归与清理

- [x] 6.1 新增 `check_series_scope_contracts.py`
- [x] 6.2 新增 `test_series_scope_contracts.py`
- [x] 6.3 为 overview / concept / locate 固化 expected fixtures
- [x] 6.4 fixture 结构改为 `assertions` 驱动，而不是最终回答文本全等
- [x] 6.5 删除 `SeriesPlanner` 在 `series scope` 中的残留协议与调试字段
- [x] 6.6 删除 `SeriesAggregator` 在 `series scope` 中的残留协议与调试字段
- [x] 6.7 清理旧 `summary/chapter` 命名在测试与调试脚本中的残留
- [x] 6.8 更新相关调试与分析脚本说明

阶段验收：

1. 三类问题都有回归测试
2. 合同测试不依赖最终文本全等
3. diff 报告能指出是 query 理解错了、检索命中错了，还是答案组织错了
4. 回归测试以大体验收为主，不对内部字段做过度苛刻绑定
5. `series scope` 相关残留旧协议已从主代码路径移除

---

## 9. 每阶段禁止事项

### 所有阶段都禁止

- [ ] 把 `chapter_titles` 改成模型重复输出字段
- [ ] 把 `series_catalog.json` 设计成模型生成资产
- [ ] 在 `series_overview.json` 中重复堆入 `catalog` 已有视频级字段
- [ ] 在新链路继续扩展 `selected_videos`
- [ ] 在新链路继续扩展 `subplans`
- [ ] 在 query understanding 默认合同里恢复 `prefer_source_types / allow_source_types`
- [ ] 在 query understanding 默认合同里恢复 `task_type`
- [ ] 在 query understanding 默认合同里恢复 `retrieval_hints`
- [ ] 在 retrieval 层按 overview / concept / locate 再造特殊执行分支
- [ ] 把 `source_type` 或 `used_source_types` 变成业务体验的硬门槛
- [ ] 用人工肉眼看回答代替结构验收
- [ ] 查询时偷偷继续构建全量索引
- [ ] 为 `series scope` 保留旧 planner/subplan 兼容主路径

---

## 10. 最终完成条件

- [x] overview / concept / locate 三类问题都通过结构合同回归
- [x] `series_catalog.json` 与 `series_overview.json` 已稳定生成
- [x] `series_catalog.json` 已确认由代码派生，不依赖模型生成
- [x] 新链路调试 trace 完整可见
- [x] `series scope` 主路径不再依赖 `selected_videos/subplans/target_video_ids`
- [x] 查询链路不再承担索引构建，summary 成功后会触发 catalog / overview / index 刷新
- [x] `update_session_memory` 只负责短期会话记忆，不承担长期知识记忆刷新
- [x] 验收脚本以结构和关键字段为主，不以回答文本全等为主
- [x] 业务体验验收优先，内部 trace 主要用于排障和辅助观察
