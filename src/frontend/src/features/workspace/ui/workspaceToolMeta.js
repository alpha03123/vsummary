import {
  BrainCircuit,
  FileText,
  FolderKanban,
  ListChecks,
  Network,
  PlaySquare,
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
    "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-accent/5 dark:hover:bg-accent/10 hover:border-accent/30 transition-all",
  iconShell: "bg-accent/10 text-accent border border-accent/20",
  arrowShell:
    "bg-stone-50 text-stone-500 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-accent group-hover:text-white group-hover:border-accent/80",
};

export const TOOL_TILES = {
  "ai-chat": {
    label: "AI 对话",
    description: "围绕当前视频提问与协作",
    icon: MessageSquare,
    ...SHARED_TOOL_VISUALS,
  },
  overview: {
    label: "AI 概况",
    description: "章节与关键结论",
    icon: FileText,
    ...SHARED_TOOL_VISUALS,
  },
  mindmap: {
    label: "思维导图",
    description: "结构化知识图谱",
    icon: Network,
    ...SHARED_TOOL_VISUALS,
  },
  "knowledge-cards": {
    label: "知识卡片",
    description: "原子知识、标签与来源锚点",
    icon: BrainCircuit,
    ...SHARED_TOOL_VISUALS,
  },
  notes: {
    label: "笔记",
    description: "手记与 Agent 记录",
    icon: StickyNote,
    ...SHARED_TOOL_VISUALS,
  },
  preview: {
    label: "视频预览",
    description: "查看原始视频内容",
    icon: PlaySquare,
    ...SHARED_TOOL_VISUALS,
  },
};

export const SERIES_TOOL_TILES = {
  "series-overview": {
    label: "全局 AI 概况",
    description: "集中查看各视频 AI 概况",
    icon: FileText,
    ...SHARED_TOOL_VISUALS,
  },
  "series-mindmap": {
    label: "全局思维导图",
    description: "结构化展现系列知识脉络",
    icon: Network,
    ...SHARED_TOOL_VISUALS,
  },
};

export const SERIES_STUDIO_TOOL_TILES = {
  "ai-chat": TOOL_TILES["ai-chat"],
  "series-overview": SERIES_TOOL_TILES["series-overview"],
  "series-mindmap": SERIES_TOOL_TILES["series-mindmap"],
};

const DEFAULT_TOOL_META = {
  label: "工具页",
  description: "当前工具信息正在同步",
  icon: FileText,
  palette: "workspace-panel border text-stone-900 dark:text-stone-100 transition-all",
  iconShell: "bg-stone-100 text-stone-700 dark:bg-stone-900 dark:text-stone-300 border border-stone-100 dark:border-stone-800",
  arrowShell: "bg-stone-50 text-stone-700 dark:bg-stone-900 dark:text-stone-300",
};

export const SOURCE_MISSING_STATUS = { label: "需先链接媒体", tone: "blocked" };

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
  if (!toolState) {
    return { label: "读取中", tone: "loading" };
  }
  if (toolState.status === "source_missing") {
    return SOURCE_MISSING_STATUS;
  }
  if (toolId === "preview") {
    return { label: "随时可查看", tone: "ready" };
  }
  if (toolId === "notes") {
    return { label: toolState.generated ? "可记录与整理" : "可立即使用", tone: "ready" };
  }
  if (toolState.generated) {
    return { label: "已生成", tone: "ready" };
  }
  if (toolState.available === false) {
    return { label: "需先生成 AI 概况", tone: "blocked" };
  }
  return { label: "点击进入后生成", tone: "pending" };
}

export function getToolState(tools, toolId) {
  if (!tools) {
    return null;
  }
  if (toolId === "knowledge-cards") {
    return tools.knowledgeCards ?? null;
  }
  return tools[toolId] ?? null;
}

export function getToolMeta(toolId) {
  return TOOL_TILES[toolId] ?? SERIES_TOOL_TILES[toolId] ?? null;
}

export function resolveToolMeta(toolId) {
  return getToolMeta(toolId) ?? DEFAULT_TOOL_META;
}
