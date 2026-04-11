# DSPy Classifier Variants Draft

## Notes

- 这份文件用于人工审查分类样例扩写质量。
- 为了便于审阅，变体只保留最关键字段：
  - `scope`
  - `user_message`
  - `goal`
  - `target_source`
  - `context_need`
  - `action_name`
- 默认系列为 `agent-frameworks`。
- 默认视频为 `1-4 准备工作：百度地图API秘钥(AK)`，除非语义明显是 `series`。

| id | scope | user_message | goal | target_source | context_need | action_name |
| --- | --- | --- | --- | --- | --- | --- |
| var-001 | video | 给我一句话总结这节视频。 | understand | summary | chunk |  |
| var-002 | video | 这节视频到底在讲什么内容？ | understand | summary | chunk |  |
| var-003 | video | 快速概括一下这一节。 | understand | summary | chunk |  |
| var-004 | video | 这一节的重点主线是什么？ | understand | summary | chunk |  |
| var-005 | video | 用简短一点的话介绍这节视频。 | understand | summary | chunk |  |
| var-006 | video | 这节课主要解决了什么？ | understand | summary | chunk |  |
| var-007 | video | 这一节最重要的结论是什么？ | understand | summary | chunk |  |
| var-008 | video | 帮我提炼这节的核心 takeaway。 | understand | summary | chunk |  |
| var-009 | video | 总结一下这一节想让我记住什么。 | understand | summary | chunk |  |
| var-010 | video | 它在后续项目里的作用是什么？ | understand | summary | chunk |  |
| var-011 | video | 为什么要先做这一节？ | understand | summary | chunk |  |
| var-012 | video | 这一节在整个课程里算什么定位？ | understand | summary | chunk |  |
| var-013 | video | 如果只看一句总结，这一节应该怎么说？ | understand | summary | chunk |  |
| var-014 | video | 提炼一下这节的主要信息。 | understand | summary | chunk |  |
| var-015 | video | 这节视频的大意是什么？ | understand | summary | chunk |  |
| var-016 | video | AK 是在哪一段提到的？ | locate | transcript | chunk |  |
| var-017 | video | 帮我定位提到 API Key 的位置。 | locate | transcript | chunk |  |
| var-018 | video | 哪里讲到了白名单配置？ | locate | transcript | chunk |  |
| var-019 | video | 给我找出说 0.0.0.0/0 的地方。 | locate | transcript | chunk |  |
| var-020 | video | 视频中哪一段在讲白名单？ | locate | transcript | chunk |  |
| var-021 | video | 原话里提到 AK 的那段完整上下文给我看看。 | locate | transcript | continuous |  |
| var-022 | video | 把讲百度地图开放平台的那一段找出来。 | locate | transcript | chunk |  |
| var-023 | video | 这一节哪里说了服务端应用类型？ | locate | transcript | chunk |  |
| var-024 | video | 视频哪个位置开始解释申请 AK？ | locate | transcript | chunk |  |
| var-025 | video | 把提到配置白名单的前后一段完整说一下。 | locate | transcript | continuous |  |
| var-026 | video | 哪句原话解释了为什么后续项目要用 AK？ | locate | transcript | continuous |  |
| var-027 | video | 给我精确定位讲 API Key 的片段。 | locate | transcript | chunk |  |
| var-028 | video | 这个视频里提到百度地图控制台是在什么位置？ | locate | transcript | chunk |  |
| var-029 | video | 把讲如何创建应用的那段找给我。 | locate | transcript | chunk |  |
| var-030 | video | 这一段完整上下文里是怎么介绍 0.0.0.0/0 的？ | locate | transcript | continuous |  |
| var-031 | video | 这一节哪一段在讲申请 AK 的步骤？ | locate | transcript | chunk |  |
| var-032 | video | 帮我找出介绍白名单用途的原话。 | locate | transcript | continuous |  |
| var-033 | video | 哪一段在说基础 API 可以全选？ | locate | transcript | chunk |  |
| var-034 | video | 把说个人身份申请不了高级服务 API 的上下文拿出来。 | locate | transcript | continuous |  |
| var-035 | video | 这一节里哪里提到后面的项目会用到百度地图 API？ | locate | transcript | chunk |  |
| var-036 | video | 这个视频目前可用的工具有哪些？ | meta_state | all | chunk |  |
| var-037 | video | 导图现在生成好了没有？ | meta_state | all | chunk |  |
| var-038 | video | 概况、导图、知识卡片分别是什么状态？ | meta_state | all | chunk |  |
| var-039 | video | 这个视频有没有已经生成知识卡片？ | meta_state | all | chunk |  |
| var-040 | video | 笔记工具现在可用吗？ | meta_state | all | chunk |  |
| var-041 | video | 视频预览是不是 ready 了？ | meta_state | all | chunk |  |
| var-042 | video | 这节课的资源状态给我列一下。 | meta_state | all | chunk |  |
| var-043 | video | 现在有哪些内容已经处理完成了？ | meta_state | all | chunk |  |
| var-044 | video | AI 概况是不是已经有了？ | meta_state | all | chunk |  |
| var-045 | video | 工具面板里哪个是 blocked，哪个是 ready？ | meta_state | all | chunk |  |
| var-046 | video | 思维导图和知识卡片现在能不能打开？ | meta_state | all | chunk |  |
| var-047 | video | 这个视频的处理资源状态帮我检查一下。 | meta_state | all | chunk |  |
| var-048 | video | 生成进度现在到什么程度了？ | meta_state | all | chunk |  |
| var-049 | video | 有哪些工具 available 但还没生成？ | meta_state | all | chunk |  |
| var-050 | video | 导图、笔记、预览这几个资源的状态分别告诉我。 | meta_state | all | chunk |  |
| var-051 | video | 打开概况页面。 | action | all | chunk | open_overview |
| var-052 | video | 切到概况工具。 | action | all | chunk | open_overview |
| var-053 | video | 帮我打开概况。 | action | all | chunk | open_overview |
| var-054 | video | 打开思维导图。 | action | all | chunk | open_mindmap |
| var-055 | video | 切到导图工具。 | action | all | chunk | open_mindmap |
| var-056 | video | 打开笔记。 | action | all | chunk | open_notes |
| var-057 | video | 切换到笔记页。 | action | all | chunk | open_notes |
| var-058 | video | 打开视频预览。 | action | all | chunk | open_video |
| var-059 | video | 切到视频工具。 | action | all | chunk | open_video |
| var-060 | video | 记一条笔记。 | action | all | chunk | save_note |
| var-061 | video | 帮我保存一下重点到笔记。 | action | all | chunk | save_note |
| var-062 | video | 把这段结论记下来。 | action | all | chunk | save_note |
| var-063 | video | 跳到刚才提到 AK 的位置。 | action | all | chunk | video_seek |
| var-064 | video | 帮我直接定位到相关时间点。 | action | all | chunk | video_seek |
| var-065 | video | 生成概况。 | action | all | chunk | generate_overview |
| var-066 | video | 把概况生成出来。 | action | all | chunk | generate_overview |
| var-067 | video | 生成思维导图。 | action | all | chunk | generate_mindmap |
| var-068 | video | 把导图做出来。 | action | all | chunk | generate_mindmap |
| var-069 | video | 帮我打开概况并继续看。 | action | all | chunk | open_overview |
| var-070 | video | 我想看视频本体。 | action | all | chunk | open_video |
| var-071 | series | 这个系列的主要内容是什么？ | understand | summary | chunk |  |
| var-072 | series | 帮我概括整个课程。 | understand | summary | chunk |  |
| var-073 | series | 这一套课都讲了些什么？ | understand | summary | chunk |  |
| var-074 | series | 整个系列的学习路径怎么安排？ | understand | summary | chunk |  |
| var-075 | series | 按章节看，这个系列的主线是什么？ | understand | summary | chunk |  |
| var-076 | series | 这个系列整体在解决什么问题？ | understand | summary | chunk |  |
| var-077 | series | 课程结构大概分几部分？ | understand | summary | chunk |  |
| var-078 | series | 这一整套内容的重点模块有哪些？ | understand | summary | chunk |  |
| var-079 | series | 我想先了解系列全貌。 | understand | summary | chunk |  |
| var-080 | series | 整体上这个系列在教什么？ | understand | summary | chunk |  |
| var-081 | series | 哪一节讲了 Nacos 3？ | locate | transcript | chunk |  |
| var-082 | series | 整个系列里哪一段提到了 Nacos 3？ | locate | transcript | chunk |  |
| var-083 | series | 帮我定位讲 MCP 管理的章节。 | locate | transcript | chunk |  |
| var-084 | series | 这个系列里哪里解释了 Agent 管理？ | locate | transcript | chunk |  |
| var-085 | series | 哪一节在说智能体卡片？ | locate | transcript | chunk |  |
| var-086 | series | A2A 通信协议是在系列的哪个位置讲的？ | locate | transcript | chunk |  |
| var-087 | series | 找出讲服务发现的那一节。 | locate | transcript | chunk |  |
| var-088 | series | 把提到 Nacos 3 的上下文找出来。 | locate | transcript | continuous |  |
| var-089 | series | 哪一段完整讲了智能体卡片和 Nacos 的关系？ | locate | transcript | continuous |  |
| var-090 | series | 我想知道这个系列里哪一节讲了 ReAct。 | locate | transcript | chunk |  |
| var-091 | series | 百度地图 API Key 和 Nacos 3 分别是什么作用？ | compare | all | chunk |  |
| var-092 | series | Jmanus 和 AgentScope 的定位有什么不同？ | compare | all | chunk |  |
| var-093 | series | A2A 和 MCP 在课程里各自扮演什么角色？ | compare | all | chunk |  |
| var-094 | series | 百度地图 AK 这一节和阿里百炼 API Key 这一节之间是什么关系？ | compare | all | chunk |  |
| var-095 | series | Jmanus、AgentScope 这两个框架分别解决什么问题？ | compare | all | chunk |  |
| var-096 | series | 比较一下 Nacos 3 和百度地图 API Key 在课程里的层次差异。 | compare | all | chunk |  |
| var-097 | series | AgentScope 和 Jmanus 哪个更偏自主代理，哪个更偏框架体验？ | compare | all | chunk |  |
| var-098 | series | 对比一下 API Key、Nacos 3、Jmanus 这三节的课程作用。 | compare | all | chunk |  |
| var-099 | series | 这个视频讲的是 API Key，那后面哪一节最可能与它衔接？ | compare | all | chunk |  |
| var-100 | series | 百度地图 API Key 和 Nacos 3 这两节之间的联系是什么？ | compare | all | chunk |  |
