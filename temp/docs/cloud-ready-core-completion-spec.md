# VSummary Cloud-Ready Core 完成规格

## 文档状态

- 状态：Draft，实施前规格。
- 编写日期：2026-09-19。
- 适用范围：VSummary Core、本地整合包、未来云端 API 与 Worker 宿主。
- 前置文档：[统一 MySQL 存储与 RAG 数据架构规格](./mysql-unified-storage-and-rag-spec.md)。本文不重复内容表和 Blob 元数据设计，而是定义如何完成云端执行层。
- 非目标：登录、OAuth、JWT、套餐、支付、计费、组织成员和网关限流不属于 Core。Core 只接受宿主传入的 owner scope 与访问过滤结果。

## 1. 结论

当前代码已经跨过“仅有数据库表设计”的阶段。媒体和结构化内容的权威存储已迁移到 MySQL + BlobStore，默认容器拒绝回退到 JSON 文件工作区。

但当前 Core 仍不是完整的多实例云端执行 Core。长任务仍在 API 进程内直接执行；进度、取消、RAG 刷新和一部分并发控制仍依赖进程内状态。

目标边界如下：

    当前：
    HTTP API -> 直接等待 ASR / LLM / FFmpeg
             -> 内存进度、Python Lock
             -> SQL + BlobStore 发布内容
             -> 当前进程线程刷新 RAG

    目标：
    HTTP API -> 在 DB 事务中提交 Job + 幂等记录
             -> 202 { job_id, status_url, events_url }

    Worker -> claim / lease / heartbeat -> 任务临时目录执行
           -> staging Blob + staging content
           -> 原子发布当前内容 + outbox

    Outbox Consumer -> RAG / 导出 / 清理等异步副作用

本地版可以把 API、Worker、Consumer 置于一个进程，但必须使用与云端多进程完全相同的 MySQL Job 与 Outbox 协议。

## 2. 当前实现基线

| 能力 | 状态 | 现有基础 | 结论 |
| --- | --- | --- | --- |
| MySQL 权威数据 | 已完成 | SqlVideoWorkspace 已替代 FileSystemVideoWorkspace。 | 可作为云端内容数据库基础。 |
| BlobStore | 已完成本地实现 | FileBlobStore 有 staging、hash 校验、原子 commit 与 materialize。 | 需要抽象 Port 与对象存储 adapter。 |
| 稳定资源 ID | 已完成基础 | 控制面、内容表使用 26 位 ULID。 | 目录和对象路径不再是业务身份。 |
| 当前内容发布 | 已完成基础 | SqlCurrentContentRepository 具备 stage/publish、版本更新、content_published outbox。 | 是 Worker 的正确发布终点。 |
| 旧工作区迁移 | 已完成基础 | LegacyWorkspaceImporter 可一次导入旧目录。 | 需补诊断与恢复验收。 |
| Agent session / LLM 用量 | 已完成 | 已切换 SQL session store 和 MySQL usage store。 | 不依赖本地 session/SQLite。 |
| SQL RAG source | 已完成基础 | rag_documents、rag_chunks、索引状态表已存在。 | 还未由 Outbox 消费驱动。 |
| Job、幂等、outbox Schema | 已完成基础 | jobs、idempotency_keys、job_events、outbox_events 已迁移。 | 还不是完整任务执行协议。 |
| Job 提交 | 部分完成 | SqlControlPlaneRepository 可提交 Job 与幂等记录。 | 生成 API 尚未以它为唯一入口。 |
| Job claim / lease / retry | 未完成 | 没有领取、续租、attempt、过期恢复实现。 | 首要云端化缺口。 |
| API 无状态 | 未完成 | 多个 InMemoryProgressTracker 由容器创建。 | 重启或负载均衡会丢状态。 |
| 长任务异步化 | 未完成 | POST generate 仍直接 await 生成用例。 | API 超时和独立扩容不可用。 |
| 跨实例并发 | 未完成 | 仍有 Lock、asyncio.Lock、进程内活动集。 | 应替换为 DB 约束和条件更新。 |
| Outbox 消费 | 未完成 | 只写 outbox 行，未见 consumer claim/deliver。 | 异步副作用不可靠。 |
| RAG 事件驱动 | 未完成 | _WorkspaceIndexRefresher 使用内存集合与线程。 | 多进程不可恢复。 |
| 生命周期清理 | 未完成 | 临时目录清理存在，staging/orphan/export 保留策略未完成。 | 长期运行会积累对象。 |
| 故障恢复测试 | 未完成 | 有持久层单测和 MySQL HTTP 冒烟。 | 尚无多 Worker、重启和竞争验收。 |

