# 架构说明

本文描述当前后端主架构，重点解释：

- 系统被分成哪些子系统
- 每个目录在架构中的职责
- 依赖方向如何流动
- 当前架构的优点、边界与待演进点

本文描述的是“现在的真实结构”，不是理想化蓝图。

## 1. 总体结构

当前后端由三个主要部分构成：

1. `video_summary`
2. `agent`
3. `api`

它们的角色分别是：

- `video_summary`：视频内容生产与工作区数据能力
- `agent`：面向 Studio 交互的意图理解、动作规划、工具执行与对话记忆
- `api`：FastAPI 交付层与依赖组装入口

这不是单一的大泥球，也不是完全统一的一套分层模板，而是“两个业务子系统 + 一个总装入口”。

## 2. 系统边界

### 2.1 `video_summary`

`video_summary` 是内容主域，负责两类能力：

- 生成链：从视频生成转写、摘要、导图、知识产物
- 工作区链：从 `workspace/<series>/<video>/` 中读取和维护 Studio 展示所需的数据

它是当前后端中最接近 Clean Architecture 的部分。

主要目录：

- `src/backend/video_summary/domain`
- `src/backend/video_summary/generation`
- `src/backend/video_summary/library`
- `src/backend/video_summary/infrastructure`

### 2.2 `agent`

`agent` 不是 `video_summary` 的上层包装，而是另一个独立子系统。

它的职责不是生产 summary/mindmap/notes 本身，而是：

- 读取当前工作区上下文
- 调用模型理解用户意图
- 生成动作计划
- 校验计划
- 执行工具动作
- 组织最终回复
- 维护会话记忆

主要目录：

- `src/backend/agent/agent`
- `src/backend/agent/infrastructure`
- `src/backend/agent/memory`
- `src/backend/agent/tools`
- `src/backend/agent/schemas`
- `src/backend/agent/validation`

### 2.3 `api`

`api` 是对外入口与 composition root。

它负责：

- 暴露 HTTP 接口
- 实例化 `video_summary` 用例
- 实例化 `agent` 服务
- 将两者接入 FastAPI

主要目录：

- `src/backend/api/app.py`
- `src/backend/api/bootstrap.py`

## 3. `video_summary` 内部结构

### 3.1 `domain`

路径：

- `src/backend/video_summary/domain/models.py`

这里放的是核心业务模型，例如：

- `VideoAsset`
- `Transcript`
- `TranscriptSegment`
- `SummaryDocument`

这一层代表“视频总结业务中稳定、可复用的对象”，不应该依赖文件系统、OpenAI、FastAPI。

### 3.2 `generation`

路径：

- `src/backend/video_summary/generation/ports.py`
- `src/backend/video_summary/generation/usecases/generate_summary.py`
- `src/backend/video_summary/generation/usecases/generate_mindmap.py`

这一层是“生成流程”的应用层。

它定义流程，但不直接绑定实现。比如摘要生成用例依赖的是这些抽象端口：

- `MediaProcessor`
- `Transcriber`
- `TranscriptEnhancer`
- `Summarizer`
- `GenerationArtifactStore`

这些端口定义在：

- `src/backend/video_summary/generation/ports.py`

这意味着生成用例只关心“要做什么”，不关心“具体怎么做”。

### 3.3 `library`

路径：

- `src/backend/video_summary/library/ports.py`
- `src/backend/video_summary/library/views.py`
- `src/backend/video_summary/library/usecases/*.py`

这一层是“工作区查询与操作”的应用层。

它面向 Studio/UI 提供能力，例如：

- 列出 series / videos
- 读取 summary
- 读取 mindmap
- 读取 chapter cards / knowledge cards
- 创建、更新、删除 notes
- 查询工具页状态

它依赖的核心端口是：

- `VideoWorkspace`

这说明 `library` 的目标不是重新生成内容，而是围绕工作区产物组织面向界面的用例。

### 3.4 `infrastructure`

路径：

- `src/backend/video_summary/infrastructure/*`

这里是外部机制实现层，主要包括：

