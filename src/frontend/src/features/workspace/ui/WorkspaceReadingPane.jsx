import {
  LoaderCircle,
  Sparkles,
  FileText,
  Network,
  PlaySquare,
} from "lucide-react";

import { formatRange } from "../../../shared/lib/time";
import { MindmapCanvas } from "./MindmapCanvas";

export function WorkspaceReadingPane({
  ui,
  tools,
  summary,
  mindmap,
  activeSeries,
  selectedVideo,
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
  const contentWidthClass = ui.contentWidth === "wide" ? "max-w-5xl" : "max-w-3xl";
  const chapterSpacingClass = ui.readingDensity === "compact" ? "gap-3" : "gap-4";
  const chapterCardClass = ui.readingDensity === "compact" ? "p-4" : "p-5";
  const previewSource = tools?.preview.previewUrl ?? previewUrl ?? undefined;

  return (
    <section className="h-full flex flex-col w-full relative bg-white">
      <div className="flex-1 overflow-auto p-6 flex flex-col gap-6">
        {!selectedVideo ? (
          <div className="flex flex-col items-center justify-center min-h-[40vh] text-center rounded-3xl border border-stone-200 border-dashed bg-stone-50/50 mt-10 p-6">
            <h2 className="text-xl font-semibold text-stone-800 mb-2">等待视频</h2>
            <p className="text-stone-500 text-sm">选择左侧 series 后再点选视频</p>
          </div>
        ) : (
          <div className="flex flex-col h-full min-h-0">
            
            {/* Header & Segmented Control */}
            <header className="shrink-0 mb-6 pb-6 border-b border-stone-100 flex flex-col gap-5">
              <div>
                <p className="text-xs font-bold text-stone-500 uppercase mb-1">Source Material</p>
                <h2 className="text-2xl font-bold text-stone-900 leading-snug">{summary?.title ?? selectedVideo.title}</h2>
              </div>

              <div className="flex bg-stone-100/80 p-1.5 rounded-2xl w-full border border-stone-200/50">
                <button 
                  onClick={() => onSelectTool("overview")}
                  className={`flex-1 flex justify-center items-center gap-2 px-4 py-2 text-sm font-bold rounded-xl transition-all duration-200 outline-none
                    ${selectedToolId === "overview" 
                      ? "bg-white text-stone-900 shadow-[0_2px_8px_-2px_rgba(0,0,0,0.05)] border border-stone-200/60" 
                      : "text-stone-500 hover:text-stone-800 hover:bg-stone-200/50"}`}
                >
                  <FileText size={16} className={selectedToolId === "overview" ? "text-teal-600" : ""} /> 
                  AI概况
                </button>
                <button 
                  onClick={() => onSelectTool("mindmap")}
                  disabled={tools?.mindmap.available === false}
                  className={`flex-1 flex justify-center items-center gap-2 px-4 py-2 text-sm font-bold rounded-xl transition-all duration-200 outline-none
                    ${selectedToolId === "mindmap" 
                      ? "bg-white text-stone-900 shadow-[0_2px_8px_-2px_rgba(0,0,0,0.05)] border border-stone-200/60" 
                      : "text-stone-500 hover:text-stone-800 hover:bg-stone-200/50"} ${tools?.mindmap.available === false ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                  <Network size={16} className={selectedToolId === "mindmap" ? "text-teal-600" : ""} /> 
                  思维导图
                </button>
                <button 
                  onClick={() => onSelectTool("preview")}
                  className={`flex-1 flex justify-center items-center gap-2 px-4 py-2 text-sm font-bold rounded-xl transition-all duration-200 outline-none
                    ${selectedToolId === "preview" 
                      ? "bg-white text-stone-900 shadow-[0_2px_8px_-2px_rgba(0,0,0,0.05)] border border-stone-200/60" 
                      : "text-stone-500 hover:text-stone-800 hover:bg-stone-200/50"}`}
                >
                  <PlaySquare size={16} className={selectedToolId === "preview" ? "text-teal-600" : ""} /> 
                  视频预览
                </button>
              </div>
            </header>

            <div className="flex-1 w-full relative min-h-0 animate-in fade-in duration-300">

              {toolsLoading ? (
                <div className="flex items-center justify-center min-h-[320px] rounded-3xl border border-stone-200 bg-stone-50">
                  <div className="inline-flex items-center gap-2 text-stone-600 bg-white px-4 py-2 rounded-full shadow-sm border border-stone-200 text-sm">
                    <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-teal-600" />
                    读取工具状态...
                  </div>
                </div>
              ) : null}

              {selectedToolId === "overview" && !toolsLoading && (
                !tools?.overview.generated ? (
                  <div className="flex flex-col items-center justify-center min-h-[320px] text-center rounded-3xl border border-stone-200 bg-stone-50 mt-10 p-6">
                    <p className="text-xs font-bold text-teal-700 tracking-widest uppercase mb-2">AI Overview</p>
                    <h2 className="text-xl font-semibold text-stone-800 mb-2">{selectedVideo.title}</h2>
                    <p className="text-stone-500 text-sm max-w-md">先在左侧点击生成，生成完成后这里会显示 AI 概况、章节纪要和关键结论。</p>
                    {isGeneratingSelectedVideo ? (
                      <div className="mt-4 inline-flex items-center gap-2 text-stone-600 bg-white px-4 py-2 rounded-full shadow-sm border border-stone-200 text-sm">
                        <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-teal-600" />
                        正在生成概况...
                      </div>
                    ) : null}
                  </div>
                ) : summaryLoading ? (
                  <div className="flex items-center justify-center min-h-[320px] rounded-3xl border border-stone-200 bg-stone-50">
                    <div className="inline-flex items-center gap-2 text-stone-600 bg-white px-4 py-2 rounded-full shadow-sm border border-stone-200 text-sm">
                      <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-teal-600" />
                      载入 AI 概况...
                    </div>
                  </div>
                ) : hasSummary ? (
                <div className={`w-full ${contentWidthClass} mx-auto flex flex-col gap-8 pb-32`}>
                  <article className="p-6 rounded-3xl bg-stone-900 text-stone-50 shadow-lg relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-4 opacity-10">
                      <Sparkles size={64} />
                    </div>
                    <p className="text-[10px] font-bold text-stone-400 tracking-widest uppercase mb-3 relative z-10">
                      Core Problem
                    </p>
                    <p className="text-base leading-relaxed font-medium relative z-10">
                      {summary.core_problem ?? "无核心问题描述。"}
                    </p>
                  </article>

                  {ui.showTakeaways && summary.key_takeaways.length ? (
                    <article className="rounded-3xl border border-stone-200 bg-stone-50 p-6">
                      <p className="text-[10px] font-bold text-teal-700 tracking-widest uppercase mb-3">Key Takeaways</p>
                      <div className="flex flex-col gap-3">
                        {summary.key_takeaways.map((takeaway) => (
                          <div key={takeaway} className="flex items-start gap-3">
                            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-500"></span>
                            <p className="text-sm leading-relaxed text-stone-700">{takeaway}</p>
                          </div>
                        ))}
                      </div>
                    </article>
                  ) : null}

                  <div className={`flex flex-col mt-2 ${chapterSpacingClass}`}>
                    <h2 className="text-xl font-bold text-stone-800 mb-2">章节纪要</h2>
                    {(summary.chapters ?? []).map((chapter, index) => (
                      <article
                        key={chapter.id}
                        id={chapter.id}
                        className={`flex flex-col gap-4 rounded-3xl border transition-all duration-300 ${chapterCardClass} ${
                          chapter.id === selectedChapterId 
                            ? "bg-white border-teal-400 shadow-md ring-2 ring-teal-500/10" 
                            : "bg-white border-stone-200/70 hover:border-stone-300 shadow-sm"
                        }`}
                      >
                        <div className="flex justify-between items-start gap-3">
                          <div>
                            <p className="text-xs font-bold text-teal-600 uppercase tracking-widest mb-1.5">Chapter {index + 1}</p>
                            <h3 className="text-lg font-bold text-stone-900 leading-tight">{chapter.title}</h3>
                          </div>
                          <span className="px-2 py-1 rounded-lg bg-stone-100 text-stone-500 text-xs font-mono font-bold shrink-0">
                            {formatRange(chapter.start_seconds, chapter.end_seconds)}
                          </span>
                        </div>
                        
                        <p className="text-sm text-stone-600 leading-relaxed">
                          {chapter.summary}
                        </p>
                        
                        <div className="flex flex-col gap-2.5 mt-2">
                          {chapter.key_points.map((point) => (
                            <div key={point} className="flex gap-3 items-start">
                              <span className="w-1.5 h-1.5 rounded-full bg-teal-400 shrink-0 mt-2"></span>
                              <p className="text-sm text-stone-700 leading-relaxed">{point}</p>
                            </div>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
                ) : null
              )}

              {selectedToolId === "mindmap" && !toolsLoading && (
                !tools?.mindmap.available ? (
                  <div className="flex flex-col items-center justify-center min-h-[320px] text-center rounded-3xl border border-stone-200 bg-stone-50 mt-10 p-6">
                    <p className="text-xs font-bold text-stone-500 tracking-widest uppercase mb-2">Mindmap</p>
                    <h2 className="text-xl font-semibold text-stone-800 mb-2">需要先生成 AI 概况</h2>
                    <p className="text-stone-500 text-sm max-w-md">导图依赖已生成的概况数据。先生成 AI 概况，再回到这里单独触发导图生成。</p>
                  </div>
                ) : !tools.mindmap.generated ? (
                  <div className="flex flex-col items-center justify-center min-h-[320px] text-center rounded-3xl border border-stone-200 bg-stone-50 mt-10 p-6">
                    <p className="text-xs font-bold text-teal-700 tracking-widest uppercase mb-2">Mindmap Tool</p>
                    <h2 className="text-xl font-semibold text-stone-800 mb-2">导图未生成</h2>
                    <p className="text-stone-500 text-sm max-w-md">思维导图不是默认产物。点击下面按钮后，后端会基于当前 AI 概况单独生成 `mindmap.json`。</p>
                    <button
                      type="button"
                      onClick={onGenerateMindmap}
                      disabled={isGeneratingMindmapSelectedVideo}
                      className={`mt-5 inline-flex items-center gap-2 px-5 py-3 rounded-2xl font-semibold text-sm transition-all ${
                        isGeneratingMindmapSelectedVideo
                          ? "bg-stone-200 text-stone-500 cursor-not-allowed"
                          : "bg-teal-600 text-white hover:bg-teal-700 shadow-sm shadow-teal-600/20"
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
                  </div>
                ) : mindmapLoading ? (
                  <div className="flex items-center justify-center min-h-[320px] rounded-3xl border border-stone-200 bg-stone-50">
                    <div className="inline-flex items-center gap-2 text-stone-600 bg-white px-4 py-2 rounded-full shadow-sm border border-stone-200 text-sm">
                      <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-teal-600" />
                      载入思维导图...
                    </div>
                  </div>
                ) : hasMindmap ? (
                <div className="w-full h-full min-h-[500px] bg-stone-50/80 rounded-3xl border border-stone-200 outline-dashed outline-1 outline-offset-4 outline-stone-100 overflow-hidden relative">
                  <div className="absolute top-4 left-4 z-10 pointer-events-none">
                     <p className="text-[10px] font-bold text-teal-700 tracking-widest uppercase mb-1 shadow-white">Mindmap</p>
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
                  <div className="rounded-3xl border border-stone-200 bg-stone-50 p-4">
                    <p className="text-xs font-bold text-stone-500 uppercase mb-2">Video Preview</p>
                    <p className="text-sm text-stone-600">后续 AI 可根据问题自动切到这里，并跳转到对应时间点。当前先实现工具容器与预览能力。</p>
                  </div>
                  <div className="overflow-hidden rounded-3xl border border-stone-200 bg-black shadow-sm">
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
