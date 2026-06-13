import { findSeriesById, findVideoById } from "./workspaceState";

export function buildAgentChatContextPayload(library, selectedContextType, seriesId, videoId, selectedToolId) {
  if (selectedContextType !== "series" && selectedContextType !== "video") {
    throw new Error("Agent 对话上下文必须是 series 或 video。");
  }
  const activeSeries = findSeriesById(library, seriesId);
  const selectedVideo = findVideoById(library, seriesId, videoId);
  return {
    scope_type: selectedContextType,
    series_id: activeSeries?.id ?? null,
    series_title: activeSeries?.title ?? null,
    video_id: selectedVideo?.id ?? null,
    video_title: selectedVideo?.title ?? null,
    selected_tool: selectedToolId ?? null,
  };
}

export function normalizeAgentToolId(toolId) {
  if (toolId === "video") {
    return "preview";
  }
  if (
    toolId === "series-overview" ||
    toolId === "overview" ||
    toolId === "cards" ||
    toolId === "knowledge-cards" ||
    toolId === "mindmap" ||
    toolId === "notes" ||
    toolId === "preview" ||
    toolId === "series-home"
  ) {
    return toolId;
  }
  return null;
}

export function normalizeAgentToolTraceStep(result) {
  const payload = result?.payload ?? {};
  switch (result?.tool_name) {
    case "list_series_videos":
      return createToolTraceStep(result.tool_name, "读取系列视频列表", payload.series_title ?? payload.series_id);
    case "open_series_overview":
      return createToolTraceStep(result.tool_name, "打开系列概览");
    case "get_video_summary":
      return createToolTraceStep(result.tool_name, "读取视频概况", payload.title ?? payload.video_id);
    case "get_video_tools":
      return createToolTraceStep(result.tool_name, "读取视频工具状态", payload.video_id);
    case "open_series_home":
      return createToolTraceStep(result.tool_name, "打开系列首页");
    case "open_overview":
      return createToolTraceStep(result.tool_name, "打开 AI 概况");
    case "open_mindmap":
      return createToolTraceStep(result.tool_name, "打开思维导图");
    case "open_knowledge_cards":
      return createToolTraceStep(result.tool_name, "打开知识卡片");
    case "open_notes":
      return createToolTraceStep(result.tool_name, "打开笔记");
    case "open_video":
      return createToolTraceStep(result.tool_name, "打开视频预览");
    case "video_seek":
      return createToolTraceStep(
        result.tool_name,
        typeof payload.seek_seconds === "number" ? `定位到 ${formatSeconds(payload.seek_seconds)}` : "定位视频时间点",
      );
    case "generate_overview":
      return createToolTraceStep(result.tool_name, "生成 AI 概况");
    case "generate_mindmap":
      return createToolTraceStep(result.tool_name, "生成思维导图");
    case "save_note":
      return createToolTraceStep(result.tool_name, "保存笔记", payload.note_title);
    case "get_video_transcript":
      return createToolTraceStep(
        result.tool_name,
        typeof payload.result_count === "number" ? "读取转写证据片段" : "读取视频转写全文",
        payload.title ?? payload.video_id,
      );
    default:
      return createToolTraceStep(result?.tool_name ?? "unknown_tool", "执行工作流步骤");
  }
}

export function buildAssistantChatMeta(durationMs, usage = null) {
  const durationLabel = formatDurationLabel(durationMs);
  const tokenLabel = formatTokenUsageLabel(usage);
  if (!durationLabel && !tokenLabel) {
    return "Notebook Assistant • Just now";
  }
  if (durationLabel && tokenLabel) {
    return `Notebook Assistant • 用时 ${durationLabel} • 消耗 ${tokenLabel}`;
  }
  if (durationLabel) {
    return `Notebook Assistant • 用时 ${durationLabel}`;
  }
  return `Notebook Assistant • 消耗 ${tokenLabel}`;
}

export function formatDurationLabel(durationMs) {
  if (typeof durationMs !== "number" || Number.isNaN(durationMs) || durationMs < 0) {
    return "";
  }
  if (durationMs < 1000) {
    return `${durationMs}ms`;
  }
  return `${(durationMs / 1000).toFixed(1)}秒`;
}

export function formatTokenUsageLabel(usage) {
  if (!usage || typeof usage !== "object") {
    return "";
  }
  const totalTokens = typeof usage.total_tokens === "number"
    ? usage.total_tokens
    : typeof usage.totalTokens === "number"
      ? usage.totalTokens
      : null;
  if (typeof totalTokens !== "number" || Number.isNaN(totalTokens) || totalTokens < 0) {
    return "";
  }
  if (totalTokens >= 1000) {
    return `${(totalTokens / 1000).toFixed(1)}k tokens`;
  }
  return `${Math.round(totalTokens)} tokens`;
}

function createToolTraceStep(toolName, label, target = "") {
  return {
    toolName,
    label,
    target: normalizeToolTarget(target),
  };
}

function normalizeToolTarget(value) {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  return value.trim();
}

function formatSeconds(seconds) {
  const totalSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
}