- `faster_whisper_transcriber.py`
- `media_tools.py`
- `openai_summarizer.py`
- `openai_mindmap_generator.py`
- `openai_transcript_enhancer.py`
- `filesystem_generation_artifact_store.py`
- `filesystem_video_workspace.py`
- `settings.py`

这一层负责把外部世界接入进来：

- 文件系统
- ffmpeg
- faster-whisper
- OpenAI 兼容接口
- 本地配置

### 3.5 `video_summary` 的依赖方向

当前合理的依赖主干是：

```text
domain
  ^
  |
generation/usecases -----> generation/ports
library/usecases --------> library/ports
  ^
  |
infrastructure
```

可以更口语地理解为：

- `domain` 定义核心业务对象
- `generation` 和 `library` 定义应用层行为
- `infrastructure` 提供外部实现

## 4. `agent` 内部结构

### 4.1 `agent/agent`

路径：

- `src/backend/agent/agent/service.py`
- `src/backend/agent/agent/planner.py`
- `src/backend/agent/agent/execution.py`
- `src/backend/agent/agent/responder.py`

这是 Agent 的核心编排层，实际扮演的是 application service 的角色。

主流程大致是：

1. 加载上下文
2. 读取记忆
3. 生成 action plan
4. 执行工具
5. 生成 assistant message
6. 追加记忆

`AgentService` 是 Agent 子系统的主入口。

### 4.2 `ports`

路径：

- `src/backend/agent/ports.py`

这里定义 Agent 编排依赖的抽象：

- `ChatGateway`
- `AgentContextLoader`
- `AgentTranscriptLookup`
- `AgentToolExecutor`

这说明 Agent 核心并不直接依赖 OpenAI SDK、文件系统或前端协议。

### 4.3 `infrastructure`

路径：

- `src/backend/agent/infrastructure/chat_gateway.py`
- `src/backend/agent/infrastructure/workspace_context_loader.py`
- `src/backend/agent/infrastructure/transcript_lookup.py`

这里是 Agent 的外部适配层，实现上面的端口。

关键点在于：

- `WorkspaceAgentContextLoader` 通过 `VideoWorkspace` 读取工作区状态
- `WorkspaceTranscriptLookup` 通过工作区转写数据做检索
- `OpenAICompatibleChatGateway` 负责调用 LLM

所以 Agent 并不直接依赖 `video_summary` 的生成实现，而是依赖它暴露出来的工作区能力。

### 4.4 `memory`

路径：

- `src/backend/agent/memory/context.py`
- `src/backend/agent/memory/store.py`

这一层负责：

- Agent 上下文模型
- 对话历史存储
- 记忆范围控制

它表达的是 Agent 的运行时会话状态，不属于 `video_summary` 领域对象。

### 4.5 `schemas`

路径：

- `src/backend/agent/schemas/action_plan.py`
- `src/backend/agent/schemas/tool_calls.py`
- `src/backend/agent/schemas/messages.py`

这里装的不是“视频总结领域实体”，而是 Agent 协议对象，例如：

- action plan
- tool call
- tool result
- chat message

所以 `schemas` 更接近“Agent 协议模型层”，不是 `domain` 的同义词。

### 4.6 `tools`

路径：

- `src/backend/agent/tools/*.py`

这一层是工具动作处理器。

例如：

- 打开概况
- 打开导图
- 打开知识卡片
- 打开笔记
- 保存笔记
- 跳转视频时间点

这些函数负责把 plan 中的 tool call 变成结构化 tool result，供前端消费。

### 4.7 `validation`

路径：

- `src/backend/agent/validation/*.py`

这是 Agent 的协议约束层。

它负责防止 Planner 输出不合法动作，确保：

- scope 合法
- tool 调用参数合法
- answer / generate / seek / open_tool 等动作符合约束

### 4.8 `agent` 的依赖方向

当前 `agent` 的依赖主干可理解为：

```text
ports <----- agent/service
  ^              |
  |              v
infrastructure   tools / validation / schemas / memory
```

它没有 `video_summary` 那样整齐的 `domain/application/infrastructure` 命名，但核心思想仍然是：

- 核心编排层依赖抽象
- 外部实现放在基础设施层

## 5. `video_summary` 与 `agent` 的关系

