# 为后端代码添加中文注释 — 设计文档

**日期**：2026-06-15
**状态**：已批准（用户口头确认 4 节设计）
**作者**：通过 brainstorming skill 与用户协作完成

---

## 1. 目标与动机

为后端核心代码添加中文 Google 风格 docstring，让中文使用者扫读代码时无需翻译业务术语即可理解模块、类、函数的意图。**不修改任何业务逻辑**。

## 2. 范围

### 2.1 包含（约 150 个 .py 文件）

| 范围 | 内容 |
|---|---|
| `src/backend/video_summary/domain/` | 领域值对象（dataclass） |
| `src/backend/video_summary/library/` | 用例 + DTO + 端口定义 |
| `src/backend/video_summary/generation/` | 转写/总结/知识卡片用例 |
| `src/backend/video_summary/infrastructure/` | 适配器：faster-whisper、LiteLLM、文件 IO、LanceDB、设置 |
| `src/backend/agent/` | Agent 协议、内存、上下文预算、会话、校验 |
| `src/backend/agent_graph/` | LangGraph 工作流、节点、状态、证据、提示词 |
| `src/backend/api/routes/` | 所有 FastAPI 路由 |
| `src/backend/api/`（除排除项外） | 剩余 API 模块 |
| `src/backend/shared/` | LLM 网关等横切关注点 |
| `src/backend/bilibili/` | B 站导入适配 |
| `src/backend/chaoxing/` | 学习通导入适配 |

### 2.2 明确排除

- `src/backend/api/static_assets.py`（静态资源挂载）
- `src/backend/api/bootstrap.py`（容器装配，模式高度重复）
- `src/backend/api/server.py`（uvicorn 入口）
- `src/backend/tools/release_packaging.py`（PyInstaller 打包）
- 所有 `__init__.py`（已自解释）
- `tests/**`（测试代码）
- `src/frontend/**`（前端，本轮不做）

## 3. 注释风格规范

### 3.1 模块顶部说明

每个 .py 文件在 `from __future__ import annotations` 之后加 1-2 句中文模块说明，说明模块做什么以及在分层架构中的位置。不写"本文件定义了..."这种废话。

```python
from __future__ import annotations

"""视频资产值对象定义。

本模块只包含不可变的领域数据类型，不依赖任何基础设施。
"""
```

### 3.2 函数 docstring

- **简单函数**（无参无返回）：单行 `"""xxx。"""`
- **有参有返回**：Google 风格多行，使用 `Args:` / `Returns:` / `Raises:` / `Yields:` 段
- **私有方法（`_` 开头）**：同样写 docstring（粒度统一）

### 3.3 类 docstring

第一段说明类做什么 + 关键不变量。复杂类可加 `Attributes:` 段列出非显然字段。

### 3.4 术语翻译约定

**保留英文**（框架/协议/缩写/专有名词）：
- 框架：`LangGraph`、`StateGraph`、`Node`、`Edge`、`FastAPI`、`Pydantic`
- 协议：`Port`、`Protocol`、`Adapter`
- 缩写：`RAG`、`ASR`、`LLM`、`SSE`、`DTO`、`IO`、`HTTP`
- 工具：`LiteLLM`、`LlamaIndex`、`LanceDB`、`FastEmbed`、`faster-whisper`、`yt-dlp`
- 业务关键名词：`Evidence`、`EvidenceItem`、`Workspace`、`Session`、`Progress`、`Transcript`、`Summary`

**译为中文**（普通业务动词/名词）：
- use case / usecase → 用例
- embed / embedding → 嵌入
- retrieve / retrieval → 检索
- transcribe → 转写
- summarize → 总结
- chunk → 分片
- workspace → 工作区
- query → 查询

## 4. 现有英文内容处理

- **docstring**：替换为中文 Google 风格
- **# 行内注释**：保留原英文（特别是 TODO、坑点提示、算法解释这类有价值的注释）；如果某些行内注释只是解释参数含义（已在 docstring 中说明），可一并改为中文或删除

## 5. 执行策略：C → B 组合

### Phase 0：示范（2 个文件）

