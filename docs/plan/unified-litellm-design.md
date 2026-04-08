# 统一 LiteLLM 设计草案

## 1. 设计目标

本设计只解决一件事：

> 后端所有 LLM 调用链统一收口到 LiteLLM，彻底删除 `AsyncOpenAI + Instructor` 旁路。

这不是“再包一层兼容层”，也不是“先保留旧链，慢慢兜底”。
目标是：

1. `agent`
2. `video_summary`
3. `mindmap / transcript enhancement / summary generation`

全部走同一条 LiteLLM 基础设施路径。

## 2. 当前问题

当前项目里实际存在两条 LLM 链路：

### 2.1 Agent 链路

- 入口：[LiteLLMChatGateway](/E:/gittools/self/video_include/src/backend/agent/infrastructure/chat_gateway.py)
- 装配位置：[bootstrap.py](/E:/gittools/self/video_include/src/backend/api/bootstrap.py)
- 特点：
  - 走 LiteLLM
  - 主要是文本 completion / stream
  - 不支持 structured completion

### 2.2 视频生成链路

- 入口：[OpenAICompletionGateway](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/openai_summary/client.py)
- 装配位置：[runtime.py](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/runtime.py)
- 具体消费者：
  - [openai_summarizer.py](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/openai_summarizer.py)
  - [openai_transcript_enhancer.py](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/openai_transcript_enhancer.py)
  - [openai_mindmap_generator.py](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/openai_mindmap_generator.py)
- 特点：
  - 直接使用 `AsyncOpenAI`
  - 结构化输出依赖 `Instructor`
  - 和 Agent 侧 provider 入口完全割裂

## 3. 这次 500 的根因

`/api/videos/.../mindmap/generate` 报 500 的直接原因不是前端，不是路径编码，也不是没有 `summary.json`。

真实根因是：

1. 导图生成走到了 [OpenAIMindmapGenerator](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/openai_mindmap_generator.py)
2. 它调用了 [OpenAICompletionGateway.create_structured_completion](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/openai_summary/client.py)
3. 这条链路依赖 `Instructor`
4. `Instructor` 对当前 `gpt-5.4` 返回形态解析失败，抛出：
   - `Instructor does not support multiple tool calls, use List[Model] instead`

本质上，这是“旧 OpenAI SDK + Instructor 结构化路径”和当前模型返回形态不兼容。

结论：

> 不是 LiteLLM 失效，而是根本没有全项目统一走 LiteLLM。

## 4. 设计原则

### 4.1 唯一 LLM 出口

项目内只允许一个外部模型出口：

- `LiteLLM`

禁止继续保留：

- `AsyncOpenAI` 直连
- `Instructor` 解析旁路
- subsystem 自己 new client

### 4.2 结构化输出不依赖 SDK 魔法

结构化输出不再依赖：

- function calling 解析魔法
- Instructor 的 tool-call 假设
- 某个 provider 的专有 structured API

统一改成：

1. LiteLLM 发起普通 completion
2. 模型返回 JSON 文本
3. 本地解析 JSON
4. 用 `pydantic` 校验
5. 校验失败则重试

### 4.3 一个基础设施实现，多处业务复用

可以有业务层自己的 prompt builder / schema，但不能再有各自独立的客户端实现。

允许存在：

- `agent` 自己的消息构造
- `video_summary` 自己的 prompt builder
- `mindmap` 自己的 schema

不允许存在：

- `agent` 一套网关
- `video_summary` 另一套网关

### 4.4 Clean Architecture 约束

LiteLLM 只能存在于 infrastructure 层。

建议新位置：

```text
src/backend/shared/llm/
├─ contracts.py
├─ json_mode.py
└─ litellm_gateway.py
```

业务层只依赖抽象，不依赖 LiteLLM 包本身。

## 5. 目标架构

## 5.1 新的统一网关

建议新增：

- [shared/llm/contracts.py](/E:/gittools/self/video_include/src/backend/shared/llm/contracts.py)
- [shared/llm/litellm_gateway.py](/E:/gittools/self/video_include/src/backend/shared/llm/litellm_gateway.py)

### 抽象建议

