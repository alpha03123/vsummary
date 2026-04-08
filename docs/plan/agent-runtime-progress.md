# Agent Runtime 重构进度

## 1. 说明

本文件只记录执行状态，不重复设计内容。

- 设计准绳以 [agent-runtime-overhaul-plan.md](/E:/gittools/self/video_include/docs/plan/agent-runtime-overhaul-plan.md) 的 14 条改造目标为准。
- 只有达到可交付状态的批次，才会把目标标记为“已完成”。
- 如果只是完成局部基础设施、前置清理或试运行验证，则标记为“进行中”，不会提前算完成。

状态约定：

- `未开始`
- `进行中`
- `已完成`

## 2. 当前总览

更新时间：2026-04-08（第十二次更新）

当前完成度：

- 已完成：`13 / 14`
- 进行中：`1 / 14`
- 未开始：`0 / 14`
- 体感进度：主干能力约 `95%`

阶段判断：

- 首轮高频请求已经全部脱离旧 `planner-first` 主路径。
- runtime 已经具备了首轮路由、确定性证据链、批量并发读取、直接动作回复这些关键骨架。
- 当前剩余工作，已经不再是“删 planner”，而是继续把 runtime/lane 结构收紧，并把产品命名与目录进一步对齐。

1. `#1 产品重心回归业务工作台`
状态：进行中
当前已完成：
- runtime 已按业务语义拆出 [lanes](/E:/gittools/self/video_include/src/backend/agent/runtime/lanes)，不再围绕 `planner / responder` 组织。
- [assistant_runtime.py](/E:/gittools/self/video_include/src/backend/agent/runtime/assistant_runtime.py) 现在更像工作台交互编排层，而不是通用 Agent 循环。
- 已删除 `planner.py`、`legacy_planner_runtime.py`、`responder.py`、旧 `prompt.py`，减少“通用 Agent 编排器”残影。
- 已新增会话级 evidence cache：
  - [evidence_cache.py](/E:/gittools/self/video_include/src/backend/agent/session/evidence_cache.py)
  - [store.py](/E:/gittools/self/video_include/src/backend/agent/session/store.py)
  现在会持久化可复用的 `list_series_videos / get_video_summary / get_video_transcript` 结果，避免下一轮重复读取。
- 当前主代码的复杂度中心已经明显转到：
  - 请求路由
  - 证据读取
  - UI 动作编排
  - runtime lane
- Agent 上下文窗口与压缩阈值已开始从业务配置统一读取，不再散落在多处硬编码默认值中。
- 已新增 [prompt_projection.py](/E:/gittools/self/video_include/src/backend/agent/runtime/prompt_projection.py)，回答阶段不再把完整 `tool_results` 原样注入模型，而是按意图裁剪成最小证据投影。
- 已新增 [semantic_compactor.py](/E:/gittools/self/video_include/src/backend/agent/context/semantic_compactor.py)，旧字符截断压缩已替换为语义压缩。
- 剩余差距主要在命名与目录层，尤其 `agent` 包名本身还没有收敛到更贴近“工作台交互编排”的名字。

2. `#2 移除 <<PLAN>> 作为主路径协议`
状态：已完成
本批落地：
- 已新增 [request_router.py](/E:/gittools/self/video_include/src/backend/agent/runtime/request_router.py)。
- 常见 `series/video` 内容问答与部分打开工具请求，首轮已经可以走无 `<<PLAN>>` 的 JSON 路由主路径。
- 旧 planner 已从主代码删除。
- 已新增 [assistant_runtime.py](/E:/gittools/self/video_include/src/backend/agent/runtime/assistant_runtime.py) 作为新的 runtime 主入口。
- [service.py](/E:/gittools/self/video_include/src/backend/agent/agent/service.py) 已收敛为薄应用壳，只负责上下文加载、runtime 委托、消息持久化。
- 已新增 routed path 的 live 仿真脚本 [run_agent_routed_live_cases.py](/E:/gittools/self/video_include/scripts/run_agent_routed_live_cases.py)。
- `video_seek` 定位请求也已进入 routed path，不再默认回退到旧 planner。
- `save_note` 记重点请求已进入 routed path，主链路变为 `get_video_summary -> save_note`，必要时可再降级读取 transcript。
- `series_locate` 系列定位请求已进入 routed path，主链路变为 `list_series_videos -> batch get_video_summary -> 候选选择 -> get_video_transcript`。
- `open_overview / open_mindmap` 在内容缺失时，已可由 runtime 直接展开为 “generate -> open” 两步动作，不再只切页。
- 已新增 [run_runtime_trace.py](/E:/gittools/self/video_include/scripts/run_runtime_trace.py) 与 [run_provider_trace.py](/E:/gittools/self/video_include/scripts/run_provider_trace.py)。
- 运行 `run_runtime_trace.py --case series-summary` 已确认 routed 主路径中 `plan_sentinel_seen=False`。
- [planner.py](/E:/gittools/self/video_include/src/backend/agent/agent/planner.py) 与 [legacy_planner_runtime.py](/E:/gittools/self/video_include/src/backend/agent/runtime/legacy_planner_runtime.py) 已删除。