| 文件 | 用途 |
|---|---|
| `src/backend/video_summary/domain/video_asset.py` | 简单 dataclass，覆盖类 docstring 模板 |
| `src/backend/agent_graph/runtime/state.py` | TypedDict 复杂类，覆盖复杂类 docstring |

完成后**输出预期 diff 给用户审**，确认风格后再进入 Phase 1。

### Phase 1-5：分批推进（按依赖从内到外）

| Phase | 范围 | 约文件数 |
|---|---|---|
| Phase 1 | `video_summary/domain/` | ~5 |
| Phase 2 | `video_summary/library/` | ~25 |
| Phase 3 | `video_summary/generation/` + `infrastructure/` | ~50 |
| Phase 4 | `agent/` + `agent_graph/` | ~40 |
| Phase 5 | `api/routes/` + `api/`（除排除项）+ `shared/` + `bilibili/` + `chaoxing/` | ~30 |
| Phase 6 | 扫尾与全量验证 | — |

每个 Phase 一个 git commit：`docs(comments): Phase N 中文注释 - <包名>`

### 工作节奏

- 本次会话：完成 Phase 0 + Phase 1
- 后续会话：按节奏推进 Phase 2-5
- 任意节点可暂停、调整风格、回滚单个文件

## 6. 质量门控

### 6.1 每个文件改完后

- `python -m py_compile <file>` 语法检查
- 抽查 diff 确认只动了 docstring/模块说明/行内注释

### 6.2 每个 Phase 完成后

- `lint-imports`（import-linter）跑全量
- `python -m pytest tests/backend/unit/<相关域> -x` 跑相关域
- grep 抽样确认 docstring 覆盖度

### 6.3 Phase 6 全部完成后

- `lint-imports` 全量
- `python -m pytest tests/backend -x` 全量
- 扫描未翻译的英文 docstring（应接近 0）
- 每个 Phase 抽 1 个文件人工 review

### 6.4 红线：不动实现代码

**任何修改只能在以下三类位置：**
1. docstring 字符串
2. 模块顶部说明
3. 必要的 # 行内注释

**不能动**：
- 函数签名、函数体实现
- import 列表
- 装饰器
- 类继承关系
- 任何运行时行为

### 6.5 跳过规则

- 自动生成的 dunder 方法（`__init__`、`__repr__`、`__eq__`、`__hash__` 等）除非被业务显式 override
- 空 `__init__.py`
- 单行 `from X import Y` 的 re-export 模块

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| 中文 docstring 编码错误 | 全程 UTF-8，每文件改完 py_compile |
| 不小心改坏逻辑 | 只改 docstring 字符串、模块顶部、行内注释 |
| 长函数 docstring 也变得不实用 | 长函数（>30 行）只写 docstring，不强求行内注释 |
| 异步 / dataclass 特殊情况 | 已在跳过规则中说明 |

## 8. 不在本次范围（YAGNI）

- 前端 JS/JSX 注释
- 测试代码注释
- README / 文档翻译
- 英文→中文术语对照表（除非后续需要维护）
- 自动生成代码（pydantic 自动字段等）

## 9. 后续步骤

1. 本设计文档提交 git commit
2. 用户复核文档
3. 调用 `writing-plans` skill 产出实施计划
4. 按计划执行 Phase 0 → Phase 6

---

## 附录 A：模板示例

### A.1 简单函数

```python
def is_empty(self) -> bool:
    """判断是否为空视频资产。"""
```

### A.2 完整 Google 风格

```python
def chunk_transcript(text: str, max_chars: int = 500) -> list[str]:
    """把长文本切成最大字符数的片段。

    按空白字符就近切分，不会截断单词。

    Args:
        text: 原始文本。
        max_chars: 单片段最大字符数。

    Returns:
        切分后的字符串列表，至少包含一个元素。
    """
```

### A.3 类

```python
class VideoAsset:
    """视频资产不可变值对象。

    表示一个已索引的视频条目：基本元数据 + 转写文本 + 总结文档。
    一旦构造不允许修改，等值比较按业务键 (asset_id) 进行。

    Attributes:
        asset_id: 业务唯一 ID。
        source_uri: 原始视频 URI。
        transcript: 转写文本，可能为空。
        summary: 结构化总结，可能为空。
    """
```