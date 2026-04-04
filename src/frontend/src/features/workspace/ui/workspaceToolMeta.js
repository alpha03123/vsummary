import {
  BrainCircuit,
  FileText,
  FolderKanban,
  ListChecks,
  Network,
  PlaySquare,
  StickyNote,
} from "lucide-react";

export const TOOL_TILES = {
  overview: {
    label: "AI概况",
    description: "章节与关键结论",
    icon: FileText,
    palette: "workspace-muted-panel border text-stone-900 dark:text-stone-100 hover:border-sky-300/70 dark:hover:border-sky-700/70",
    iconShell: "bg-sky-100 text-sky-700 dark:bg-sky-950/30 dark:text-sky-300 border border-sky-100 dark:border-sky-900/50",
    arrowShell: "bg-sky-50 text-sky-700 dark:bg-sky-950/20 dark:text-sky-300",
  },
  mindmap: {
    label: "思维导图",
    description: "结构化知识图谱",
    icon: Network,
    palette: "workspace-muted-panel border text-stone-900 dark:text-stone-100 hover:border-violet-300/70 dark:hover:border-violet-700/70",
    iconShell: "bg-violet-100 text-violet-700 dark:bg-violet-950/30 dark:text-violet-300 border border-violet-100 dark:border-violet-900/50",
    arrowShell: "bg-violet-50 text-violet-700 dark:bg-violet-950/20 dark:text-violet-300",
  },
  "knowledge-cards": {
    label: "知识卡片",
    description: "原子知识、标签与来源锚点",
    icon: BrainCircuit,
    palette: "workspace-muted-panel border text-stone-900 dark:text-stone-100 hover:border-amber-300/70 dark:hover:border-amber-700/70",
    iconShell: "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300 border border-amber-100 dark:border-amber-900/50",
    arrowShell: "bg-amber-50 text-amber-700 dark:bg-amber-950/20 dark:text-amber-300",
  },
  notes: {
    label: "笔记",
    description: "手记与 Agent 记录",
    icon: StickyNote,
    palette: "workspace-muted-panel border text-stone-900 dark:text-stone-100 hover:border-rose-300/70 dark:hover:border-rose-700/70",
    iconShell: "bg-rose-100 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300 border border-rose-100 dark:border-rose-900/50",
    arrowShell: "bg-rose-50 text-rose-700 dark:bg-rose-950/20 dark:text-rose-300",
  },
  preview: {
    label: "视频预览",
    description: "查看原始视频内容",
    icon: PlaySquare,
    palette: "workspace-muted-panel border text-stone-900 dark:text-stone-100 hover:border-emerald-300/70 dark:hover:border-emerald-700/70",
    iconShell: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300 border border-emerald-100 dark:border-emerald-900/50",
    arrowShell: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-300",
  },
};

export const SERIES_TOOL_TILES = {
  "series-overview": {
    label: "系列概览",
    description: "理解整个 series 的覆盖范围",
    icon: FolderKanban,
    palette: "workspace-muted-panel border text-stone-900 dark:text-stone-100 hover:border-sky-300/70 dark:hover:border-sky-700/70",
    iconShell: "bg-sky-100 text-sky-700 dark:bg-sky-950/30 dark:text-sky-300 border border-sky-100 dark:border-sky-900/50",
    arrowShell: "bg-sky-50 text-sky-700 dark:bg-sky-950/20 dark:text-sky-300",
  },
  "series-progress": {
    label: "系列进度",
    description: "查看处理状态和视频分布",
    icon: ListChecks,
    palette: "workspace-muted-panel border text-stone-900 dark:text-stone-100 hover:border-emerald-300/70 dark:hover:border-emerald-700/70",
    iconShell: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300 border border-emerald-100 dark:border-emerald-900/50",
    arrowShell: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-300",
  },
};

export function describeToolState(toolId, toolState) {
  if (!toolState) {
    return "读取中";
  }
  if (toolId === "preview") {
    return "随时可查看";
  }
  if (toolId === "notes") {
    return toolState.generated ? "可记录与整理" : "可立即使用";
  }
  if (toolState.generated) {
    return "已生成";
  }
  if (toolState.available === false) {
    return "需先生成 AI 概况";
  }
  return "点击进入后生成";
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
