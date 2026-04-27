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
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-sky-50/50 dark:hover:bg-sky-900/20 hover:border-sky-200 dark:hover:border-sky-700/50 transition-all",
    iconShell: "bg-sky-100 text-sky-600 dark:bg-sky-500/10 dark:text-sky-400 border border-sky-200 dark:border-sky-500/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-sky-500 group-hover:text-white group-hover:border-sky-400 dark:group-hover:bg-sky-500 dark:group-hover:border-sky-400",
  },
  overview: {
    label: "AI概况",
    description: "章节与关键结论",
    icon: FileText,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-sky-50/50 dark:hover:bg-sky-900/20 hover:border-sky-200 dark:hover:border-sky-700/50 transition-all",
    iconShell: "bg-sky-100 text-sky-600 dark:bg-sky-500/10 dark:text-sky-400 border border-sky-200 dark:border-sky-500/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-sky-500 group-hover:text-white group-hover:border-sky-400 dark:group-hover:bg-sky-500 dark:group-hover:border-sky-400",
  },
  mindmap: {
    label: "思维导图(beta)",
    description: "结构化知识图谱",
    icon: Network,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-violet-50/50 dark:hover:bg-violet-900/20 hover:border-violet-200 dark:hover:border-violet-700/50 transition-all",
    iconShell: "bg-violet-100 text-violet-600 dark:bg-violet-500/10 dark:text-violet-400 border border-violet-200 dark:border-violet-500/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-violet-500 group-hover:text-white group-hover:border-violet-400 dark:group-hover:bg-violet-500 dark:group-hover:border-violet-400",
  },
  "knowledge-cards": {
    label: "知识卡片(beta)",
    description: "原子知识、标签与来源锚点",
    icon: BrainCircuit,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-amber-50/50 dark:hover:bg-amber-900/20 hover:border-amber-200 dark:hover:border-amber-700/50 transition-all",
    iconShell: "bg-amber-100 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400 border border-amber-200 dark:border-amber-500/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-amber-500 group-hover:text-white group-hover:border-amber-400 dark:group-hover:bg-amber-500 dark:group-hover:border-amber-400",
  },
  notes: {
    label: "笔记",
    description: "手记与 Agent 记录",
    icon: StickyNote,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-rose-50/50 dark:hover:bg-rose-900/20 hover:border-rose-200 dark:hover:border-rose-700/50 transition-all",
    iconShell: "bg-rose-100 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400 border border-rose-200 dark:border-rose-500/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-rose-500 group-hover:text-white group-hover:border-rose-400 dark:group-hover:bg-rose-500 dark:group-hover:border-rose-400",
  },
  preview: {
    label: "视频预览",
    description: "查看原始视频内容",
    icon: PlaySquare,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-emerald-50/50 dark:hover:bg-emerald-900/20 hover:border-emerald-200 dark:hover:border-emerald-700/50 transition-all",
    iconShell: "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-emerald-500 group-hover:text-white group-hover:border-emerald-400 dark:group-hover:bg-emerald-500 dark:group-hover:border-emerald-400",
  },
};

export const SERIES_TOOL_TILES = {
  "series-chat-management": {
    label: "对话管理",
    description: "用于切换会话记录",
    icon: MessageSquare,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-sky-50/50 dark:hover:bg-sky-900/20 hover:border-sky-200 dark:hover:border-sky-700/50 transition-all",
    iconShell: "bg-sky-100 text-sky-600 dark:bg-sky-500/10 dark:text-sky-400 border border-sky-200 dark:border-sky-500/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-sky-500 group-hover:text-white group-hover:border-sky-400 dark:group-hover:bg-sky-500 dark:group-hover:border-sky-400",
  },
  "series-mindmap": {
    label: "全局思维导图",
    description: "结构化展现系列知识脉络 (暂未实现)",
    icon: Network,
    palette: "workspace-panel border hover:shadow-lg hover:-translate-y-0.5 hover:bg-violet-50/50 dark:hover:bg-violet-900/20 hover:border-violet-200 dark:hover:border-violet-700/50 transition-all",
    iconShell: "bg-violet-100 text-violet-600 dark:bg-violet-500/10 dark:text-violet-400 border border-violet-200 dark:border-violet-500/20",
    arrowShell: "bg-stone-50 text-stone-400 dark:bg-neutral-900/50 dark:text-zinc-500 border border-stone-200/50 dark:border-white/5 group-hover:bg-violet-500 group-hover:text-white group-hover:border-violet-400 dark:group-hover:bg-violet-500 dark:group-hover:border-violet-400",
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