两者不是上下级，也不是互相嵌套。

更准确地说：

- `video_summary` 提供内容能力与工作区能力
- `agent` 消费工作区能力，完成交互编排
- `api` 负责把两者组装到同一套 HTTP 服务中

当前关键耦合点是：

- `agent` 通过 `VideoWorkspace` 获取上下文
- `agent` 的工具动作通过 API / 前端协议驱动 Studio 行为

这是一种“跨子系统协作”，不是“同一个 domain 被拆烂了”。

## 6. API 层的角色

### 6.1 `api/bootstrap.py`

路径：

- `src/backend/api/bootstrap.py`

这是当前后端真正的 composition root。

它负责：

- 构建 `FileSystemVideoWorkspace`
- 构建 summary/mindmap/cards/notes 用例
- 构建 settings service
- 延迟构建 `AgentService`
- 把所有依赖装进 `ApiContainer`

这是整个系统中最重要的组装点。

### 6.2 `api/app.py`

路径：

- `src/backend/api/app.py`

这里是 FastAPI 交付层。

它负责：

- 定义 HTTP request / response
- 调用 container 中的用例
- 将异常映射为 HTTP 错误

从架构角色上讲，它不应该承载业务决策，只应该负责交付。

## 7. 当前架构的优点

### 7.1 生成链与工作区链已经分开

`video_summary` 没把“内容生产”和“Studio 查询”揉成一层，这是对的。

### 7.2 关键流程已引入端口抽象

无论是 `video_summary/generation/ports.py`，还是 `agent/ports.py`，都表明核心流程已经有“依赖抽象而非依赖实现”的意识。

### 7.3 `agent` 没有直接塞进 `video_summary`

这避免了把交互编排逻辑污染到内容主域中。

### 7.4 `api/bootstrap.py` 已经承担 composition root 职责

这让组装逻辑集中，而不是分散在业务代码里到处 `new`。

## 8. 当前架构的真实问题

### 8.1 两个子系统内部命名体系不一致

`video_summary` 更像：

- `domain`
- `ports`
- `usecases`
- `infrastructure`

`agent` 更像：

- `agent`
- `schemas`
- `tools`
- `validation`
- `memory`
- `infrastructure`

这会带来“像两套哲学拼在一起”的观感。

### 8.2 `agent/schemas` 是协议模型，但名字不够语义化

它现在承担的其实是：

- 交互协议
- 工具协议
- Planner 输出模型

`schemas` 这个名字太泛，后续容易继续长成大杂烩。

### 8.3 `video_summary` 中 `generation`、`library`、`usecases` 并存

目前 `usecases` 目录几乎没有实质内容，说明该子系统的目录演化还没有完全收口。

### 8.4 `api/app.py` 仍偏胖

交付层已经承担了过多接口定义，后续如果继续扩功能，建议按 bounded context 拆 router。

### 8.5 仓库存在噪音文件

如 `__pycache__` 这类编译产物不属于架构本身，但会显著干扰架构阅读与 review。

## 9. 当前最准确的架构判断

当前架构不是“纯正 Clean Architecture”，更不是“完全撕裂”。

更准确的描述是：

- 它已经形成两个明确的业务子系统
- `video_summary` 内部层次相对清楚
- `agent` 内部是以交互编排为核心的子系统
- `api` 作为总装入口把两者接起来
- 问题主要在于命名不对称和部分目录还未彻底收敛

## 10. 后续演进方向

后续如果继续收敛架构，优先级建议如下：

1. 统一 `agent` 与 `video_summary` 的内部层次语言
2. 收紧 `schemas` 的职责，避免继续泛化
3. 清理 `video_summary/usecases` 这类未完全收口的目录
4. 将 `api/app.py` 按功能域拆分 router
5. 持续保持“应用层依赖端口，基础设施实现端口”的方向

## 11. 一句话总结

当前后端架构可以概括为：

> `video_summary` 负责内容生产与工作区能力，`agent` 负责交互编排，`api` 负责统一组装与交付。

它的核心问题不是“子系统拆错了”，而是“两个子系统内部的架构语言还没有完全对齐”。