本轮基线检查：持久层单测通过，持久化模块可编译。该结果不能替代真实 MySQL、多 Worker、重启恢复测试。

## 3. 目标与非目标

### 3.1 目标

1. 所有长任务通过持久化 Job 提交和执行，API 不等待 ASR、FFmpeg、LLM 或向量索引。
2. 任务状态、进度、取消、重试次数、租约、失败原因和结果在 MySQL 持久化。
3. 一个任务最多由持有有效 lease 的 Worker 发布；失联 Worker 不能覆盖后来重试结果。
4. 相同请求可通过 idempotency key 安全重试；同一资源同操作用数据库 active key 去重。
5. 内容发布、任务终态和 outbox event 在同一事务完成。
6. RAG、导出、清理由 Outbox Consumer 可恢复处理；向量库始终可从 SQL 重建。
7. BlobStore 通过 Port 注入，本地文件和 S3/OSS adapter 共享正确性契约。
8. 本地同进程与云端多进程运行同一份 Core 语义。

### 3.2 非目标

- 首期不引入消息队列作为新的真相来源。MySQL Job 和 Outbox 表是权威；消息队列以后最多作为唤醒优化。
- 不在 Core 推断用户身份或实现商业系统。
- 不保留 JSON 与 SQL 的长期双写或运行时回退。
- 不让同步接口执行任何长计算；仅保留小型纯数据库编辑。

## 4. 不变量

### 4.1 权威来源

- MySQL：业务状态、当前内容、任务、进度、取消、用量、outbox。
- BlobStore：视频、音频、图片、原始字幕、导出等二进制。
- 向量库：派生索引，可完全从 MySQL 恢复。
- 内存：仅缓存或执行优化；进程退出不能影响正确性。

### 4.2 身份和路径

- workspace_id、series_id、video_id、job_id、artifact_id、outbox_event_id 均为稳定 ULID。
- 标题、原文件名、对象 key、临时目录、外部平台 ID 都是属性，不能作为授权、锁或主键。
- Worker 临时目录必须包含 job_id 和 attempt_no，且绝不能返回给客户端。

### 4.3 失败优先

- 无法验证任务所有权、内容完整性、Blob hash 或版本一致性时，任务失败并持久化诊断，不能静默回退。
- 外部 I/O 成功但 DB 事务失败时，对象必须作为 orphan 留待清理，不能假设发布完成。
- 内容发布成功后 RAG 失败不回滚内容，应记录 needs_rebuild 并重试。

## 5. 目标组件边界

    API Host
      -> JobRepository: submit/query/cancel
      -> Job event SSE: 读取 MySQL 事件

    Job Worker
      -> JobRepository: claim/renew/complete/fail
      -> JobExecutor: ASR/LLM/FFmpeg
      -> BlobStore: staging/commit/materialize
      -> CurrentContentRepository: atomic publish

    Outbox Consumer
      -> OutboxRepository: claim/deliver/retry
      -> RAG / export / lifecycle handlers

Core 最小 Port：

| Port | 最小责任 |
| --- | --- |
| JobRepository | submit、get、claim、renew_lease、append_event、request_cancel、complete、fail、retry。 |
| JobExecutor | 执行已领取的某个 operation；不拥有领取策略。 |
| OutboxRepository | claim、mark_delivered、reschedule、查看死信。 |
| OutboxHandler | 处理明确事件类型，例如 RAG 更新、导出、清理。 |
| BlobStore | staging put、commit、open、materialize、stat、discard、delete。 |
| Clock | 统一时间和可控测试时钟。 |
| WorkerIdentityProvider | 提供稳定 worker_id，例如 pod ID 加实例 UUID。 |

SqlVideoWorkspace 必须从直接依赖 FileBlobStore 改为依赖 BlobStore Protocol。

## 6. Job 模型

