# DSPy Decompose Variants Draft

## Notes

- 这份文件用于人工审查 `decompose` 的任务拆分样例。
- 为了便于审阅，任务数组都保持紧凑 JSON。
- 这批变体主要考察：
  - 单任务识别
  - 复合动作链
  - locate + action 组合
  - compare 后续任务
  - 状态查询后动作

## Variant Samples

| id | scope | user_message | tasks_json |
| --- | --- | --- | --- |
| dvar-001 | video | `给我概括一下这节视频。` | `[{"task_id":"task-1","instruction":"概括当前视频主要内容","depends_on":[],"kind_hint":"understand"}]` |
| dvar-002 | video | `快速总结这节的重点。` | `[{"task_id":"task-1","instruction":"概括当前视频的重点","depends_on":[],"kind_hint":"understand"}]` |
| dvar-003 | video | `这段视频大意是什么？` | `[{"task_id":"task-1","instruction":"概括当前视频主要内容","depends_on":[],"kind_hint":"understand"}]` |
| dvar-004 | video | `AK 是在哪一段提到的？` | `[{"task_id":"task-1","instruction":"定位视频里提到 AK 的位置","depends_on":[],"kind_hint":"locate"}]` |
| dvar-005 | video | `帮我找出白名单那一段。` | `[{"task_id":"task-1","instruction":"定位视频里讲白名单配置的片段","depends_on":[],"kind_hint":"locate"}]` |
| dvar-006 | video | `原话里怎么说的？` | `[{"task_id":"task-1","instruction":"定位并提取当前视频相关原话","depends_on":[],"kind_hint":"locate"}]` |
| dvar-007 | video | `这个视频目前有哪些工具已经生成了？` | `[{"task_id":"task-1","instruction":"读取当前视频的工具状态","depends_on":[],"kind_hint":"meta_state"}]` |
| dvar-008 | video | `导图和知识卡片现在是什么状态？` | `[{"task_id":"task-1","instruction":"读取当前视频的工具状态","depends_on":[],"kind_hint":"meta_state"}]` |
| dvar-009 | video | `打开概况页面。` | `[{"task_id":"task-1","instruction":"打开概况工具","depends_on":[],"kind_hint":"action"}]` |
| dvar-010 | video | `切到笔记页。` | `[{"task_id":"task-1","instruction":"打开笔记工具","depends_on":[],"kind_hint":"action"}]` |
| dvar-011 | video | `帮我打开思维导图。` | `[{"task_id":"task-1","instruction":"打开思维导图工具","depends_on":[],"kind_hint":"action"}]` |
| dvar-012 | video | `帮我记一下这一节的重点。` | `[{"task_id":"task-1","instruction":"概括当前视频的重点","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"把重点保存到笔记","depends_on":["task-1"],"kind_hint":"action"}]` |
| dvar-013 | video | `先总结重点，再记笔记。` | `[{"task_id":"task-1","instruction":"概括当前视频的重点","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"把总结保存到笔记","depends_on":["task-1"],"kind_hint":"action"}]` |
| dvar-014 | video | `先总结，再保存到笔记。` | `[{"task_id":"task-1","instruction":"概括当前视频主要内容","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"把总结保存到笔记","depends_on":["task-1"],"kind_hint":"action"}]` |
| dvar-015 | video | `先总结，再保存，再打开笔记。` | `[{"task_id":"task-1","instruction":"概括当前视频主要内容","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"把总结保存到笔记","depends_on":["task-1"],"kind_hint":"action"},{"task_id":"task-3","instruction":"打开笔记工具","depends_on":["task-2"],"kind_hint":"action"}]` |
| dvar-016 | video | `帮我总结一下并直接记进笔记，再打开让我看。` | `[{"task_id":"task-1","instruction":"概括当前视频的重点","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"把总结保存到笔记","depends_on":["task-1"],"kind_hint":"action"},{"task_id":"task-3","instruction":"打开笔记工具","depends_on":["task-2"],"kind_hint":"action"}]` |
| dvar-017 | video | `找到 AK 的位置并跳过去。` | `[{"task_id":"task-1","instruction":"定位视频里提到 AK 的位置","depends_on":[],"kind_hint":"locate"},{"task_id":"task-2","instruction":"跳到刚才定位到的视频位置","depends_on":["task-1"],"kind_hint":"action"}]` |
| dvar-018 | video | `先找出讲 AK 的地方，再直接跳到那里。` | `[{"task_id":"task-1","instruction":"定位视频里讲 AK 的位置","depends_on":[],"kind_hint":"locate"},{"task_id":"task-2","instruction":"跳到刚才定位到的视频位置","depends_on":["task-1"],"kind_hint":"action"}]` |
| dvar-019 | video | `找到提到 AK 的地方，跳过去，并解释那段内容。` | `[{"task_id":"task-1","instruction":"定位视频里提到 AK 的位置","depends_on":[],"kind_hint":"locate"},{"task_id":"task-2","instruction":"跳到刚才定位到的视频位置","depends_on":["task-1"],"kind_hint":"action"},{"task_id":"task-3","instruction":"解释刚才定位到的那段内容","depends_on":["task-1"],"kind_hint":"understand"}]` |
| dvar-020 | video | `先找位置，再跳转，再告诉我那段在讲什么。` | `[{"task_id":"task-1","instruction":"定位当前视频相关内容的位置","depends_on":[],"kind_hint":"locate"},{"task_id":"task-2","instruction":"跳到刚才定位到的视频位置","depends_on":["task-1"],"kind_hint":"action"},{"task_id":"task-3","instruction":"解释刚才定位到的那段内容","depends_on":["task-1"],"kind_hint":"understand"}]` |
| dvar-021 | video | `先看看有哪些工具已经生成了，再打开概况。` | `[{"task_id":"task-1","instruction":"读取当前视频的工具状态","depends_on":[],"kind_hint":"meta_state"},{"task_id":"task-2","instruction":"打开概况工具","depends_on":[],"kind_hint":"action"}]` |
| dvar-022 | video | `先检查导图状态，再打开导图。` | `[{"task_id":"task-1","instruction":"读取当前视频的工具状态","depends_on":[],"kind_hint":"meta_state"},{"task_id":"task-2","instruction":"打开思维导图工具","depends_on":[],"kind_hint":"action"}]` |
| dvar-023 | video | `先看看笔记可不可用，再打开笔记。` | `[{"task_id":"task-1","instruction":"读取当前视频的工具状态","depends_on":[],"kind_hint":"meta_state"},{"task_id":"task-2","instruction":"打开笔记工具","depends_on":[],"kind_hint":"action"}]` |
| dvar-024 | series | `帮我概括整个系列。` | `[{"task_id":"task-1","instruction":"概括整个系列的主要内容","depends_on":[],"kind_hint":"understand"}]` |
| dvar-025 | series | `这个系列的主线是什么？` | `[{"task_id":"task-1","instruction":"概括整个系列的主线","depends_on":[],"kind_hint":"understand"}]` |
| dvar-026 | series | `这个系列里哪里讲过 Nacos 3？` | `[{"task_id":"task-1","instruction":"定位系列里提到 Nacos 3 的位置","depends_on":[],"kind_hint":"locate"}]` |
| dvar-027 | series | `哪一节在讲 A2A 通信协议？` | `[{"task_id":"task-1","instruction":"定位系列里讲 A2A 通信协议的章节","depends_on":[],"kind_hint":"locate"}]` |
| dvar-028 | series | `帮我找出讲智能体卡片的地方。` | `[{"task_id":"task-1","instruction":"定位系列里讲智能体卡片的内容","depends_on":[],"kind_hint":"locate"}]` |
| dvar-029 | series | `比较一下百度地图 API Key 和 Nacos 3 的作用。` | `[{"task_id":"task-1","instruction":"比较百度地图 API Key 与 Nacos 3 在课程中的作用","depends_on":[],"kind_hint":"compare"}]` |
| dvar-030 | series | `Jmanus 和 AgentScope 的定位有什么不同？` | `[{"task_id":"task-1","instruction":"比较 Jmanus 和 AgentScope 在系列中的定位差异","depends_on":[],"kind_hint":"compare"}]` |
| dvar-031 | series | `先比较 Jmanus 和 AgentScope，再总结哪个更适合当前场景。` | `[{"task_id":"task-1","instruction":"比较 Jmanus 和 AgentScope 的差异","depends_on":[],"kind_hint":"compare"},{"task_id":"task-2","instruction":"基于比较结果总结哪个更适合当前场景","depends_on":["task-1"],"kind_hint":"understand"}]` |
| dvar-032 | series | `先对比这两个框架，再给我一个结论。` | `[{"task_id":"task-1","instruction":"比较两个框架的差异","depends_on":[],"kind_hint":"compare"},{"task_id":"task-2","instruction":"基于比较结果给出结论","depends_on":["task-1"],"kind_hint":"understand"}]` |
| dvar-033 | series | `先说系列结构，再定位 Nacos 3 在哪一节。` | `[{"task_id":"task-1","instruction":"概括整个系列的结构","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"定位系列里提到 Nacos 3 的位置","depends_on":[],"kind_hint":"locate"}]` |
| dvar-034 | series | `先整体介绍一下课程，再告诉我哪节讲 Nacos 3。` | `[{"task_id":"task-1","instruction":"概括整个系列的主要内容","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"定位系列里提到 Nacos 3 的位置","depends_on":[],"kind_hint":"locate"}]` |
| dvar-035 | video | `先总结视频重点，再定位 AK 那段。` | `[{"task_id":"task-1","instruction":"概括当前视频的重点","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"定位视频里提到 AK 的位置","depends_on":["task-1"],"kind_hint":"locate"}]` |
| dvar-036 | video | `先说这节主要讲什么，再帮我跳到 AK 那段。` | `[{"task_id":"task-1","instruction":"概括当前视频主要内容","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"定位视频里提到 AK 的位置","depends_on":["task-1"],"kind_hint":"locate"},{"task_id":"task-3","instruction":"跳到刚才定位到的视频位置","depends_on":["task-2"],"kind_hint":"action"}]` |
| dvar-037 | video | `先查资源状态，再决定要不要打开概况。` | `[{"task_id":"task-1","instruction":"读取当前视频的工具状态","depends_on":[],"kind_hint":"meta_state"},{"task_id":"task-2","instruction":"打开概况工具","depends_on":[],"kind_hint":"action"}]` |
| dvar-038 | video | `帮我总结重点，记到笔记，再打开概况。` | `[{"task_id":"task-1","instruction":"概括当前视频的重点","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"把总结保存到笔记","depends_on":["task-1"],"kind_hint":"action"},{"task_id":"task-3","instruction":"打开概况工具","depends_on":["task-2"],"kind_hint":"action"}]` |
| dvar-039 | series | `先比较百度地图 API Key 和 Nacos 3，再把结论记下来。` | `[{"task_id":"task-1","instruction":"比较百度地图 API Key 与 Nacos 3 在课程中的作用和关系","depends_on":[],"kind_hint":"compare"},{"task_id":"task-2","instruction":"把比较结论保存到笔记","depends_on":["task-1"],"kind_hint":"action"}]` |
| dvar-040 | video | `打开概况，然后打开笔记。` | `[{"task_id":"task-1","instruction":"打开概况工具","depends_on":[],"kind_hint":"action"},{"task_id":"task-2","instruction":"打开笔记工具","depends_on":[],"kind_hint":"action"}]` |
| dvar-041 | video | `先定位提到 AK 的地方，再跳过去，再解释那段，最后记到笔记。` | `[{"task_id":"task-1","instruction":"定位视频里提到 AK 的位置","depends_on":[],"kind_hint":"locate"},{"task_id":"task-2","instruction":"跳到刚才定位到的视频位置","depends_on":["task-1"],"kind_hint":"action"},{"task_id":"task-3","instruction":"解释刚才定位到的那段内容","depends_on":["task-1"],"kind_hint":"understand"},{"task_id":"task-4","instruction":"把解释保存到笔记","depends_on":["task-3"],"kind_hint":"action"}]` |
| dvar-042 | video | `先找出讲白名单的地方，再帮我跳过去，并总结那段内容。` | `[{"task_id":"task-1","instruction":"定位视频里讲白名单配置的片段","depends_on":[],"kind_hint":"locate"},{"task_id":"task-2","instruction":"跳到刚才定位到的视频位置","depends_on":["task-1"],"kind_hint":"action"},{"task_id":"task-3","instruction":"解释刚才定位到的那段内容","depends_on":["task-1"],"kind_hint":"understand"}]` |
| dvar-043 | series | `先比较 Jmanus 和 AgentScope，再总结哪个更适合当前场景，最后把结论存成笔记。` | `[{"task_id":"task-1","instruction":"比较 Jmanus 和 AgentScope 的差异","depends_on":[],"kind_hint":"compare"},{"task_id":"task-2","instruction":"基于比较结果总结哪个更适合当前场景","depends_on":["task-1"],"kind_hint":"understand"},{"task_id":"task-3","instruction":"把总结结论保存到笔记","depends_on":["task-2"],"kind_hint":"action"}]` |
| dvar-044 | series | `先概括整个系列，再找 Nacos 3 在哪一节，再解释它的作用。` | `[{"task_id":"task-1","instruction":"概括整个系列的主要内容","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"定位系列里提到 Nacos 3 的位置","depends_on":[],"kind_hint":"locate"},{"task_id":"task-3","instruction":"解释 Nacos 3 在课程里的作用","depends_on":["task-2"],"kind_hint":"understand"}]` |
| dvar-045 | series | `先整体介绍课程结构，再定位讲 A2A 的部分，最后比较 A2A 和 MCP 的角色。` | `[{"task_id":"task-1","instruction":"概括整个系列的结构","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"定位系列里讲 A2A 通信协议的内容","depends_on":[],"kind_hint":"locate"},{"task_id":"task-3","instruction":"比较 A2A 和 MCP 在课程里的角色","depends_on":["task-2"],"kind_hint":"compare"}]` |