3. `#3 去掉 Planner / Responder 双模型调用主路径`
状态：已完成
本批落地：
- `video` 的 summary/transcript 首轮证据读取已可直接绕过 planner。
- `series` 的 summary-first 首轮证据读取已可直接绕过 planner。
- 部分打开工具请求的首轮也已可直接绕过 planner。
- 已新增 [routed_answerer.py](/E:/gittools/self/video_include/src/backend/agent/runtime/routed_answerer.py)，常见 routed QA 路径不再默认走旧 responder prompt，而是走更轻的证据回答器。
- `video_summary / series_summary` 的 routed path 现在已形成 “request router -> routed loop -> lightweight answerer”。
- `series_locate` 现在也已形成 “request router -> routed loop -> lightweight answerer”，中间只增加一个候选选择器模型调用。
- 当前主路径已经不再进入旧 `planner / responder` 双模型调用链；`responder.py` 已删除。

4. `#4 主循环从按轮规划改成按事件推进`
状态：已完成
本批落地：
- 对走新主路径的首轮请求，运行时现在是“先路由，再执行，再回答”，而不是先进入 planner 循环。
- `series/video` 的确定性证据链已由 runtime 驱动，而不是轮轮重新规划。
- routed loop 已从 `service.py` 中拆出，沉到 [assistant_runtime.py](/E:/gittools/self/video_include/src/backend/agent/runtime/assistant_runtime.py)。
- 工具批处理、上下文推进、终态收口已拆到 [tool_loop.py](/E:/gittools/self/video_include/src/backend/agent/runtime/tool_loop.py)，不再混在 `service.py` 主循环里。
- routed path 已经提升到 `run_with_context(...) / stream_with_context(...)` 入口层，而不是只在 planning loop 内部偷偷试探。
- `save_note` 现在也走事件驱动链，而不是让旧 planner 先解释、再生成、再保存。
- `series_locate` 现在也走事件驱动链，而不是在“列视频后再回 planner 重新想下一步”。 

5. `#5 批量能力从 prompt / validation 下沉到 runtime`
状态：已完成
本批落地：
- `ToolDefinition` 已新增 `concurrency_safe` 元数据。
- 读取型业务工具已标记为 `concurrency_safe=True`。
- [tool_loop.py](/E:/gittools/self/video_include/src/backend/agent/runtime/tool_loop.py) 已按“连续可并发工具块”执行批处理，而不是简单串行逐个执行。
- 新增 [test_agent_runtime_batching.py](/E:/gittools/self/video_include/tests/test_agent_runtime_batching.py)。
- 新增 [run_series_batch_probe.py](/E:/gittools/self/video_include/scripts/run_series_batch_probe.py)。

6. `#6 内部运行态不再暴露为模型工具`
状态：已完成
本批落地：
- `runtime_internal` 工具已从模型可见工具面移除。
- 模型可见工具目录只展示 `business_read / ui_action`。
- 旧 planner 时代的 `tool_name` 约束已经收紧为模型可见工具枚举，不再暴露内部工具名。
- 当前模型上下文视图不再直接暴露 `candidate_buffer / inspected_video_ids / rejected_video_ids / inspection_stage`。

