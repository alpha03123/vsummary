# Core 宿主接口

当前版本：`vsummary-core==0.5.0a28`。

## 视频获取扩展

`build_host_container(linked_video_resolvers=..., linked_video_downloaders=...)` 接收按 provider
命名的宿主适配器。解析端口是 `LinkedVideoResolver`，下载端口是 `LinkedVideoDownloader`；
API 预览/导入、后台下载和 Agent 视频处理共用这些适配器。下载返回临时文件路径，
后续 BlobStore、转录、生成和 RAG 更新仍由 Core 处理，宿主不能绕过工作区权限和持久化。

yt-dlp 适配器的 `cookie=None` 保留 Local 的匿名优先、认证失败后重试配置 Cookie 的行为；
`cookie=""` 明确只尝试匿名，非空值明确只尝试该 Cookie。宿主可组合自己的获取策略，
无需改写进程环境变量。Core 不依赖 TikHub，也不包含第三方获取服务的密钥。

`UsageEstimate` / `UsageRecord` 导出 `multimodal_enabled` 计费特征；宿主可通过 `multimodal_estimate` 回调提供每次任务的有效设置，结算从提交时的预估快照读取该特征。Core 不包含积分倍率或价格。

宿主可向 `build_host_container(job_queue_policy=...)` 注入 `backend.core.job_queue.SqlJobQueuePolicy`，在同一服务器的 API/Worker 之间共用锁文件，提供提交容量限制和按账号公平领取。Local 默认不启用此策略。`WorkerOptions.concurrency` 控制执行线程数，默认 1；`maintenance_seconds` 默认 5 秒，让系列收尾和结算恢复独立于长任务运行。本版本不增加数据库迁移。

## 装配与隔离

`backend.api.di.bootstrap.build_host_container()` 接收 SQL session、宿主配额、偏好、模型预设、
资源预算和可选聊天队列。`SqlWorkspaceServicesProvider` 按 workspace 构建服务，
`build_worker_host()` 独立运行任务与 Outbox。API 与 worker 绑定同一 `WorkspaceContext`。
身份认证和成员关系由宿主处理。Core wheel 不含 Local 路由。

## 偏好与计量

`backend.core` 导出 `USER_OVERRIDABLE`、`UserPreferences`、`UserPreferenceStore`、
`UsageEstimate`、`UsageRecord`、`ResourceUsage`、`ResourceBudget`、`SqlChatQueue` 等契约。
白名单仅开放多模态概括、自动制品、回复长度和服务端模型档位。密钥、端点、ASR、检索模型与
并发预算保持部署级；Local 未接入覆盖存储时沿用原设置。

任务保存提交时偏好，提供真实时长、输入/输出 Token 与批量子任务计量。
宿主定义积分规则；Core 支持预留、结算、释放与失败重试。外部调用通过资源预算单独计量。

`GET /api/preferences`、`PUT /api/preferences` 仅在宿主接入偏好存储时开放。
`GET /api/jobs`、`GET /api/jobs/stats` 按账号/workspace 查询。
聊天队列提供公平准入、租约、取消与结算，SSE 使用 `queue` 事件。
`/api/provider-settings/usage` 返回账号/workspace 的真实 LLM Token 用量。

## 独立产物与宿主清理

产物读取与编辑校验视频元数据，不以原媒体文件存在作为资源存在条件。
`SqlVideoWorkspace.get_video_title()`、`save_generated_artifact()`、`get_saved_visual_paths()`
用于独立保存、读取产物与图片。导图生成消费标题和已有内容，不再为了取标题而读取原视频。

`SqlWorkspaceServicesProvider(media_preview_enabled=False)` 关闭宿主预览派生文件。
`build_worker_host(..., maintenance=...)` 接收宿主维护回调。Cloud 在视频任务全部终态且没有
并行工作时提交图片、检查引用，再删除原媒体与处理目录。缺失图片引用时停止删除并报告错误。
Core 不默认删除 Local 原媒体；Local 媒体预览能力保持启用。

部署前先迁移到 `0020_host_execution_contracts`。本次独立产物改动不新增数据库迁移。

## 系列批任务

系列父任务会创建视频子任务后进入 `waiting_children`。只有全部子任务进入成功、失败或取消的
终态后，父任务才收敛为成功、失败或取消。取消请求保持父任务的 `cancelling` 状态，直至全部
子任务终态；重复取消返回当前持久状态。

系列估算包含每个待处理视频的时长、已有转录状态和模型档位。配额宿主可以在创建父任务时一次性
预留整批预算，并在父任务终态按所有子任务的实际计量结算。



