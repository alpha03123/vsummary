# DSPy Split Compare Seeds Draft

## Task

`split_compare` 的职责不是拆步骤，而是把一个 compare task 里的比较对象拆成 atomic queries。

要求：

- 输出 `queries`
- 每个 query 尽量短、可直接送入 retrieval
- 不要把整句问题原样返回
- 不要把关系句、比较句、结论句保留成 query

## Seed Samples

| id | user_message | queries_json |
| --- | --- | --- |
| cseed-001 | `百度地图 API Key 和 Nacos 3 在课程里分别承担什么作用？它们之间是什么关系？` | `["百度地图 API Key","Nacos 3"]` |
| cseed-002 | `Jmanus 和 AgentScope 的定位有什么不同？` | `["Jmanus","AgentScope"]` |
| cseed-003 | `A2A 和 MCP 在课程里各自扮演什么角色？` | `["A2A","MCP"]` |
| cseed-004 | `百度地图 AK 这一节和阿里百炼 API Key 这一节之间是什么关系？` | `["百度地图 AK","阿里百炼 API Key"]` |
| cseed-005 | `Jmanus、AgentScope 这两个框架分别解决什么问题？` | `["Jmanus","AgentScope"]` |
| cseed-006 | `比较一下 Nacos 3 和百度地图 API Key 在课程里的层次差异。` | `["Nacos 3","百度地图 API Key"]` |
| cseed-007 | `AgentScope 和 Jmanus 哪个更偏自主代理，哪个更偏框架体验？` | `["AgentScope","Jmanus"]` |
| cseed-008 | `对比一下 API Key、Nacos 3、Jmanus 这三节的课程作用。` | `["API Key","Nacos 3","Jmanus"]` |
| cseed-009 | `百度地图 API Key 和 Nacos 3 这两节之间的联系是什么？` | `["百度地图 API Key","Nacos 3"]` |
| cseed-010 | `Jmanus 和 AgentScope，哪个更适合当前场景？` | `["Jmanus","AgentScope"]` |