7. `#7 证据获取路径从模型决定改成代码策略决定`
状态：已完成
本批落地：
- `list_series_videos` 执行后，运行时会自动把 series 上下文推进到内容核验阶段。
- 这使系列问题后续可以直接进入 `get_video_summary / get_video_transcript`，而不再依赖模型去操作内部候选缓冲区工具。
- 对于 `series_answer`，运行时现在会默认走 `list_series_videos -> 批量 get_video_summary -> lightweight answerer` 的 summary-first 主干。
- 这条主干已经不再依赖模型在第二轮手工拼出所有 `get_video_summary` 调用。
- 新增 [video_evidence_selector.py](/E:/gittools/self/video_include/src/backend/agent/runtime/video_evidence_selector.py)，将 `video` 问答首轮分成 `summary / transcript / fallback`。
- 新增 [series_evidence_selector.py](/E:/gittools/self/video_include/src/backend/agent/runtime/series_evidence_selector.py)，将 `series` 问答首轮分成 `summary / fallback`。
- 已新增会话级证据缓存复用，后一轮问答会优先复用已读 `summary / transcript / series list`，而不是重复执行同类读取工具。
- 新增 [test_video_evidence_selector.py](/E:/gittools/self/video_include/tests/test_video_evidence_selector.py) 与 [test_series_evidence_selector.py](/E:/gittools/self/video_include/tests/test_series_evidence_selector.py)。
- 新增 [run_video_evidence_selector_cases.py](/E:/gittools/self/video_include/scripts/run_video_evidence_selector_cases.py) 与 [run_series_evidence_selector_cases.py](/E:/gittools/self/video_include/scripts/run_series_evidence_selector_cases.py)。

8. `#8 Provider 抽象升级为 adapter 层`
状态：已完成
本批落地：
- Agent provider 入口已从 `openai SDK` 直绑切到 LiteLLM adapter。
- 新增 [LiteLLMChatGateway](/E:/gittools/self/video_include/src/backend/agent/infrastructure/chat_gateway.py)。
- [bootstrap.py](/E:/gittools/self/video_include/src/backend/api/bootstrap.py) 已改为通过 provider 配置组装该 gateway。
- `AgentContextBudgetService` 已与 gateway 实例化解耦，避免预算检查被 provider 初始化耦合。
- [requirements.txt](/E:/gittools/self/video_include/requirements.txt) 已固定 `litellm==1.74.0`。

9. `#9 工具面分层：业务读取 / UI 动作 / 内部状态`
状态：已完成
本批落地：
- [ToolDefinition](/E:/gittools/self/video_include/src/backend/agent/schemas/tool_calls.py) 新增 `plane` 元数据。
- 工具目录已按 `BUSINESS_READ / UI_ACTION / RUNTIME_INTERNAL` 拆分。
- 新增 [test_agent_tool_catalog.py](/E:/gittools/self/video_include/tests/test_agent_tool_catalog.py)。
- 新增 [run_tool_catalog_dump.py](/E:/gittools/self/video_include/scripts/run_tool_catalog_dump.py) 用于直接导出当前工具面。

10. `#10 Prompt 缩减与稳定前缀化`
状态：已完成
本批落地：
- 旧 prompt 协议文件已删除，当前系统 prompt 已收敛到 router / routed answerer / note_drafter / locator 等仍在 runtime 中使用的最小集合。
- 大证据不再整包塞进回答 prompt，而是先经过 `PromptProjectionService` 投影后再注入。
- tool catalog 渲染已只保留模型可见工具。
- 新增 [test_agent_prompt_contract.py](/E:/gittools/self/video_include/tests/test_agent_prompt_contract.py)。
- 新增 [run_prompt_size_report.py](/E:/gittools/self/video_include/scripts/run_prompt_size_report.py)。

