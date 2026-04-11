# DSPy Classifier Seeds Draft

## Project Goal Summary

- 这是一个本地优先、BYOK 的视频知识工作台。
- 后端 agent 的核心任务是围绕 `video` 和 `series` 两种 scope 处理用户请求。
- 当前分类目标固定为：
  - `understand`
  - `locate`
  - `compare`
  - `meta_state`
  - `action`
- 分类输出需要进一步决定：
  - `target_source = summary | transcript | all`
  - `context_need = chunk | continuous`
  - `action_name`
  - `action_args`
- 关键约束：
  - 不依赖业务关键词硬编码
  - 不默认全文 transcript
  - `meta_state` 优先走结构化状态
  - `compare` 需要后续拆成 atomic queries

## Seed Samples

| id | source | scope | user_message | goal | target_source | context_need | action_name |
| --- | --- | --- | --- | --- | --- | --- | --- |
| seed-001 | `test_agent_graph_video_flow` | `video` | `这个视频主要讲了什么？` | `understand` | `summary` | `chunk` | `` |
| seed-002 | `test_agent_graph_video_flow` | `video` | `帮我概括一下这节视频的重点。` | `understand` | `summary` | `chunk` | `` |
| seed-003 | `project_goal` | `video` | `这节主要在解决什么问题？` | `understand` | `summary` | `chunk` | `` |
| seed-004 | `project_goal` | `video` | `这一节的核心结论有哪些？` | `understand` | `summary` | `chunk` | `` |
| seed-005 | `project_goal` | `video` | `这一节在整个准备工作里扮演什么角色？` | `understand` | `summary` | `chunk` | `` |
| seed-006 | `test_agent_graph_video_flow` | `video` | `视频里哪里提到了 AK？` | `locate` | `transcript` | `chunk` | `` |
| seed-007 | `subjective/video-quote-locate` | `video` | `视频里哪里提到了 0.0.0.0/0？那一段主要在讲什么？` | `locate` | `transcript` | `continuous` | `` |
| seed-008 | `project_goal` | `video` | `原话里是怎么说的？` | `locate` | `transcript` | `continuous` | `` |
| seed-009 | `project_goal` | `video` | `这段内容在视频哪个位置？` | `locate` | `transcript` | `chunk` | `` |
| seed-010 | `project_goal` | `video` | `把提到白名单配置的那一段找出来。` | `locate` | `transcript` | `chunk` | `` |
| seed-011 | `test_agent_graph_video_flow` | `video` | `这个视频有哪些工具已经生成了？` | `meta_state` | `all` | `chunk` | `` |
| seed-012 | `subjective/video-tool-status` | `video` | `这个 API Key 视频目前有哪些工具已生成？导图、知识卡片、笔记分别是什么状态？` | `meta_state` | `all` | `chunk` | `` |
| seed-013 | `project_goal` | `video` | `概况和思维导图现在生成了吗？` | `meta_state` | `all` | `chunk` | `` |
| seed-014 | `project_goal` | `video` | `这个视频处理到哪一步了？` | `meta_state` | `all` | `chunk` | `` |
| seed-015 | `test_agent_graph_actions` | `video` | `打开概况` | `action` | `all` | `chunk` | `open_overview` |
| seed-016 | `test_agent_graph_actions` | `video` | `帮我记一下重点` | `action` | `all` | `chunk` | `save_note` |
| seed-017 | `test_agent_graph_actions` | `video` | `跳到相关位置` | `action` | `all` | `chunk` | `video_seek` |
| seed-018 | `test_agent_direct_action_response` | `video` | `打开思维导图` | `action` | `all` | `chunk` | `open_mindmap` |
| seed-019 | `subjective/notes-workflow` | `video` | `打开笔记让我查阅` | `action` | `all` | `chunk` | `open_notes` |
| seed-020 | `project_goal` | `video` | `打开视频` | `action` | `all` | `chunk` | `open_video` |
| seed-021 | `test_agent_direct_action_response` | `video` | `生成概况` | `action` | `all` | `chunk` | `generate_overview` |
| seed-022 | `test_agent_graph_series_flow` | `series` | `这个系列主要讲了哪些主题？` | `understand` | `summary` | `chunk` | `` |
| seed-023 | `project_goal` | `series` | `整个课程的主线是什么？` | `understand` | `summary` | `chunk` | `` |
| seed-024 | `project_goal` | `series` | `这个系列的结构怎么安排的？` | `understand` | `summary` | `chunk` | `` |
| seed-025 | `subjective/series-concept-location` | `series` | `这个系列里哪里讲过 Nacos 3？最好指出是哪一节，如果能的话大致说明是在哪个位置或章节。` | `locate` | `transcript` | `chunk` | `` |
| seed-026 | `project_goal` | `series` | `整个系列里哪一节讲了 A2A 通信协议？` | `locate` | `transcript` | `chunk` | `` |
| seed-027 | `project_goal` | `series` | `这个系列里哪一段解释了智能体卡片？` | `locate` | `transcript` | `continuous` | `` |
| seed-028 | `subjective/series-relationship` | `series` | `百度地图 API Key 这一节和 Nacos 3 这一节在整个课程中分别承担什么作用？它们之间是什么关系？` | `compare` | `all` | `chunk` | `` |
| seed-029 | `project_goal` | `series` | `Jmanus 和 AgentScope 在整个系列里分别承担什么角色？` | `compare` | `all` | `chunk` | `` |
| seed-030 | `subjective/video-scope-boundary` | `video` | `当前这个视频讲的是 API Key，那后面哪一节最可能与它衔接？` | `compare` | `all` | `chunk` | `` |