```python
class LlmMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LlmGateway(Protocol):
    def complete_text(self, messages: list[LlmMessage], *, temperature: float = 0) -> str: ...
    def stream_text(self, messages: list[LlmMessage], *, temperature: float = 0) -> Iterator[str]: ...
    def complete_model(
        self,
        messages: list[LlmMessage],
        *,
        response_model: type[BaseModel],
        temperature: float = 0,
        retries: int = 2,
    ) -> BaseModel: ...
```

这里的关键不是“再抽象一层 provider 兼容矩阵”，而是：

> 对内只暴露一个统一的 LiteLLM 基础设施入口。

## 5.2 LiteLLM 网关内部能力

### `complete_text`

- 统一调用 `litellm.completion`
- 支持基础文本 completion
- 供：
  - request router
  - evidence selector
  - routed answerer
  - summary chunk summarizer

### `stream_text`

- 统一调用 `litellm.completion(..., stream=True)`
- 只给 `agent` 流式输出使用

### `complete_model`

这是替代 `Instructor` 的关键。

实现方式：

1. 从 `response_model.model_json_schema()` 生成 JSON 输出约束
2. 把 schema 以“输出必须严格符合此 JSON 结构”的形式拼进 system/user prompt
3. 调用 `complete_text`
4. 提取 JSON 对象
5. 用 `response_model.model_validate(...)` 校验
6. 校验失败则把错误反馈拼回 prompt，要求模型重发纯 JSON

注意：

- 这里仍然只走 LiteLLM completion
- 不是另一条 structured client
- 不是 `Instructor fallback`
- 不是双栈

## 5.3 JSON 输出策略

建议统一封装到：

- [shared/llm/json_mode.py](/E:/gittools/self/video_include/src/backend/shared/llm/json_mode.py)

内部做三件事：

### A. Schema 渲染

把 `pydantic` schema 缩成模型可理解的 JSON 结构说明。

要求：

- 只保留必要字段
- 避免把完整 schema 原样塞进去造成 prompt 爆炸
- 对递归结构如 `MindmapNodePayload` 做简化说明

### B. JSON 提取

从模型返回文本中提取：

- 纯 JSON
- fenced JSON
- 前后混杂说明但中间有 JSON 的情况

如果提取失败，直接进入 retry，不要吞错。

### C. 校验重试

如果校验失败，下一轮补充：

- 上一轮输出片段
- 校验错误摘要
- “请只返回修正后的 JSON”

最大重试次数建议：

- 默认 `2`
- mindmap 可放宽到 `3`

## 6. 子系统迁移方案

## 6.1 第一批：video_summary 全量迁 LiteLLM

优先迁这三个，因为它们当前直接受 `Instructor` 影响：

1. [openai_mindmap_generator.py](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/openai_mindmap_generator.py)
2. [openai_summarizer.py](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/openai_summarizer.py)
3. [openai_transcript_enhancer.py](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/openai_transcript_enhancer.py)

改造后：

- 文件可保留业务语义命名，但内部依赖改成统一 `LlmGateway`
- 或直接更名为：
  - `litellm_mindmap_generator.py`
  - `litellm_summarizer.py`
  - `litellm_transcript_enhancer.py`

建议更名，避免“名字叫 openai，实际上走 litellm”的认知污染。

## 6.2 第二批：video_summary runtime 删除旧客户端

改造：

- 删除 [openai_summary/client.py](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/openai_summary/client.py)
- 删除 `AsyncOpenAI`
- 删除 `Instructor`
- [runtime.py](/E:/gittools/self/video_include/src/backend/video_summary/infrastructure/runtime.py) 改为从 shared llm 装配统一 LiteLLM gateway

## 6.3 第三批：agent 网关收口到 shared llm

当前 Agent 已经走 LiteLLM，但实现是另一套独立网关：

- [chat_gateway.py](/E:/gittools/self/video_include/src/backend/agent/infrastructure/chat_gateway.py)

这一步不需要改业务行为，重点是：

- 让 Agent 也复用 shared llm 基础设施
- `LiteLLMChatGateway` 可以变成 shared gateway 的薄适配壳，或者直接删除

## 6.4 第四批：bootstrap 统一装配

最终目标：

- `agent`
- `video_summary`
- `mindmap`
- `transcript enhancement`

都从同一个 provider 配置入口拿到同一种 `LiteLLMGateway`。

装配点建议最终统一到：

