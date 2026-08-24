# Issue #7: Bilibili 浏览器扩展规格

- Issue: [#7 feat: 添加浏览器插件用于总结](https://github.com/alpha03123/vsummary/issues/7)
- 状态: Draft
- 范围: Chrome Manifest V3 Side Panel 扩展与现有本地 vsummary 后端的集成

## 1. 目标

用户在 Bilibili 的视频播放页打开扩展侧边栏，可将当前视频交给本机 vsummary
处理，并在同一侧边栏内查看该视频的处理进度和最终总结。

扩展是单视频投递与结果回显入口，不是第二个 vsummary 工作区。视频下载、转写、
总结、产物持久化和任务进度均复用现有后端链路。

## 2. 非目标

- 不在扩展中提供系列创建、选择、管理或批量处理。
- 不在扩展中编辑模型、ASR、Cookie 或工作区配置。
- 不因进入页面、URL 变化或打开侧边栏自动下载或开始处理视频。
- 不在扩展中解析 Bilibili 播放器 DOM、提取媒体流或实现下载逻辑。
- 不新增一套与现有视频库平行的任务、存储或总结模型。

## 3. 数据归属与唯一性

所有由扩展投递的 Bilibili 视频进入固定的内置 Series：

```text
series_id: bilibili
title: B站导入
kind: bilibili_inbox
is_system: true
provider: bilibili
```

该 Series 在后端初始化时确保存在，并具备现有 Agent 单视频处理所需的属性。扩展
始终传递 `target_series_id: "bilibili"`；扩展 UI 不向用户暴露 Series 概念。

视频的业务唯一键为 `bvid + page`。同一个 BV 可以有多个分 P，`BVxxxx?p=1` 与
`BVxxxx?p=2` 必须作为不同视频处理。后端若能从 Bilibili 元数据获得稳定 `cid`，可
将其作为内部唯一键的一部分；URL 原文、标题和短链均不得作为唯一键。

`bilibili` 是稳定的存储和路由标识；前端展示特殊样式必须依据后端返回的
`kind: "bilibili_inbox"`，不散落 `id === "bilibili"` 判断。

## 4. 启用范围

扩展仅在可处理的 Bilibili 视频页启用 Side Panel：

- `https://www.bilibili.com/video/*`
- `https://www.bilibili.com/bangumi/play/*`

非视频页不启用，不显示空白的“总结”界面。Bilibili 是 SPA，扩展须监听活动标签 URL
和页面内路由变化，及时重新计算当前视频身份。

短链或跳转页在最终落到上述播放页后才启用。首期不支持直播、动态、收藏夹、搜索
结果、合集页或 UP 主页。

## 5. 侧边栏体验

### 5.1 页面识别

扩展从当前标签 URL 提取候选 BVID 与页码，仅用于决定是否可用和作为后端请求输入。
后端在处理前重新解析 URL，后端解析结果才是标题、封面、页码和视频身份的权威来源。

打开侧边栏、切换到新的可处理视频或上一次健康状态过期时，扩展后台检查
`GET /api/health`。建议缓存 30 秒；不做全局高频轮询。

### 5.2 状态

| 状态 | 侧边栏行为 |
| --- | --- |
| 后端不可达 | 显示本机服务不可用及重试操作，不允许提交。 |
| 后端可达且视频不存在 | 显示当前视频和“开始总结”操作。 |
| 已入库、未处理 | 显示“开始总结”。 |
| 下载/转写/生成中 | 恢复并显示既有任务进度；禁止重复提交。 |
| 已完成 | 回显概况摘要、章节入口和“在 vsummary 中打开”操作。 |
| 失败 | 显示后端返回的可读错误和“重试”操作。 |

同一 `bvid + page` 再次进入时，必须恢复该视频的既有状态，而不是新建视频或重新
下载。用户显式点击“重试”时才允许重新调度失败任务。

## 6. 后端复用流程

扩展按下列顺序调用现有 API；不新增独立的扩展处理流水线：

```text
当前 Bilibili URL
  -> GET /api/health
  -> GET /api/videos，定位 series_id=bilibili 下 bvid + page 对应的视频
  -> 未命中时 POST /api/linked/bilibili/resolve/video
       { url, target_series_id: "bilibili" }
  -> POST /api/agent/series/bilibili/process
       { video_ids: [video_id] }
  -> GET /api/videos/bilibili/{video_id}/generate/progress
  -> GET /api/videos/bilibili/{video_id}/summary
```

解析接口必须满足幂等性：同一个 `target_series_id + bvid + page` 已存在时，返回既有
`VideoCardResponse`，不得追加重复视频。扩展可在调用解析前先查询视频库，后端仍需
保证该约束，以消除多标签页并发提交造成的重复。

已有视频已处理完成时，不调用 process，直接读取摘要。已有视频处理中时，不重复
调用 process，直接订阅现有进度。`409`、下载错误、Cookie 缺失、ASR 未就绪和 LLM
配置错误均原样转换为侧边栏的失败状态，不在扩展中绕过或模拟成功。

进度结束为 `completed` 后，再请求 summary；summary 不存在或请求失败即视为任务失败，
不能只依据 SSE 连接结束声明完成。

## 7. API 与跨域约束

首期沿用现有 `/api/health`、`/api/videos`、Bilibili resolve、Agent process、生成进度
及 summary 接口。仅在现有 API 无法表达以下约束时，再增加目标明确的接口：

- 按 `series_id + bvid + page` 查询单视频，避免扩展拉取完整视频库；
- 返回扩展所需的单视频状态快照。

新增接口必须是现有视频库查询/编排接口的薄适配，不复制下载、生成或存储逻辑。

扩展声明最小化的 Bilibili host permissions 与本机 vsummary 服务 host permission。
本机 API 应要求扩展专用配对令牌或等价的来源认证；健康检查可保持最小、无敏感信息的
响应。不得为了扩展访问而将所有本机 API 无条件暴露给任意网页来源。

## 8. 主程序展示

主程序视频库将 `kind: bilibili_inbox` 作为专属来源展示，例如“B站导入”图标与排序。
其中视频仍使用普通视频阅读、概况、转写、思维导图和导出能力，不产生特例工作区。

扩展的“在 vsummary 中打开”应跳转到 `bilibili` Series 内对应 `video_id` 的既有工作区
路由，而不是另建详情页。

## 9. 验收标准

1. 在支持的 Bilibili 视频页可打开侧边栏；非视频页不启用。
2. 后端未运行时，扩展只显示不可用状态，且不会发起解析或处理请求。
3. 用户点击“开始总结”后，当前视频仅进入 `bilibili` Series，不创建新 Series。
4. 同一 `bvid + page` 重复点击、刷新页面或多标签页提交，库中只保留一个视频记录。
5. 同一 BV 的不同分 P 可各自处理、查看进度和回显结果。
6. 关闭并重新打开侧边栏，或重新进入同一视频页，可恢复处理中或已完成状态。
7. SSE 结束后必须成功读取 summary 才显示完成。
8. Bilibili Cookie、下载、ASR 或 LLM 配置失败时，侧边栏展示后端失败原因且允许显式重试。
9. 主程序中 `bilibili` Series 有专属来源展示，但其中视频保持普通工作区能力。
