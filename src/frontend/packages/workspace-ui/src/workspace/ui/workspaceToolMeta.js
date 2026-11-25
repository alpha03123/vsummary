import {
  BrainCircuit,
  CalendarDays,
  FileText,
  FolderKanban,
  ListChecks,
  Network,
  PlaySquare,
  Presentation,
  StickyNote,
  MessageSquare,
} from "lucide-react";

/**
 * Shared visual styling for every tool tile.
 *
 * Previously each of the 8 tiles repeated the same `palette` / `iconShell` /
 * `arrowShell` strings verbatim (~1.4 KB of duplication). They are now sourced
 * from a single object so the look-and-feel of tool tiles can be tuned in one
 * place. Tile entries only declare their semantic identity (label/description/icon).
 */
const SHARED_TOOL_VISUALS = {
  palette:
    "workspace-panel border hover:border-accent/30 hover:bg-accent/5 dark:hover:bg-accent/10",
  iconShell: "bg-accent/10 text-accent",
};

// Order is reading order for a new user: the summary first, then what builds on it.
export const TOOL_TILES = {
  "ai-summary": {
    label: "AI 概括",
    description: "章节要点与学习笔记",
    icon: ListChecks,
    ...SHARED_TOOL_VISUALS,
  },
  overview: {
    label: "逐字稿",
    description: "带时间点的完整原文",
    icon: FileText,
    ...SHARED_TOOL_VISUALS,
  },
  mindmap: {
    label: "思维导图",
    description: "按章节梳理知识结构",
    icon: Network,
    ...SHARED_TOOL_VISUALS,
  },
  "knowledge-cards": {
    label: "知识卡片",
    description: "知识点与原文出处",
    icon: BrainCircuit,
    ...SHARED_TOOL_VISUALS,
  },
  courseware: {
    label: "视频课件",
    description: "提取 PPT 与板书",
    badge: "Beta",
    icon: Presentation,
    ...SHARED_TOOL_VISUALS,
  },
  "study-plan": {
    label: "学习计划",
    description: "按天安排学习进度",
    badge: "Beta",
    icon: CalendarDays,
    ...SHARED_TOOL_VISUALS,
  },
  "ai-chat": {
    label: "AI 对话",
    description: "就当前视频提问",
    icon: MessageSquare,
    ...SHARED_TOOL_VISUALS,
  },
  notes: {
    label: "我的笔记",
    description: "记录自己的笔记",
    icon: StickyNote,
    ...SHARED_TOOL_VISUALS,
  },
  preview: {
    label: "视频预览",
    description: "播放原视频",
    icon: PlaySquare,
    ...SHARED_TOOL_VISUALS,
  },
};

export const SERIES_TOOL_TILES = {
  "series-overview": {
    label: "全局 AI 概括",
    description: "各视频 AI 概括汇总",
    icon: FileText,
    ...SHARED_TOOL_VISUALS,
  },
  "series-mindmap": {
    label: "全局思维导图",
    description: "整个系列的知识脉络",
    icon: Network,
    ...SHARED_TOOL_VISUALS,
  },
  "series-study-plan": {
    label: "课程学习计划",
    description: "按天安排整门课程",
    badge: "Beta",
    icon: CalendarDays,
    ...SHARED_TOOL_VISUALS,
  },
};

export const SERIES_STUDIO_TOOL_TILES = {
  "series-overview": SERIES_TOOL_TILES["series-overview"],
  "series-mindmap": SERIES_TOOL_TILES["series-mindmap"],
  "series-study-plan": SERIES_TOOL_TILES["series-study-plan"],
  "ai-chat": TOOL_TILES["ai-chat"],
};

const DEFAULT_TOOL_META = {
  label: "全部工具",
  description: "当前工具信息正在同步",
  icon: FileText,
  palette: "workspace-panel border text-strong transition-all",
  iconShell: "bg-soft text-body border border-line-soft",
  arrowShell: "bg-muted text-body",
};

export const SOURCE_MISSING_STATUS = { label: "需先链接媒体", tone: "blocked" };
// One wording for "usable, generates when opened", on video and series tiles alike.
export const NOT_GENERATED_STATUS = { label: "未生成", tone: "pending" };

/**
 * Tool status descriptor — `{ label, tone }`.
 *
 * These tiles used to render a bare grey string in a fixed slot, but that one
 * slot carried four unrelated meanings (a chat session name, "loading", "not
 * generated yet", "generates on click"). Same position, same size, so users
 * could not build an expectation. The status is now an explicit chip whose
 * `tone` makes the four cases visually distinct:
 *
 *   ready   — nothing to do, the tool already has content
 *   pending — usable, will generate on click
 *   blocked — disabled until something else happens
 *   loading — state not resolved yet
 *
 * A missing/unknown state deliberately degrades to `loading` rather than
 * claiming the tool is ready.
 */
export function describeToolState(toolId, toolState) {
  // Chat has no per-video snapshot; it is always usable.
  if (toolId === "ai-chat") {
    return null;
  }
  if (!toolState) {
    return { label: "读取中", tone: "loading" };
  }
  if (toolState.status === "source_missing") {
    return SOURCE_MISSING_STATUS;
  }
  if (toolState.status === "source_released") {
    // Cloud deletes the source after processing; only an import-time choice keeps it for courseware.
    return { label: toolId === "courseware" ? "需导入时勾选" : "原视频已删除", tone: "blocked" };
  }
  if (toolState.status === "audio_only") {
    return { label: "纯音频不支持", tone: "blocked" };
  }
  // Ready is the normal case and shows nothing: a chip on every tile ("已生成", "随时可查看"…)
  // drowned out the ones that need attention.
  if (toolId === "preview" || toolId === "notes" || toolState.generated) {
    return null;
  }
  if (toolState.available === false) {
    if (toolId === "courseware") {
      return { label: "需先下载视频", tone: "blocked" };
    }
    return { label: "需先生成 AI 概括", tone: "blocked" };
  }
  return NOT_GENERATED_STATUS;
}

export function getToolState(tools, toolId) {
  if (!tools) {
    return null;
  }
  if (toolId === "knowledge-cards") {
    return tools.knowledgeCards ?? null;
  }
  if (toolId === "ai-summary") {
    return tools.aiSummary ?? null;
  }
  if (toolId === "study-plan") {
    return tools.studyPlan ?? null;
  }
  return tools[toolId] ?? null;
}

export function getToolMeta(toolId) {
  return TOOL_TILES[toolId] ?? SERIES_TOOL_TILES[toolId] ?? null;
}

export function resolveToolMeta(toolId) {
  return getToolMeta(toolId) ?? DEFAULT_TOOL_META;
}
