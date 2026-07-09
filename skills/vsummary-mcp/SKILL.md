---
name: vsummary-mcp
description: Use when 使用 VSummary 本地 MCP 服务处理视频系列，包括创建 agent 管理的 series、导入 Bilibili URL 或本地视频/音频文件路径、启动处理、查询进度、导出摘要/字幕/混合 Markdown，以及清理 MCP 创建的 series。
---

# VSummary MCP

## 概览

`vsummary-video-series` MCP server 是本地 VSummary 后端上的一层薄工具封装。使用时保持链路简单：创建或导入 series，添加 Bilibili URL 或本地媒体文件路径，启动处理，轮询状态，最后导出 Markdown 文本。

当用户明确要求测试或使用 MCP 时，不要绕过 MCP 直接调用后端 HTTP API。MCP server 内部会调用后端，所以日志里出现后端 URL 是正常的，但任务动作仍应通过 MCP tools 完成。

## 推荐流程

1. 先调用 `get_project_status`，确认后端是否可用，以及当前 library/series 状态。
2. 处理 Bilibili URL 时，调用 `create_series` 创建空的 agent-managed linked series，再调用 `add_series_videos` 把 URL 添加到这个 series。
3. 处理本地视频/音频时，调用 `import_local_series(title, file_paths=[...])` 从本地文件路径创建新 series，或调用 `add_local_series_videos(series_id, file_paths=[...])` 把本地媒体追加到已有本地 series。
4. 调用 `process_series` 启动处理。默认把 series 当成组织单位；只有用户明确要求处理部分视频时才传 `video_ids`。
5. 轮询 `get_series_status`，直到 `overall_status` 变成 `completed`、`failed` 或 `cancelled`。
6. 调用 `export_series` 导出 Markdown。除非用户指定其他类型，默认使用 `kind="mixed"`。
7. 只有用户明确要求删除或清理时，才调用 `delete_series`。

## 工具语义

- `get_project_status(include_series=true)`：检查后端健康状态，并可选返回当前 series 概览。
- `create_series(title)`：创建一个给 agent/MCP 使用的空 linked series。创建结果会带 `is_agent_managed=true`。
- `add_series_videos(series_id, videos=[{"url": "..."}])`：解析并添加 Bilibili 视频 URL。失败按 URL 单独返回，不要默认认为整个批次都失败。
- `import_local_series(title, file_paths=["C:/path/video.mp4", ...])`：通过后端上传已有本地视频/音频文件并创建新的本地 series。MCP server 从本机文件系统读取路径，并转发给后端 multipart 导入接口。
- `add_local_series_videos(series_id, file_paths=["C:/path/audio.mp3", ...])`：通过后端上传已有本地视频/音频文件，并追加到已有本地 series。
- `process_series(series_id, video_ids=None, run_id=None, transcript_enhancement_enabled=None, wait=false)`：启动处理。默认 `wait=false`，也就是只调度任务并快速返回。
- `get_series_status(series_id, video_ids=None)`：读取 series 总体进度和每个视频的进度。这是 agent 查询处理进度的主接口。
- `export_series(series_id, kind="mixed", video_ids=None)`：返回 Markdown 文本，不写入文件。
- `delete_series(series_id)`：通过后端删除 series 及其 workspace 产物。只在用户明确要求时使用。

识别 MCP/agent 创建的 series 时，使用 `is_agent_managed` 字段，不要依赖标题命名规则或 `source_url`。

本地媒体格式由后端校验。当前支持的视频后缀包括 `.mp4`、`.mov`、`.mkv`、`.avi`、`.webm`、`.m4v`，音频后缀包括 `.mp3`、`.wav`、`.m4a`、`.aac`、`.flac`、`.ogg`、`.opus`、`.wma`。

## 进度判断

以 `overall_status` 为准：

- `processing` 或 `running`：继续轮询。
- `completed`：可以导出已处理视频。
- `failed`：报告 `series_generation.error` 或单个视频的 `generation.error`。
- `cancelled`：报告已取消，不要自动重试，除非用户要求。
- `pending`：当前没有可见的活动处理。如果刚启动处理后立刻看到 `pending`，再轮询一两次，不要马上判定为空闲。

Linked Bilibili 视频会先下载再生成。`yt-dlp` 下载期间，library 里可能短暂出现 `.f100026`、`.f30280` 这类临时媒体分片。不要把它们当成用户添加的视频；等待下载完成后，最终视频列表会恢复稳定。

本地媒体导入要求文件路径能被本地 MCP server 进程读取。如果路径不存在、不可访问或指向目录，直接报告路径问题，不要绕过 MCP 去调用原始后端 HTTP API。

## 导出行为

`export_series` 返回 Markdown 字符串，不创建本地文件。结果里每个被选中的视频都有一项：

```json
{
  "series_id": "agent-example",
  "kind": "mixed",
  "exported_count": 2,
  "failed_count": 0,
  "items": [
    {
      "video_id": "BV...",
      "status": "exported",
      "markdown": "# BV...\n\n..."
    }
  ]
}
```

如果用户需要文件，由 agent 在导出后把返回的 Markdown 写入工作区。写入路径应由用户指定，或使用清晰的项目内路径。不要假设 `export_series` 已经生成了文件。

## 失败处理

- 如果 Bilibili URL 解析返回 cookie 或 412 错误，说明后端 Bilibili 登录/Cookie 状态需要修复。
- 如果本地媒体导入返回不支持格式或重复媒体名，直接报告后端错误，并要求用户换文件或换目标 series。
- 如果处理卡在下载阶段，先看 status 是否仍显示正在下载 linked video；较大的 Bilibili 视频可能需要数分钟。
- 如果处理卡在 `progress=88` 附近，并且 detail 类似正在生成 AI summary，通常是在等待配置的 LLM 调用返回。
- 如果出现 CUDA DLL 错误，问题来自后端 ASR runtime，不是 MCP 本身。MCP 只负责调用后端。
- 如果用户明确要求 MCP 测试，除启动后端、进程管理或必要健康检查外，不要直接调用后端 HTTP endpoint。

## 后端假设

MCP server 需要一个正在运行的 VSummary 后端，并读取 `VSUMMARY_BACKEND_URL`。默认值是 `http://127.0.0.1:8000`。本地开发中这个项目常用 `http://127.0.0.1:8001`。

在 Windows 上自行启动后端时，优先使用项目环境和 `start.bat` 的 PATH 形态：conda env 根目录、`Library\bin`、`Scripts` 都应在 `PATH` 前面，然后再启动 `backend.api.http.server`。