### 6.1 Operation 白名单

operation 必须是固定枚举，不能由 API 传任意函数名：

| operation | resource | 结果 |
| --- | --- | --- |
| generate_summary | video | 发布转写、总结、视觉证据等新的 content_version。 |
| generate_transcript | video | 发布转写并使依赖制品过期。 |
| generate_mindmap | video/series | 发布导图。 |
| generate_cards | video | 发布知识卡。 |
| generate_ai_summary | video | 发布 AI 概括和证据。 |
| download_linked_media | video | 下载并提交媒体 Blob。 |
| import_legacy_workspace | installation/workspace | 一次性迁移。 |
| rebuild_rag | workspace/series/video | 重建 SQL RAG source 或向量索引。 |
| export_series | series | 创建有保留期的导出 Blob。 |
| cleanup_lifecycle | workspace/global | 清理 staging、orphan、临时缓存和过期导出。 |

每个 operation 有版本化 Pydantic payload。Worker 不得依赖 HTTP Request、request.state、API 进程闭包或当前工作目录。

### 6.2 Job 状态机

    queued -- claim --> running -- complete --> succeeded
      |                  |  ^
      | cancel           |  | retry after backoff
      v                  |  |
    cancelled <- cancel -+  +-- retrying <- transient error / lost lease

    queued/running/retrying -- permanent error --> failed
    running -- cancellation request --> cancelling --> cancelled
    succeeded -- derived failure --> needs_rebuild

状态定义：

- queued：已提交、等待领取。
- running：Worker 有有效 lease。
- retrying：上次 attempt 可重试，等待 available_at。
- cancelling：取消意图已持久化。
- cancelled：未发布候选结果且已停止。
- succeeded：结果已原子发布。
- failed：最终失败，保存稳定错误码和脱敏细节。
- needs_regeneration / needs_rebuild：结果或派生索引过期，不等于内容丢失。

jobs 应补充下列字段：

    available_at
    claimed_by
    lease_expires_at
    cancel_requested_at
    started_at
    finished_at
    next_retry_at
    max_attempts
    last_failure_code
    last_failure_detail
    result_content_version

新增 job_attempts 表，每次 claim 一行：

    job_id, attempt_no, worker_id, lease_token,
    started_at, heartbeat_at, finished_at,
    outcome, failure_code, failure_detail

lease_token 必须随机且不可预测，不能只依赖 job_id。

### 6.3 Claim 和 Lease

Worker 在短事务内领取一个任务。MySQL 8 使用 SELECT ... FOR UPDATE SKIP LOCKED，或等价条件 UPDATE；两种实现都必须保证最多一个 Worker 成功领取。

可领取条件：

    status IN (queued, retrying)
    AND available_at <= now
    AND cancel_requested_at IS NULL

过期恢复条件：

    status = running
    AND lease_expires_at < now

恢复时先结束旧 attempt 为 lost_lease，再按 retry policy 转为 retrying 或 failed。

任何以下写入都必须检查 lease 所有权：

    job_id = :job_id
    status = running
    claimed_by = :worker_id
    lease_token = :lease_token
    lease_expires_at > :now

该条件适用于 heartbeat、进度、staging 标记、发布、成功、失败和取消。受影响行数不是 1 时，Worker 必须停止，不得发布。

默认：lease 60 秒，heartbeat 15 秒。长供应商调用若不可中断，仍需后台续租；调用完成后必须再次验证 lease 和取消状态。

### 6.4 重试

仅暂态错误重试：网络超时、供应商 429/5xx、对象存储暂不可用、可重试 DB 死锁。输入无效、媒体格式不支持、权限失败、非法内容、用户取消不能自动重试。

默认最多 3 次，退避为 15 秒、60 秒、300 秒，并加不超过 20% 抖动。每次重试创建新的 attempt、临时目录和 staging Blob。

稳定 failure_code：

    invalid_request
    source_missing
    source_corrupt
    provider_rate_limited
    provider_unavailable
    provider_invalid_response
    blob_unavailable
    blob_integrity_failed
    database_conflict
    lease_lost
    cancelled
    internal_error

## 7. API 合约

### 7.1 提交