11. `#11 流式体验从“展示思考”改成“展示执行”`
状态：已完成
本批落地：
- 走新主路径的请求不会产生旧 planner 的 `thinking_delta` 流，而是更快进入 `tool_started / tool_completed`。
- `thinking` 仍默认保留发送，但常见内容问答的流式主体验已经开始向执行事件倾斜。
- routed path 的流式事件已经是“短 thinking + 直接执行 + 最终回答”的形态。
- 明确动作类 routed path 已能在执行完成后直接返回确定性回复，不再额外进入 responder 生成阶段。
- `video_seek` 现在也走执行导向流式：`thinking -> get_video_transcript -> video_seek -> answer`。
- `save_note` 现在也走执行导向流式：`thinking -> get_video_summary -> save_note -> answer`。
- `open_mindmap / open_overview` 在缺失内容时，现在也走执行导向流式：`thinking -> generate_* -> open_* -> answer`。

12. `#12 建立自动化回归体系，减少手动网页测试`
状态：已完成
本批落地：
- 新增 [test_litellm_chat_gateway.py](/E:/gittools/self/video_include/tests/test_litellm_chat_gateway.py)。
- 新增 [run_agent_provider_probe.py](/E:/gittools/self/video_include/scripts/run_agent_provider_probe.py)。
- 新增 [run_assistant_regressions.py](/E:/gittools/self/video_include/scripts/run_assistant_regressions.py)，支持 `--fake / --live / --providers / --cases`。
- [run_backend_tests.py](/E:/gittools/self/video_include/scripts/run_backend_tests.py) 已纳入新的 provider 单测。
- 已形成 “单元测试 + fake 脚本 + live 脚本入口” 的统一回归骨架。
- 已补齐 [tests/__init__.py](/E:/gittools/self/video_include/tests/__init__.py)，修复 [run_backend_tests.py](/E:/gittools/self/video_include/scripts/run_backend_tests.py) 以 `tests.*` 方式执行时的导入问题。

13. `#13 文档与实现重新对齐`
状态：已完成
本批落地：
- [architecture.md](/E:/gittools/self/video_include/docs/architecture.md) 已补充 LiteLLM adapter、tool plane、runtime/lane 主路径等现状说明。
- [agent-tool-chain-design.md](/E:/gittools/self/video_include/docs/agent-tool-chain-design.md) 已补充当前 plane 分层和过渡态边界。
- [agent-runtime-progress.md](/E:/gittools/self/video_include/docs/plan/agent-runtime-progress.md) 已同步反映 planner/responder 删除与 lane 拆分现状。

14. `#14 系统目标从“解释链路”改成“尽快完成任务”`
状态：已完成
本批落地：
- 已新增可直接观测批量并发效果的 [run_series_batch_probe.py](/E:/gittools/self/video_include/scripts/run_series_batch_probe.py)。
- 当前 probe 结果已能输出 `duration_seconds` 与 `max_concurrency`，用于验证批量读取是否真正并发。
- 明确动作类 routed path 现在会直接返回确定性回复，减少不必要的额外模型调用。
- 已新增 live 仿真脚本 [run_agent_routed_live_cases.py](/E:/gittools/self/video_include/scripts/run_agent_routed_live_cases.py)，用于主观评估 routed path 是否符合预期。
- live 仿真已确认 `video_seek` 路径能直接完成动作，不再只做“读 transcript 后文字回答”。 
- live 仿真已确认 `save_note` 路径能直接完成“读证据 -> 整理笔记 -> 保存笔记”，不再经过旧 planner-first 回路。
- 常见 summary 型 routed QA 已开始使用 lightweight answerer，减少不必要的回答层上下文负载。 
- live 仿真已确认 `series_locate` 路径能直接完成“批量读 summary -> 选候选视频 -> 读 transcript -> 回答定位结果”。 
- live 样本已确认：当视频缺少 mindmap 时，`打开思维导图` 会直接触发 `generate_mindmap -> open_mindmap`，而不是只打开空页面。 
- [run_provider_trace.py](/E:/gittools/self/video_include/scripts/run_provider_trace.py) 已确认 `series-locate` 当前实际只触发 `router + series_locator + routed_answerer` 3 次模型调用，没有 `planner` / `responder` 介入。
- Agent 上下文窗口默认值已调整为 `1_000_000`，并通过 [settings.toml](/E:/gittools/self/video_include/config/settings.toml) 的 `agent_context` 配置段统一管理。
- [compact.py](/E:/gittools/self/video_include/src/backend/agent/context/compact.py) 已不再使用固定 `12_000` token 作为压缩线，而是从上下文窗口和压缩比例推导阈值。
- 已新增 [run_semantic_compaction_probe.py](/E:/gittools/self/video_include/scripts/run_semantic_compaction_probe.py)，并实际完成一次“大量历史消息 -> 单次语义压缩”仿真，压缩结果主观可读、保留了用户目标、已确认事实、待继续事项与约束。

