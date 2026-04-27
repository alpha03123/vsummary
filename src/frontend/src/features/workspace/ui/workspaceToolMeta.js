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

export const TOOL_TILES = {
  "chat-management": {
    label: "对话管理",
    description: "用于切换会话记录",
    icon: MessageSquare,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-accent/5 dark:hover:bg-accent/10 hover:border-accent/30 transition-all",
    iconShell: "bg-accent/10 text-accent border border-accent/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-accent group-hover:text-white group-hover:border-accent/80",
  },
  overview: {
    label: "AI概况",
    description: "章节与关键结论",
    icon: FileText,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-accent/5 dark:hover:bg-accent/10 hover:border-accent/30 transition-all",
    iconShell: "bg-accent/10 text-accent border border-accent/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-accent group-hover:text-white group-hover:border-accent/80",
  },
  mindmap: {
    label: "思维导图(beta)",
    description: "结构化知识图谱",
    icon: Network,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-accent/5 dark:hover:bg-accent/10 hover:border-accent/30 transition-all",
    iconShell: "bg-accent/10 text-accent border border-accent/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-accent group-hover:text-white group-hover:border-accent/80",
  },
  "knowledge-cards": {
    label: "知识卡片(beta)",
    description: "原子知识、标签与来源锚点",
    icon: BrainCircuit,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-accent/5 dark:hover:bg-accent/10 hover:border-accent/30 transition-all",
    iconShell: "bg-accent/10 text-accent border border-accent/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-accent group-hover:text-white group-hover:border-accent/80",
  },
  notes: {
    label: "笔记",
    description: "手记与 Agent 记录",
    icon: StickyNote,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-accent/5 dark:hover:bg-accent/10 hover:border-accent/30 transition-all",
    iconShell: "bg-accent/10 text-accent border border-accent/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-accent group-hover:text-white group-hover:border-accent/80",
  },
  preview: {
    label: "视频预览",
    description: "查看原始视频内容",
    icon: PlaySquare,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-accent/5 dark:hover:bg-accent/10 hover:border-accent/30 transition-all",
    iconShell: "bg-accent/10 text-accent border border-accent/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-accent group-hover:text-white group-hover:border-accent/80",
  },
};

export const SERIES_TOOL_TILES = {
  "series-chat-management": {
    label: "对话管理",
    description: "用于切换会话记录",
    icon: MessageSquare,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-accent/5 dark:hover:bg-accent/10 hover:border-accent/30 transition-all",
    iconShell: "bg-accent/10 text-accent border border-accent/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-accent group-hover:text-white group-hover:border-accent/80",
  },
  "series-mindmap": {
    label: "全局思维导图",
    description: "结构化展现系列知识脉络 (暂未实现)",
    icon: Network,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-accent/5 dark:hover:bg-accent/10 hover:border-accent/30 transition-all",
    iconShell: "bg-accent/10 text-accent border border-accent/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-accent group-hover:text-white group-hover:border-accent/80",
  },
};

const DEFAULT_TOOL_META = {
  label: "工具页",
  description: "当前工具信息正在同步",
  icon: FileText,
  palette: "workspace-panel border text-stone-900 dark:text-stone-100 transition-all",
  iconShell: "bg-stone-100 text-stone-700 dark:bg-stone-900 dark:text-stone-300 border border-stone-100 dark:border-stone-800",
  arrowShell: "bg-stone-50 text-stone-700 dark:bg-stone-900 dark:text-stone-300",
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

export function resolveToolMeta(toolId) {
  return getToolMeta(toolId) ?? DEFAULT_TOOL_META;
}