所有长任务端点改为 Job 提交。例如：

    POST /api/videos/{series_id}/{video_id}/generate
    Idempotency-Key: 01J...
    { "processing_mode": "summary", "transcript_enhancement_enabled": true }

返回 202：

    {
      "job_id": "01J...",
      "status": "queued",
      "resource": { "type": "video", "id": "01J..." },
      "status_url": "/api/jobs/01J...",
      "events_url": "/api/jobs/01J.../events"
    }

相同 scope、相同幂等键和相同规范化 body 返回同一 job_id。相同 key、不同 body 返回 409 idempotency_key_reused。缺少幂等键时仍需 active key 防止同资源同操作并发。

客户端不得提供 workspace_id、owner_scope_id、job_id、worker_id、active_key、对象 key 或 provider secret。宿主负责从认证上下文注入 scope。

### 7.2 查询、SSE 和取消

端点：

    GET /api/jobs/{job_id}
    GET /api/jobs/{job_id}/events?after_sequence=42
    POST /api/jobs/{job_id}/cancel

查询返回状态、attempt 数、最新进度、取消意图、失败码和公开结果引用，不返回绝对路径、密钥、原始 exception 或供应商私密响应。

SSE 从 job_events 读取，而不是 InMemoryProgressTracker。客户端可通过 Last-Event-ID 或 after_sequence 补发；job 内 sequence 严格单调且唯一。

事件最小形式：

    {
      "job_id": "01J...",
      "sequence": 43,
      "status": "running",
      "stage": "transcribe",
      "progress": 48.0,
      "detail": "正在转写音频",
      "occurred_at": "2026-09-19T...Z"
    }

阶段变化必须记录；同一阶段按至少 1% 或每 2 秒限流写入。终态事件必须记录。

取消 API 只记录取消意图并把非终态任务置为 cancelling。Worker 在阶段边界检查取消；取消先于发布提交时，发布事务必须失败并将 Job 转 cancelled。

## 8. 原子发布和版本控制

现有 staging/publish 模式保留，但改为仅由持有有效 lease 的 Worker 调用：

1. Worker 为一次 attempt 创建 staging 内容和 staging Blob。
2. 校验 payload、Blob、内容 schema、取消请求和 lease。
3. 一个 DB 事务锁定 Job 与 Video，并检查 lease token 与 cancel_requested_at 为空。
4. 发布 staging 内容，递增 content_version，绑定已提交 Blob 元数据，写 content_published outbox，写终态 Job event，置 Job 为 succeeded 并清空 active_key。
5. 提交后清理本地临时目录和 staging；失败交给 cleanup Job，不能回滚已经发布内容。

人工编辑必须携带 row_version 或 content_version，执行条件更新。条件不满足返回 409，禁止最后写入者静默覆盖。

content_published 最小 payload：

    {
      "workspace_id": "01J...",
      "series_id": "01J...",
      "video_id": "01J...",
      "content_version": 18,
      "source": "generate_summary",
      "job_id": "01J..."
    }

## 9. Outbox 和 RAG

### 9.1 投递模型

不能以单个 outbox_events.delivered_at 表示所有下游已处理。新增每 consumer 的投递记录：

    outbox_deliveries(
      event_id,
      consumer_name,
      status,
      claimed_by,
      lease_expires_at,
      attempt_count,
      available_at,
      last_error,
      delivered_at,
      PRIMARY KEY(event_id, consumer_name)
    )

Handler 必须幂等，允许至少一次投递。SQL RAG refresh 用 video_id + content_version + source_type 去重；向量库使用 chunk_id 作为稳定文档 ID。

### 9.2 RAG Handler

content_published、note_published、knowledge_cards_published、resource_deleted 等事件驱动 RAG：

1. RAG Worker claim delivery。
2. 以资源 ID 和版本读取 SQL；旧版本已被替代时可跳过并索引最新版本。
3. 原子刷新 rag_documents/rag_chunks，再更新向量索引状态。
4. 成功后标记 delivery；失败后记录错误并重试。

进程内 _WorkspaceIndexRefresher、内存集合和线程不能再承担索引正确性职责。它们可短期保留为 UI cache 优化，但不是事实来源。

### 9.3 索引重建

向量库被删除、embedding 模型升级或 chunker 修改时：