## 2.1 剩余重点

如果明天继续推进，建议优先顺序如下：

1. 继续压缩 `#2 / #4`
已完成，后续不再作为重点。

2. 继续压缩 `#3`
已完成，后续不再作为重点。

3. 补强 `#5 / #11 / #14`
已完成，后续只做细节优化。

4. 最后再处理 `#1`
等主路径稳定后，再把产品重心回归业务工作台的文档、目录和命名彻底对齐，否则容易一边迁路径、一边又被旧命名误导回去。

## 3. 本轮已落地但不单独计为完成项的修正

- 已撤回字符匹配式命令路由实验，不把补丁式意图识别留在主干代码中。

## 4. 本轮验证

已执行：

- `python .\scripts\run_backend_tests.py agent`
- `python .\scripts\run_backend_tests.py api`
- `python .\scripts\run_agent_provider_probe.py`
- `python .\scripts\run_tool_catalog_dump.py`
- `python .\scripts\run_prompt_size_report.py`
- `python .\scripts\run_evidence_policy_cases.py`
- `python .\scripts\run_series_batch_probe.py`
- `python .\scripts\run_video_evidence_selector_cases.py`
- `python .\scripts\run_series_evidence_selector_cases.py`
- `python .\scripts\run_request_router_cases.py`
- `.\.venv\Scripts\python.exe .\scripts\run_agent_routed_live_cases.py`
- `.\.venv\Scripts\python.exe .\scripts\run_agent_routed_live_cases.py --cases series-summary video-summary save-note`
- `.\.venv\Scripts\python.exe .\scripts\run_agent_routed_live_cases.py --cases series-locate`
- `.\.venv\Scripts\python.exe .\scripts\run_agent_manual_cases.py --manual --cases video-seek --skip-budget --skip-recovery`
- `.\.venv\Scripts\python.exe .\tests\test_request_router.py`
- `.\.venv\Scripts\python.exe .\tests\test_agent_save_note_route.py`
- `.\.venv\Scripts\python.exe .\tests\test_agent_routed_answerer.py`
- `.\.venv\Scripts\python.exe .\tests\test_series_locator.py`
- `.\.venv\Scripts\python.exe .\tests\test_agent_series_locate_route.py`
- `.\.venv\Scripts\python.exe .\tests\test_agent_direct_action_response.py`
- `.\.venv\Scripts\python.exe .\scripts\run_backend_tests.py agent`
- `.\.venv\Scripts\python.exe -`（单次 live 样本：`打开思维导图`，命中 `generate_mindmap -> open_mindmap`）
- `.\.venv\Scripts\python.exe .\scripts\run_runtime_trace.py --case series-summary`
- `.\.venv\Scripts\python.exe .\scripts\run_provider_trace.py --case series-locate`
- `.\.venv\Scripts\python.exe .\tests\test_prompt_projection.py`
- `.\.venv\Scripts\python.exe .\scripts\run_semantic_compaction_probe.py --turns 60 --window-tokens 12000`
- `.\.venv\Scripts\python.exe .\tests\test_agent_evidence_cache.py`
- `.\.venv\Scripts\python.exe .\scripts\run_evidence_cache_probe.py --case series-entity-after-summary`
- `python .\scripts\run_assistant_regressions.py --mode fake`
- `python .\scripts\run_assistant_regressions.py --fake --providers openai_compatible --skip-tests`
- `python .\scripts\run_assistant_regressions.py --fake --providers openai_compatible`
- `python .\scripts\run_assistant_regressions.py --fake --providers openai_compatible --skip-tests --skip-provider --skip-tool-catalog --skip-prompt-report --skip-evidence-policy`
- `.\.venv\Scripts\python.exe .\scripts\run_agent_provider_probe.py`
- `.\.venv\Scripts\python.exe -c "from litellm import completion; print('litellm-import-ok')"`
