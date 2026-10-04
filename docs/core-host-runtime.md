# Core 宿主运行接口

`vsummary-core==0.5.0a7` 提供 Local 与单机 Cloud 共用的多 workspace、持久任务及 API RAG 能力。身份、成员关系、部署目录和进程管理由宿主提供。

## 装配

- `backend.api.di.bootstrap.build_host_container()`：创建共享数据库仓储、模型配置、HTTP client 和其他宿主依赖，不启动后台任务。
- `build_workspace_services(container, workspace)`：装配属于该 workspace 的用例与 operation handlers；这些服务可以捕获自己的 workspace，不得复用其他 workspace 的服务图。
- `backend.api.di.sql_workspace_services.SqlWorkspaceServicesProvider`：根据 context 从关系库校验 workspace，再按 workspace 装配并缓存服务。配置目录共用，workspace 缓存与索引目录独立。
- `backend.api.common.app.create_app()`：注册 Core 路由。宿主已验证并注入的 `request.state.workspace_context` 会被保留；未注入身份且未提供显式 Local context provider 时，workspace 路由返回 401。
- `backend.api.workers.host.build_worker_host()`：独立 Job/Outbox 宿主，接受显式 `WorkerOptions`。worker 按 claim 的 workspace 选择服务。

Local 使用原有 `build_local_container()` 与 Local app。Local lifespan 继续在同一个进程中启动 worker/Outbox，固定 Local workspace 与原有启动命令保持有效。

文件 BlobStore 位于 `backend.video_summary.infrastructure.persistence.file_blob_store`，本地调用方与 wheel 消费方共用同一实现。配额基础策略统一命名为 `UnlimitedQuotaGuard`、`NoopUsageMeter`；Cloud 可以替换为自己的政策。

## 同机并发预算

`backend.core.concurrency.FileRequestLimiter(root, limits)` 接收同机共享锁目录与 `jobs/llm/asr/embedding/rerank` 额度。API 和 worker 必须绑定相同 limiter 预算。OS 文件锁约束进程之间的并发，进程结束后释放占用；预算不一致会拒绝启动。

Core 的 LiteLLM 同步、异步和流式网关、原生搜索、云端 ASR、API embedding/rerank 均使用请求额度。流式调用从开始请求到消费结束持续持有额度。`summary_chunk_concurrency` 仍然只限制一个视频内部的分片任务。

Local 可以不注入宿主预算，保留现有并发语义。自定义宿主若需要统一额度，应在 HTTP/worker 执行边界绑定 limiter，而非在每个 workspace 重新创建一份进程内 Semaphore。

## API RAG 配置

通过 `config/settings.toml` 的 `agent_retrieval` 段配置：

- `embedding_provider = "openai_compatible"`，完整 `embedding_endpoint`，模型名和明确的 `embedding_dimensions`。
- `embedding_batch_size` 控制每批文本数，独立于宿主请求并发预算。
- `api_timeout_seconds` 控制 HTTP 超时。
- rerank 关闭时不构建打分器；开启 API rerank 需要 `rerank_provider = "api"`、完整 `rerank_endpoint` 和 `rerank_model`。

`EMBEDDING_API_KEY`、`RERANK_API_KEY` 从服务器统一 `.env` 或进程环境读取，不写入 TOML。embedding 响应必须包含完整、唯一的输入索引和有限数值向量；rerank 必须返回每个候选文档的索引和有限分数。429/5xx/网络超时作为可重试 Job 错误，非法响应明确失败。

Local FastEmbed 配置仍然有效，API 模式的 Agent 不再要求本地 embedding 已下载。embedding profile 改变后，旧索引会触发重建。

## 持久任务与发布

部署需要执行 Core Alembic migration `0018_workspace_index_revisions`。它添加索引 requested/completed revision、当前 generation 指针，以及父 Job/资源/operation 唯一约束。迁移遇到已有重复子任务时应先检查历史数据，不应绕过唯一约束。

索引更新通过持久 Job 执行，Outbox 负责把内容发布转为持久刷新请求。刷新过程中出现新修改，完成当前任务时会创建后续刷新任务。worker 在新的 generation 目录构建候选索引，仅在租约有效时发布数据库指针；API 查询按该指针加载 workspace 索引。

系列父 Job 的成功表示分发结束。`GET /api/jobs/{id}` 对系列父 Job 返回 `children`、`dispatch_complete`、`batch_complete`。取消父 Job 会取消其子任务；子任务有持久幂等约束。

worker 将租约与请求 context 传播到后台服务及同步线程。业务发布事务检查租约、取消状态和已读取的内容版本，阻止过期 attempt 或基于旧内容的派生结果覆盖新数据。主内容发布后保持 Job 租约，直到辅助制品完成才标记任务成功。可写生成目录与缓存按 attempt 隔离，媒体 materialize 采用校验后的原子替换。

Core 不提供 Cloud 登录、workspace 成员管理、组织或计费产品实现。Cloud 应仅依赖发布的 wheel，并针对其实际数据库、文件目录、身份系统和模型 API 完成部署验收。