1. 创建 building 状态的 rag_index_version。
2. rebuild_rag Job 分页读取 SQL rag_chunks。
3. 每个 chunk 的状态写入 rag_index_entries。
4. 全部成功后把新版本切为 active；失败保留 failed 和恢复游标。

不得扫描旧 workspace 文件或依赖 LanceDB signature 文件。

## 10. BlobStore Port 和生命周期

### 10.1 Port 契约

BlobStore Protocol 至少包含：

    put_staging(job_id, source, content_type) -> StagedBlob
    commit(staged, object_key) -> BlobReference
    open(reference) -> BinaryIO
    materialize(reference, task_dir, filename) -> Path
    stat(reference) -> BlobReference
    discard_staging(staged)
    delete(reference)

所有 adapter 都必须：

- 拒绝客户端给出的绝对路径、..、反斜杠和不可索引对象 key。
- 以 sha256 与 size 验证 staging/committed 对象。
- 同 key 同内容 commit 幂等；同 key 不同内容失败。
- 只对已授权资源提供 materialize 或 presigned URL。

本地 FileBlobStore 保持同卷原子 replace。S3/OSS adapter 应采取 staging key 到 committed key 的服务端复制，再由 DB 事务发布元数据；不能假设对象存储和 MySQL 存在跨系统事务。

### 10.2 生命周期

Blob/artifact 状态：staging、committed、orphaned、deleted。

- staging：成功发布转 committed；失败/取消后待删。
- orphaned：对象存储成功而 DB 发布失败时标记，保留期后清理。
- materialized 文件：attempt 结束删除；重启遗留由 cleanup Job 按 age 回收。
- export：默认保留 24 小时。
- failed Job staging：默认保留 24 小时用于诊断，随后删除，且绝不对客户端可见。

清理是独立可重试 Job，先切 DB 状态，再删对象。删除对象成功但 DB 更新失败时，下次清理仍须安全重复。

## 11. 配置和宿主装配

Core 仅接收显式 options/Port，不自行读取当前目录、.env、Docker secret 或 Kubernetes secret。

建议宿主配置：

    DatabaseOptions(url, pool_size, ...)
    BlobStoreOptions(kind, endpoint, bucket, credential_reference, ...)
    WorkerOptions(worker_id, concurrency, lease_seconds, heartbeat_seconds, ...)
    VectorIndexOptions(kind, location, embedding_model, chunker_version, ...)
    ModelProviderOptions(...)

本地宿主：

1. 启动受管 loopback MySQL。
2. 获取显式 DatabaseOptions。
3. 运行 migration，必要时仅执行一次 legacy import。
4. 注入 FileBlobStore、本地 Worker host 和 RAG consumer。

云端宿主：

1. 从部署配置取得 DB/Blob/Provider options。
2. 由发布流程在受锁环境运行 migration；每个 API 实例启动时不竞争迁移。
3. API host 仅装配 submit/query/cancel。
4. Worker host 装配 JobRepository + JobExecutor。
5. RAG host 装配 Outbox Consumer。

当前拒绝隐式文件工作区的约束必须保留。

## 12. 实施阶段

### 阶段 A：收口存储迁移

1. SqlVideoWorkspace 依赖 BlobStore Protocol。
2. 增加真实 MySQL 集成测试，覆盖 SQL workspace、legacy import、SQL generation adapter。
3. 修复 diff check 发现的尾随空白问题，再把存储迁移形成可审查提交。
4. 明确 legacy import 状态机：not_started、running、succeeded、failed；失败保存诊断，不允许静默覆盖重跑。

### 阶段 B：持久 Job Repository

1. 增加 job_attempts migration。
2. 实现 submit、idempotency、active key、claim、renew lease、cancel、append event、complete、fail、retry。
3. 演进现有 SqlControlPlaneRepository，避免新增第二套 Job 代码。
4. SqlCurrentContentRepository.publish 接收 Job lease context。

### 阶段 C：第一个 Worker 和 API 切换

1. 先迁移 generate_summary，复用已有 SQL generation adapter 与临时目录工作流。
2. POST generate 改为 202 Job 提交，不长期维护同步/异步双语义。
3. 生成 SSE/status 改读 job_events。
4. 取消 API 改为持久取消请求，删除进程内 activity checker 的正确性职责。