- [bootstrap.py](/E:/gittools/self/video_include/src/backend/api/bootstrap.py)
- [video_summary/bootstrap.py](/E:/gittools/self/video_include/src/backend/video_summary/bootstrap.py)

但后者只允许“从 shared gateway 工厂拿实例”，不允许自己再 new provider client。

## 7. 必删项

这轮设计明确要求删除以下技术债：

### 7.1 删除旧 OpenAI 客户端链

- `src/backend/video_summary/infrastructure/openai_summary/client.py`

### 7.2 删除 Instructor 依赖路径

- 不再在任何业务路径中使用 `instructor.from_openai(...)`

### 7.3 删除 subsystem 私建 client

禁止继续出现：

- 某个 generator/summarizer 自己持有 `AsyncOpenAI`
- 某个 workflow 自己决定 provider SDK

## 8. 为什么不继续保留“旧链 fallback”

因为这会重新制造双路径：

1. LiteLLM 主路径
2. AsyncOpenAI / Instructor fallback

这类 fallback 的问题不是“能不能跑”，而是：

- 调试时你不知道到底走了哪条链
- 某些 provider 只在一条链上可用
- 同样的模型配置在不同子系统表现不一致
- 又回到今天这个问题

所以：

> 这次设计明确不保留旧客户端 fallback。

只允许：

- LiteLLM completion
- LiteLLM stream
- LiteLLM + JSON contract + pydantic validate

## 9. 风险点

## 9.1 递归 schema 提示过重

`MindmapNodePayload` 是递归结构，完整 schema 直接灌给模型会很重。

解决：

- schema 渲染时只描述字段和递归关系
- 不把全部 JSON Schema 原样贴进 prompt

## 9.2 JSON 输出不稳定

部分 OpenAI-compatible 模型 JSON 输出能力一般。

解决：

- 本地提取 + 校验 + retry
- 把校验错误反馈给模型重发

## 9.3 agent 与 video_summary message 模型不同

这不是核心问题。

解决：

- shared llm 接受统一 `LlmMessage`
- 各子系统做轻量转换

## 9.4 测试迁移成本

现有 [test_openai_summary_infrastructure.py](/E:/gittools/self/video_include/tests/test_openai_summary_infrastructure.py) 是围绕旧客户端写的。

解决：

- 新建 `test_litellm_video_summary_gateway.py`
- 旧测试逐步替换

## 10. 实施顺序

### Phase 1：shared LiteLLM gateway

产出：

- `shared/llm/contracts.py`
- `shared/llm/json_mode.py`
- `shared/llm/litellm_gateway.py`
- 单测

### Phase 2：mindmap 先迁

原因：

- 当前真实 bug 就在这里
- 价值最高
- 可快速验证“LiteLLM + JSON 校验”是否稳定

### Phase 3：summary / transcript enhancement 迁移

把所有 `video_summary` 结构化输出迁完。

### Phase 4：agent 网关收口

让 `agent` 与 `video_summary` 共用同一 LiteLLM 基础设施。

### Phase 5：删除旧链

删除：

- `OpenAICompletionGateway`
- `Instructor`
- 旧测试与引用

## 11. 验证策略

### 单元测试

新增：

- LiteLLM 文本 completion 测试
- LiteLLM stream 测试
- JSON 提取测试
- pydantic 校验重试测试
- 递归 mindmap schema 测试

### 集成测试

新增：

- `mindmap/generate` 在 fake completion 下成功落盘
- `summary` 生成结构化输出成功
- `transcript enhancer` 分块校验成功

### 真实模型回归

新增脚本建议：

- `scripts/run_mindmap_live_probe.py`
- `scripts/run_summary_live_probe.py`

至少输出：

- prompt token 估算
- completion token
- 是否一次过校验
- 重试次数
- 最终落盘路径

## 12. 最终结论

这次不应该再修 `Instructor`。

正确方向是：

1. 统一 LiteLLM 为唯一模型出口
2. 结构化输出改为 `LiteLLM completion -> JSON -> pydantic`
3. 先迁 mindmap，再迁 summary/transcript enhancement
4. 最后删除旧 `AsyncOpenAI + Instructor` 链

一句话总结：

> 不是给旧 OpenAI 结构化链打补丁，而是把整个项目的 LLM I/O 收敛为一条统一的 LiteLLM 主路。 
