# DSPy Decompose Seeds Draft

## Task Schema

每个 task 结构：

```json
{
  "task_id": "task-1",
  "instruction": "要执行的单步任务",
  "depends_on": [],
  "kind_hint": "understand|locate|compare|meta_state|action"
}
```

设计原则：

- 尽量先拆“步骤”，不要在 decompose 阶段拆 compare 对象
- compare 对象的拆分由后续 `split_compare` 负责
- 只有后一步明确依赖前一步结果时，才加 `depends_on`
- 如果用户问题本身就是单任务，就只返回 1 个 task

## Seed Samples

| id | scope | user_message | tasks_json |
| --- | --- | --- | --- |
| dseed-001 | video | `这个视频主要讲了什么？` | `[{"task_id":"task-1","instruction":"概括当前视频主要内容","depends_on":[],"kind_hint":"understand"}]` |
| dseed-002 | video | `视频里哪里提到了 AK？` | `[{"task_id":"task-1","instruction":"定位视频里提到 AK 的位置","depends_on":[],"kind_hint":"locate"}]` |
| dseed-003 | video | `这个视频有哪些工具已经生成了？` | `[{"task_id":"task-1","instruction":"读取当前视频的工具状态","depends_on":[],"kind_hint":"meta_state"}]` |
| dseed-004 | video | `打开概况` | `[{"task_id":"task-1","instruction":"打开概况工具","depends_on":[],"kind_hint":"action"}]` |
| dseed-005 | video | `打开思维导图` | `[{"task_id":"task-1","instruction":"打开思维导图工具","depends_on":[],"kind_hint":"action"}]` |
| dseed-006 | video | `打开笔记` | `[{"task_id":"task-1","instruction":"打开笔记工具","depends_on":[],"kind_hint":"action"}]` |
| dseed-007 | video | `打开视频` | `[{"task_id":"task-1","instruction":"打开视频工具","depends_on":[],"kind_hint":"action"}]` |
| dseed-008 | video | `生成概况` | `[{"task_id":"task-1","instruction":"生成当前视频概况","depends_on":[],"kind_hint":"action"}]` |
| dseed-009 | video | `生成思维导图` | `[{"task_id":"task-1","instruction":"生成当前视频思维导图","depends_on":[],"kind_hint":"action"}]` |
| dseed-010 | video | `帮我记一下重点` | `[{"task_id":"task-1","instruction":"概括当前视频的重点","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"把重点保存到笔记","depends_on":["task-1"],"kind_hint":"action"}]` |
| dseed-011 | video | `先总结一下这节 API Key 的重点，再把总结保存到笔记里，然后打开笔记让我查阅。` | `[{"task_id":"task-1","instruction":"概括这节 API Key 视频的重点","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"把总结保存到笔记","depends_on":["task-1"],"kind_hint":"action"},{"task_id":"task-3","instruction":"打开笔记工具","depends_on":["task-2"],"kind_hint":"action"}]` |
| dseed-012 | video | `找到提到 AK 的地方，跳过去，并告诉我那段在讲什么。` | `[{"task_id":"task-1","instruction":"定位视频里提到 AK 的位置","depends_on":[],"kind_hint":"locate"},{"task_id":"task-2","instruction":"跳到刚才定位到的视频位置","depends_on":["task-1"],"kind_hint":"action"},{"task_id":"task-3","instruction":"解释刚才定位到的那段内容","depends_on":["task-1"],"kind_hint":"understand"}]` |
| dseed-013 | series | `这个系列主要讲了哪些主题？` | `[{"task_id":"task-1","instruction":"概括整个系列的主要主题","depends_on":[],"kind_hint":"understand"}]` |
| dseed-014 | series | `这个系列里哪里讲过 Nacos 3？` | `[{"task_id":"task-1","instruction":"定位系列里提到 Nacos 3 的位置","depends_on":[],"kind_hint":"locate"}]` |
| dseed-015 | series | `百度地图 API Key 这一节和 Nacos 3 这一节在整个课程中分别承担什么作用？它们之间是什么关系？` | `[{"task_id":"task-1","instruction":"比较百度地图 API Key 与 Nacos 3 在课程中的作用和关系","depends_on":[],"kind_hint":"compare"}]` |
| dseed-016 | series | `Jmanus 和 AgentScope 在整个系列里分别承担什么角色？` | `[{"task_id":"task-1","instruction":"比较 Jmanus 与 AgentScope 在整个系列中的角色","depends_on":[],"kind_hint":"compare"}]` |
| dseed-017 | series | `先比较 Jmanus 和 AgentScope 的差异，再帮我总结哪个更适合当前场景。` | `[{"task_id":"task-1","instruction":"比较 Jmanus 和 AgentScope 的差异","depends_on":[],"kind_hint":"compare"},{"task_id":"task-2","instruction":"基于比较结果总结哪个更适合当前场景","depends_on":["task-1"],"kind_hint":"understand"}]` |
| dseed-018 | video | `这个视频讲的是 API Key，那后面哪一节最可能与它衔接？` | `[{"task_id":"task-1","instruction":"判断当前视频内容与后续章节的衔接关系","depends_on":[],"kind_hint":"compare"}]` |
| dseed-019 | video | `先看看有哪些工具已经生成了，再打开概况。` | `[{"task_id":"task-1","instruction":"读取当前视频的工具状态","depends_on":[],"kind_hint":"meta_state"},{"task_id":"task-2","instruction":"打开概况工具","depends_on":[],"kind_hint":"action"}]` |
| dseed-020 | series | `先告诉我整个系列的结构，再定位哪一节讲了 Nacos 3。` | `[{"task_id":"task-1","instruction":"概括整个系列的结构","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"定位系列里提到 Nacos 3 的位置","depends_on":[],"kind_hint":"locate"}]` |
| dseed-021 | video | `先找出提到 AK 的位置，再跳过去，然后解释那一段，最后把解释保存到笔记。` | `[{"task_id":"task-1","instruction":"定位视频里提到 AK 的位置","depends_on":[],"kind_hint":"locate"},{"task_id":"task-2","instruction":"跳到刚才定位到的视频位置","depends_on":["task-1"],"kind_hint":"action"},{"task_id":"task-3","instruction":"解释刚才定位到的那段内容","depends_on":["task-1"],"kind_hint":"understand"},{"task_id":"task-4","instruction":"把解释保存到笔记","depends_on":["task-3"],"kind_hint":"action"}]` |
| dseed-022 | series | `先比较 Jmanus 和 AgentScope 的差异，再总结谁更适合当前场景，最后把结论记下来。` | `[{"task_id":"task-1","instruction":"比较 Jmanus 和 AgentScope 的差异","depends_on":[],"kind_hint":"compare"},{"task_id":"task-2","instruction":"基于比较结果总结谁更适合当前场景","depends_on":["task-1"],"kind_hint":"understand"},{"task_id":"task-3","instruction":"把总结结论保存到笔记","depends_on":["task-2"],"kind_hint":"action"}]` |
| dseed-023 | video | `先检查概况和导图的状态，如果都可用就打开概况，否则先生成概况。` | `[{"task_id":"task-1","instruction":"读取当前视频的工具状态","depends_on":[],"kind_hint":"meta_state"},{"task_id":"task-2","instruction":"根据工具状态决定打开概况还是生成概况","depends_on":["task-1"],"kind_hint":"action"}]` |
| dseed-024 | series | `先概括整个系列的结构，再定位 Nacos 3，接着解释它在课程里的作用，最后比较它和百度地图 API Key 的关系。` | `[{"task_id":"task-1","instruction":"概括整个系列的结构","depends_on":[],"kind_hint":"understand"},{"task_id":"task-2","instruction":"定位系列里提到 Nacos 3 的位置","depends_on":[],"kind_hint":"locate"},{"task_id":"task-3","instruction":"解释 Nacos 3 在课程里的作用","depends_on":["task-2"],"kind_hint":"understand"},{"task_id":"task-4","instruction":"比较 Nacos 3 和百度地图 API Key 在课程里的关系","depends_on":["task-3"],"kind_hint":"compare"}]` |