### 阶段 D：Outbox 和 RAG

1. 增加 outbox_deliveries、consumer claim/retry。
2. 用 Outbox Consumer 替换 WorkspaceIndexRefresher 的正确性职责。
3. 持久 rag_index_entries，实现可恢复 rebuild_rag Job。

### 阶段 E：其余任务和清理

1. 迁移下载、导图、卡片、AI 概括、系列生成和导出。
2. 明确模型下载是否只属于本机运行时，不混入 Workspace Job。
3. 实现 staging/orphan/export/cache 的 cleanup Job。

### 阶段 F：多实例发布验收

1. 两个 API、两个 Worker、一个 RAG Consumer，共享 MySQL 和 BlobStore。
2. 运行故障测试矩阵。
3. 验证旧版本升级、迁移失败恢复、备份恢复、向量索引重建。
4. 通过验收后删除所有旧内存正确性链路。

## 13. 验收测试矩阵

| 场景 | 必须断言 |
| --- | --- |
| 相同 idempotency key/body 重复提交 | 返回同一 job_id，只产生一次有效发布。 |
| 相同 key、不同 body | 返回 409，原 Job 不受影响。 |
| 两 Worker 同时 claim | 仅一个获得 lease。 |
| Worker 生成中崩溃 | lease 过期后新 attempt 可恢复；旧 attempt 不能发布。 |
| DB 发布前崩溃 | 当前内容保持旧版本，staging 不可读。 |
| DB 发布后、清理前崩溃 | 新内容可读，cleanup 最终回收临时对象。 |
| 内容发布后、RAG 前崩溃 | 内容成功，outbox 最终驱动 RAG。 |
| 取消与发布竞争 | 取消先提交则不发布；不得产生假 cancelled 成功。 |
| 两用户编辑同一内容 | 一个成功，一个 409，无静默覆盖。 |
| Blob commit 成功、DB 失败 | Blob 可标 orphan 并最终清理。 |
| DB 成功、Blob materialize 失败 | Job 可重试/失败，不破坏已发布内容。 |
| 向量库全部删除 | rebuild_rag 可从 SQL rag_chunks 恢复。 |
| API 重启 | Job 查询与 SSE 可返回真实历史。 |
| Worker 重启 | 活跃任务按 lease 恢复，不能重复发布。 |
| 跨 workspace 请求 | 不泄露 Job、Blob 或 RAG 内容。 |

测试分层：

- 单元：状态机、重试分类、请求 hash、lease 条件、Blob key 安全、RAG 幂等。
- MySQL 集成：真实事务、唯一键竞争、SKIP LOCKED、过期 lease、原子发布。
- 本地 E2E：受管 MySQL + FileBlobStore + API + 同进程 Worker。
- 多进程 E2E：两个 API、两个 Worker、一个 Consumer，共享 DB/Blob。
- 故障注入：在外部 I/O 与 DB commit 边界终止进程后验证恢复。

## 14. 完成定义

只有以下条件全部满足，才可称“Core 已实现云端化基础”：

1. 所有长任务 API 返回 Job，不直接执行生成。
2. 多个 Worker 共享 Job 表领取，Worker 崩溃后可恢复。
3. 进度、取消和失败信息在 API 重启后仍可查询与 SSE 重连。
4. 内容发布、Job 成功、content_published 在一个 DB 事务中发生。
5. RAG 由持久 Outbox 最终一致更新，可从 SQL 重建。
6. 生成正确性不依赖 InMemoryProgressTracker、Python keyed lock 或 API 容器 activity set。
7. BlobStore 通过 Port 注入，本地与对象存储 adapter 通过同一契约测试。
8. 重复、lease 丢失、发布边界崩溃、取消竞争、对象孤儿和索引丢失均有自动化覆盖。

## 15. 实施约束

- 不添加 SQLite/JSON 回退模式；缺少 SQL workspace 必须明确失败。
- 不为迁移保留长期双写。
- 不将 JobRepository 或 OutboxRepository 泛化成与业务无关的框架；只覆盖明确 operation 和事件。
- 不在 API 请求中扫描、修复或推断旧 workspace 目录。
- 不以“本地单进程可用”为理由绕开 lease、幂等、条件更新或持久事件。
