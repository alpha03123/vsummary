import {
  LoaderCircle,
  Sparkles,
  FileText,
  Network,
  PlaySquare,
  ArrowRight,
  ArrowLeft,
  FolderKanban,
  ListChecks,
  ChevronDown,
  Captions,
} from "lucide-react";

import { formatRange, formatTimestamp } from "../../../shared/lib/time";
import { MindmapCanvas } from "./MindmapCanvas";

const TOOL_TILES = {
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
  preview: {
    label: "视频预览",
    description: "查看原始视频内容",
    icon: PlaySquare,
    palette: "workspace-muted-panel border text-stone-900 dark:text-stone-100 hover:border-emerald-300/70 dark:hover:border-emerald-700/70",
    iconShell: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300 border border-emerald-100 dark:border-emerald-900/50",
    arrowShell: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-300",
  },
};

const SERIES_TOOL_TILES = {
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

function describeToolState(toolId, toolState) {
  if (!toolState) {
    return "读取中";
  }
  if (toolId === "preview") {
    return "随时可查看";
  }
  if (toolState.generated) {
    return "已生成";
  }
  if (toolState.available === false) {
    return "需先生成 AI 概况";
  }
  return "点击进入后生成";
}

export function WorkspaceReadingPane({
  ui,
  tools,
  library,
  summary,
  mindmap,
  activeSeries,
  selectedVideo,
  selectedContextType,
  selectedNode,
  previewUrl,
  selectedToolId,
  selectedChapterId,
  toolsLoading,
  summaryLoading,
  mindmapLoading,
  isGeneratingMindmapSelectedVideo,
  isGeneratingSelectedVideo,
  onSelectTool,
  onFocusNode,
  onGenerateMindmap,
}) {
  const hasSummary = Boolean(summary);
  const hasMindmap = Boolean(mindmap);
  const previewSource = tools?.preview.previewUrl ?? previewUrl ?? undefined;
  const isStudioHome = selectedToolId === "studio";
  const isSeriesHome = selectedToolId === "series-home";
  const currentToolMeta = TOOL_TILES[selectedToolId] ?? SERIES_TOOL_TILES[selectedToolId] ?? null;
  const seriesVideos = activeSeries?.videos ?? [];
  const processedSeriesVideos = seriesVideos.filter((video) => video.processed);
  const contentMotionKey = `${selectedContextType}:${selectedToolId}:${selectedVideo?.id ?? activeSeries?.id ?? "empty"}`;

  return (
    <section className="h-full flex flex-col w-full relative bg-transparent">
      <div className="flex-1 overflow-auto p-6 flex flex-col gap-5">
        {!activeSeries ? (
          <div className="workspace-muted-panel flex flex-col items-center justify-center min-h-[40vh] text-center rounded-3xl border border-dashed mt-10 p-6">
            <h2 className="text-xl font-semibold text-stone-800 dark:text-stone-100 mb-2">等待系列</h2>
            <p className="text-stone-500 dark:text-stone-400 text-sm">先进入一个 series，右侧才会显示系列或视频工具</p>
          </div>
        ) : (
          <div key={contentMotionKey} className="motion-fade-scale flex flex-col h-full min-h-0">
            
            {/* Header & Tool Tiles */}
            <header className="shrink-0 mb-5 pb-5 border-b border-stone-200/80 dark:border-stone-800 flex flex-col gap-5">
              {isStudioHome ? (
                <>
                  <div>
                    <p className="text-xs font-bold text-stone-500 dark:text-stone-400 uppercase mb-1">Studio</p>
                    <h2 className="text-2xl font-bold text-stone-900 dark:text-stone-100 leading-snug">{summary?.title ?? selectedVideo?.title}</h2>
                    <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">选择一个工具进入专门页面，进入后会隐藏其他卡片。</p>
                  </div>

                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    {Object.entries(TOOL_TILES).map(([toolId, meta], index) => {
                      const toolState = tools?.[toolId];
                      const Icon = meta.icon;
                      const isDisabled = toolState?.available === false;

                      return (
                        <button
                          key={toolId}
                          type="button"
                          onClick={() => onSelectTool(toolId)}
                          disabled={isDisabled}
                          className={`motion-stagger group rounded-[1.5rem] p-5 text-left transition-all duration-200 hover:-translate-y-0.5 hover:bg-white dark:hover:bg-[#1f1f1f] hover:shadow-[0_10px_24px_rgba(15,23,42,0.08)] dark:hover:shadow-[0_10px_24px_rgba(0,0,0,0.26)] ${meta.palette} ${isDisabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}`}
                          style={{ "--stagger-index": index }}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex items-start gap-3">
                              <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl shadow-sm shadow-slate-950/10 transition-colors group-hover:brightness-105 ${meta.iconShell}`}>
                                <Icon size={18} />
                              </span>
                              <span className="flex flex-col">
                                <span className="text-base font-bold">{meta.label}</span>
                                <span className="mt-1 text-xs text-stone-500 dark:text-stone-400">{meta.description}</span>
                                <span className="mt-3 text-xs font-semibold text-stone-600 dark:text-stone-300">{describeToolState(toolId, toolState)}</span>
                              </span>
                            </div>
                            <span className={`motion-arrow-shift flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-white/40 dark:border-stone-800 transition-colors group-hover:brightness-105 ${meta.arrowShell}`}>
                              <ArrowRight size={18} />
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </>
              ) : isSeriesHome ? (
                <>
                  <div>
                    <p className="text-xs font-bold text-stone-500 dark:text-stone-400 uppercase mb-1">Series Home</p>
                    <h2 className="text-2xl font-bold text-stone-900 dark:text-stone-100 leading-snug">{activeSeries.title}</h2>
                    <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">你现在看的不是某条视频，而是整个 series。先选系列工具，再决定是否切到单视频。</p>
                  </div>

                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    {Object.entries(SERIES_TOOL_TILES).map(([toolId, meta], index) => {
                      const Icon = meta.icon;
                      return (
                        <button
                          key={toolId}
                          type="button"
                          onClick={() => onSelectTool(toolId)}
                          className={`motion-stagger group rounded-[1.5rem] p-5 text-left transition-all duration-200 hover:-translate-y-0.5 hover:bg-white dark:hover:bg-[#1f1f1f] hover:shadow-[0_10px_24px_rgba(15,23,42,0.08)] dark:hover:shadow-[0_10px_24px_rgba(0,0,0,0.26)] cursor-pointer ${meta.palette}`}
                          style={{ "--stagger-index": index }}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex items-start gap-3">
                              <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl transition-colors group-hover:brightness-105 ${meta.iconShell}`}>
                                <Icon size={18} />
                              </span>
                              <span className="flex flex-col">
                                <span className="text-base font-bold">{meta.label}</span>
                                <span className="mt-1 text-xs text-stone-500 dark:text-stone-400">{meta.description}</span>
                                <span className="mt-3 text-xs font-semibold text-stone-600 dark:text-stone-300">series 级工具</span>
                              </span>
                            </div>
                            <span className={`motion-arrow-shift flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-white/40 dark:border-stone-800 transition-colors group-hover:brightness-105 ${meta.arrowShell}`}>
                              <ArrowRight size={18} />
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-bold text-stone-500 dark:text-stone-400 uppercase mb-1">Tool Page</p>
                    <h2 className="text-2xl font-bold text-stone-900 dark:text-stone-100 leading-snug">{currentToolMeta?.label}</h2>
                    <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">{currentToolMeta?.description}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => onSelectTool(selectedContextType === "series" ? "series-home" : "studio")}
                    className="workspace-elevated-panel inline-flex items-center gap-2 rounded-2xl border px-4 py-2 text-sm font-semibold text-stone-700 dark:text-stone-200 transition-all hover:border-stone-300 dark:hover:border-white/16 hover:bg-white dark:hover:bg-[#1f1f1f] hover:text-stone-900 dark:hover:text-stone-100 hover:-translate-y-0.5"
                  >
                    <ArrowLeft size={16} />
                    返回工具页
                  </button>
                </div>
              )}
            </header>

            <div className="flex-1 w-full relative min-h-0">

              {toolsLoading ? (
                <div className="flex items-center justify-center min-h-[320px] rounded-3xl border border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-950">
                  <div className="inline-flex items-center gap-2 text-stone-600 dark:text-stone-300 bg-white dark:bg-stone-900 px-4 py-2 rounded-full shadow-sm border border-stone-200 dark:border-stone-700 text-sm">
                    <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-[#0070f3]" />
                    读取工具状态...
                  </div>
                </div>
              ) : null}

              {isSeriesHome ? (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <article className="workspace-muted-panel rounded-3xl border p-6">
                    <p className="text-sm font-semibold uppercase tracking-widest text-stone-500 dark:text-stone-400">系列视频数</p>
                    <strong className="mt-3 block text-4xl font-bold text-stone-900 dark:text-stone-100">{seriesVideos.length}</strong>
                  </article>
                  <article className="workspace-accent-panel rounded-3xl border p-6">
                    <p className="text-sm font-semibold uppercase tracking-widest text-stone-700 dark:text-zinc-300">已处理视频</p>
                    <strong className="mt-3 block text-4xl font-bold text-stone-900 dark:text-white">{processedSeriesVideos.length}</strong>
                  </article>
                  <article className="workspace-muted-panel rounded-3xl border p-6">
                    <p className="text-sm font-semibold uppercase tracking-widest text-stone-500 dark:text-stone-400">当前焦点</p>
                    <strong className="mt-3 block text-xl font-bold text-stone-900 dark:text-stone-100">整个 {activeSeries.title}</strong>
                  </article>
                </div>
              ) : null}

              {selectedToolId === "series-overview" ? (
                <div className="w-full max-w-4xl">
                  <article className="workspace-muted-panel rounded-[2rem] border p-7">
                    <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">Series Overview</p>
                    <h3 className="mt-3 text-3xl font-bold text-stone-900 dark:text-stone-100">{activeSeries.title}</h3>
                    <p className="mt-4 text-sm leading-relaxed text-stone-600 dark:text-stone-400">
                      这是系列级上下文。后续 AI 可以基于整个 series 理解主题范围、视频分布和知识覆盖，而不是被锁定在单一视频上。
                    </p>
                    <div className="mt-6 flex flex-col gap-3">
                      {seriesVideos.map((video) => (
                        <div key={video.id} className="workspace-elevated-panel rounded-2xl border px-4 py-3">
                          <div className="flex items-center justify-between gap-3">
                            <strong className="text-sm font-semibold text-stone-900 dark:text-stone-100">{video.title}</strong>
                            <span className={`text-xs font-semibold ${video.processed ? "text-[#0070f3] dark:text-[#4da3ff]" : "text-stone-500"}`}>
                              {video.processed ? "已处理" : "未处理"}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </article>
                </div>
              ) : null}

              {selectedToolId === "series-progress" ? (
                <div className="w-full max-w-4xl">
                  <article className="workspace-muted-panel rounded-[2rem] border p-7">
                    <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">Series Progress</p>
                    <h3 className="mt-3 text-3xl font-bold text-stone-900 dark:text-stone-100">处理进度</h3>
                    <div className="mt-6 flex flex-col gap-3">
                      {seriesVideos.map((video, index) => (
                        <div key={video.id} className="workspace-elevated-panel rounded-2xl border px-4 py-4">
                          <div className="flex items-center justify-between gap-4">
                            <div>
                              <p className="text-xs font-bold uppercase tracking-widest text-stone-400 dark:text-stone-500">Video {index + 1}</p>
                              <strong className="mt-1 block text-sm font-semibold text-stone-900 dark:text-stone-100">{video.title}</strong>
                            </div>
                            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
                              video.processed ? "bg-stone-100 text-stone-900 dark:bg-[#111111] dark:text-white border border-stone-200 dark:border-white/10" : "bg-stone-100 text-stone-500 dark:bg-stone-800 dark:text-stone-300"
                            }`}>
                              {video.processed ? "已完成" : "待处理"}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </article>
                </div>
              ) : null}

              {isStudioHome && !toolsLoading ? (
                <div className="workspace-muted-panel flex min-h-[320px] items-center justify-center rounded-3xl border border-dashed text-center">
                  <div className="max-w-md px-6 py-10">
                    <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">Studio Home</p>
                    <h3 className="mt-3 text-2xl font-bold text-stone-900 dark:text-stone-100">选择一个工具进入工作页</h3>
                    <p className="mt-3 text-sm leading-relaxed text-stone-500 dark:text-stone-400">
                      AI概况、思维导图和视频预览现在都是独立工具页。点上面的卡片进入，完成后再返回工具页切换其他工具。
                    </p>
                  </div>
                </div>
              ) : null}

              {selectedToolId === "overview" && !toolsLoading && (
                !tools?.overview.generated ? (
                  <div className="workspace-muted-panel flex flex-col items-center justify-center min-h-[320px] text-center rounded-3xl border mt-10 p-6">
                    <p className="text-xs font-bold text-stone-600 dark:text-zinc-400 tracking-widest uppercase mb-2">AI Overview</p>
                    <h2 className="text-xl font-semibold text-stone-800 mb-2">{selectedVideo.title}</h2>
                    <p className="text-stone-500 text-sm max-w-md">先在左侧点击生成，生成完成后这里会显示 AI 概况、章节纪要和关键结论。</p>
                    {isGeneratingSelectedVideo ? (
                      <div className="motion-busy-button mt-4 inline-flex items-center gap-2 text-stone-600 bg-white px-4 py-2 rounded-full shadow-sm border border-stone-200 text-sm">
                        <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-[#0070f3]" />
                        正在生成概况...
                      </div>
                    ) : null}
                    {isGeneratingSelectedVideo ? (
                      <div className="motion-fade-up mt-6 w-full max-w-xl">
                        <div className="workspace-elevated-panel rounded-3xl border p-6">
                          <div className="motion-shimmer h-3 w-24 rounded-full bg-stone-100 dark:bg-stone-800"></div>
                          <div className="motion-shimmer mt-5 h-7 w-3/4 rounded-2xl bg-stone-100 dark:bg-stone-800"></div>
                          <div className="motion-shimmer mt-4 h-4 w-full rounded-full bg-stone-100 dark:bg-stone-800"></div>
                          <div className="motion-shimmer mt-3 h-4 w-5/6 rounded-full bg-stone-100 dark:bg-stone-800"></div>
                          <div className="motion-shimmer mt-8 h-24 w-full rounded-[1.5rem] bg-stone-100 dark:bg-stone-800"></div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : summaryLoading ? (
                  <div className="workspace-muted-panel flex items-center justify-center min-h-[320px] rounded-3xl border">
                    <div className="inline-flex items-center gap-2 text-stone-600 dark:text-stone-300 bg-white/95 dark:bg-stone-950 px-4 py-2 rounded-full shadow-sm border border-stone-200 dark:border-stone-700 text-sm">
                      <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-[#0070f3]" />
                      载入 AI 概况...
                    </div>
                  </div>
                ) : hasSummary ? (
                <div className="w-full max-w-3xl mx-auto flex flex-col gap-8 pb-32">
                  <article className="workspace-accent-panel rounded-3xl border p-6 text-stone-900 dark:text-stone-100 relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-4 opacity-10">
                      <Sparkles size={64} />
                    </div>
                    <p className="text-[10px] font-bold text-stone-500 dark:text-stone-400 tracking-widest uppercase mb-3 relative z-10">
                      Core Problem
                    </p>
                    <p className="text-base leading-relaxed font-medium relative z-10">
                      {summary.core_problem ?? "无核心问题描述。"}
                    </p>
                  </article>

                  {ui.showTakeaways && summary.key_takeaways.length ? (
                    <article className="workspace-muted-panel rounded-3xl border p-6">
                      <p className="text-[10px] font-bold text-stone-600 dark:text-zinc-400 tracking-widest uppercase mb-3">Key Takeaways</p>
                      <div className="flex flex-col gap-3">
                        {summary.key_takeaways.map((takeaway) => (
                          <div key={takeaway} className="flex items-start gap-3">
                            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#0070f3]"></span>
                            <p className="text-sm leading-relaxed text-stone-700 dark:text-stone-300">{takeaway}</p>
                          </div>
                        ))}
                      </div>
                    </article>
                  ) : null}

                  <div className="flex flex-col mt-2 gap-4">
                    <h2 className="text-xl font-bold text-stone-800 mb-2">章节纪要</h2>
                    {(summary.chapters ?? []).map((chapter, index) => (
                      <article
                        key={chapter.id}
                        id={chapter.id}
                        className={`flex flex-col gap-4 rounded-3xl border transition-all duration-300 p-5 ${
                          chapter.id === selectedChapterId 
                            ? "workspace-elevated-panel border-[#0070f3] shadow-md ring-2 ring-[#0070f3]/10" 
                            : "workspace-elevated-panel border-stone-200/70 dark:border-stone-800 hover:border-stone-300 dark:hover:border-stone-700 hover:bg-white dark:hover:bg-[#1f1f1f] hover:-translate-y-0.5 hover:shadow-[0_8px_20px_rgba(15,23,42,0.05)] dark:hover:shadow-[0_8px_20px_rgba(0,0,0,0.2)]"
                        }`}
                      >
                        <div className="flex justify-between items-start gap-3">
                          <div>
                            <p className="text-xs font-bold text-stone-600 dark:text-zinc-400 uppercase tracking-widest mb-1.5">Chapter {index + 1}</p>
                            <h3 className="text-lg font-bold text-stone-900 dark:text-stone-100 leading-tight">{chapter.title}</h3>
                          </div>
                          <span className="px-2 py-1 rounded-lg bg-stone-100 dark:bg-stone-900 text-stone-500 dark:text-stone-400 text-xs font-mono font-bold shrink-0">
                            {formatRange(chapter.start_seconds, chapter.end_seconds)}
                          </span>
                        </div>
                        
                        <p className="text-sm text-stone-600 dark:text-stone-400 leading-relaxed">
                          {chapter.summary}
                        </p>
                        
                        <div className="flex flex-col gap-2.5 mt-2">
                          {chapter.key_points.map((point) => (
                            <div key={point} className="flex gap-3 items-start">
                              <span className="w-1.5 h-1.5 rounded-full bg-[#0070f3] shrink-0 mt-2"></span>
                              <p className="text-sm text-stone-700 dark:text-stone-300 leading-relaxed">{point}</p>
                            </div>
                          ))}
                        </div>

                        {chapter.transcript_segments.length ? (
                          <details className="group mt-1 rounded-2xl border border-stone-200/80 bg-stone-50/80 dark:border-stone-800 dark:bg-stone-950/60">
                            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3">
                              <div className="flex items-center gap-3">
                                <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-white text-[#0070f3] shadow-sm dark:bg-stone-900">
                                  <Captions size={16} />
                                </span>
                                <div>
                                  <p className="text-sm font-semibold text-stone-900 dark:text-stone-100">查看本章原文</p>
                                  <p className="text-xs text-stone-500 dark:text-stone-400">
                                    {chapter.transcript_segments.length} 段转写
                                  </p>
                                </div>
                              </div>
                              <span className="flex items-center gap-2 text-xs font-semibold text-stone-500 dark:text-stone-400">
                                {formatRange(chapter.start_seconds, chapter.end_seconds)}
                                <ChevronDown size={16} className="transition-transform duration-200 group-open:rotate-180" />
                              </span>
                            </summary>

                            <div className="border-t border-stone-200/80 px-4 py-4 dark:border-stone-800">
                              <div className="flex flex-col gap-3">
                                {chapter.transcript_segments.map((segment) => (
                                  <div key={`${chapter.id}-${segment.start_seconds}-${segment.end_seconds}`} className="rounded-2xl bg-white/90 px-3 py-3 dark:bg-[#121212]">
                                    <p className="text-[11px] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">
                                      {formatTimestamp(segment.start_seconds)} - {formatTimestamp(segment.end_seconds)}
                                    </p>
                                    <p className="mt-2 text-sm leading-relaxed text-stone-700 dark:text-stone-300">
                                      {segment.text}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </details>
                        ) : null}
                      </article>
                    ))}
                  </div>
                </div>
                ) : null
              )}

              {selectedToolId === "mindmap" && !toolsLoading && (
                !tools?.mindmap.available ? (
                  <div className="workspace-muted-panel flex flex-col items-center justify-center min-h-[320px] text-center rounded-3xl border mt-10 p-6">
                    <p className="text-xs font-bold text-stone-500 tracking-widest uppercase mb-2">Mindmap</p>
                    <h2 className="text-xl font-semibold text-stone-800 mb-2">需要先生成 AI 概况</h2>
                    <p className="text-stone-500 text-sm max-w-md">导图依赖已生成的概况数据。先生成 AI 概况，再回到这里单独触发导图生成。</p>
                  </div>
                ) : !tools.mindmap.generated ? (
                  <div className="workspace-muted-panel flex flex-col items-center justify-center min-h-[320px] text-center rounded-3xl border mt-10 p-6">
                    <p className="text-xs font-bold text-stone-600 dark:text-zinc-400 tracking-widest uppercase mb-2">Mindmap Tool</p>
                    <h2 className="text-xl font-semibold text-stone-800 mb-2">导图未生成</h2>
                    <p className="text-stone-500 text-sm max-w-md">思维导图不是默认产物。点击下面按钮后，后端会基于当前 AI 概况单独生成 `mindmap.json`。</p>
                    <button
                      type="button"
                      onClick={onGenerateMindmap}
                      disabled={isGeneratingMindmapSelectedVideo}
                      className={`mt-5 inline-flex items-center gap-2 px-5 py-3 rounded-2xl font-semibold text-sm transition-all ${
                        isGeneratingMindmapSelectedVideo
                          ? "motion-busy-button bg-stone-200 text-stone-500 cursor-not-allowed"
                          : "bg-[#0070f3] text-white hover:bg-[#0064db] shadow-sm"
                      }`}
                    >
                      {isGeneratingMindmapSelectedVideo ? (
                        <>
                          <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin" />
                          Generating Mindmap...
                        </>
                      ) : (
                        <>
                          <Network size={16} strokeWidth={2.2} />
                          生成思维导图
                        </>
                      )}
                    </button>
                    {isGeneratingMindmapSelectedVideo ? (
                      <div className="motion-fade-up mt-6 w-full max-w-2xl">
                        <div className="workspace-elevated-panel rounded-3xl border p-5">
                          <div className="motion-shimmer h-4 w-28 rounded-full bg-stone-100 dark:bg-stone-800"></div>
                          <div className="motion-shimmer mt-5 h-[220px] w-full rounded-[1.5rem] bg-stone-100 dark:bg-stone-800"></div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : mindmapLoading ? (
                  <div className="workspace-muted-panel flex items-center justify-center min-h-[320px] rounded-3xl border">
                    <div className="inline-flex items-center gap-2 text-stone-600 dark:text-stone-300 bg-white/95 dark:bg-stone-950 px-4 py-2 rounded-full shadow-sm border border-stone-200 dark:border-stone-700 text-sm">
                      <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-[#0070f3]" />
                      载入思维导图...
                    </div>
                  </div>
                ) : hasMindmap ? (
                <div className="workspace-elevated-panel w-full h-full min-h-[500px] rounded-3xl border outline-dashed outline-1 outline-offset-4 outline-stone-200 dark:outline-stone-800 overflow-hidden relative">
                  <div className="absolute top-4 left-4 z-10 pointer-events-none">
                     <p className="text-[10px] font-bold text-stone-600 dark:text-zinc-400 tracking-widest uppercase mb-1">Mindmap</p>
                  </div>
                  <div className="w-full h-full">
                    <MindmapCanvas
                      root={mindmap}
                      selectedNodeId={selectedNode?.id ?? null}
                      onSelectNode={onFocusNode}
                    />
                  </div>
                </div>
                ) : null
              )}

              {selectedToolId === "preview" && !toolsLoading ? (
                <div className="flex flex-col gap-4">
                  <div className="workspace-muted-panel rounded-3xl border p-4">
                    <p className="text-xs font-bold text-stone-500 dark:text-stone-400 uppercase mb-2">Video Preview</p>
                    <p className="text-sm text-stone-600 dark:text-stone-400">后续 AI 可根据问题自动切到这里，并跳转到对应时间点。当前先实现工具容器与预览能力。</p>
                  </div>
                  <div className="workspace-elevated-panel overflow-hidden rounded-3xl border bg-black shadow-sm">
                    <video key={previewSource} className="h-full w-full max-h-[72vh] bg-black" controls preload="metadata">
                      <source src={previewSource} />
                    </video>
                  </div>
                </div>
              ) : null}

            </div>
          </div>
        )}
      </div>
    </section>
  );
}
