import { LoaderCircle, Network, Download, RefreshCw } from "lucide-react";

import { MindmapCanvas } from "../MindmapCanvas";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function WorkspaceSeriesMindmapView({
  seriesId,
  seriesMindmap,
  seriesMindmapAvailable,
  seriesMindmapLoading,
  generatingSeriesMindmap,
  selectedNode,
  onFocusNode,
  onGenerateSeriesMindmap,
  mindmapGenerationProgress,
}) {
  if (seriesMindmapLoading) {
    return (
      <WorkspaceStateBlock
        eyebrow="Series Mindmap"
        title="载入思维导图"
        description="正在读取已生成的导图。"
        loading
      />
    );
  }

  if (!seriesMindmapAvailable) {
    return (
      <WorkspaceStateBlock
        eyebrow="Series Mindmap"
        title="需要先生成 AI 概况"
        description="系列导图依赖已生成的视频概况。请先生成系列中各视频的 AI 概况。"
      />
    );
  }

  if (!seriesMindmap) {
    return (
      <WorkspaceStateBlock
        eyebrow="Series Mindmap"
        title="导图未生成"
        description="点击下面按钮，基于系列中所有视频的概况生成跨视频知识结构导图。"
      >
        <button
          type="button"
          onClick={onGenerateSeriesMindmap}
          disabled={generatingSeriesMindmap}
          className={`inline-flex items-center gap-2 rounded-2xl px-5 py-3 text-sm font-semibold transition-all ${
            generatingSeriesMindmap
              ? "motion-busy-button cursor-not-allowed bg-stone-200 text-stone-500"
              : "bg-accent text-white shadow-sm hover:bg-accent/90"
          }`}
        >
          {generatingSeriesMindmap ? (
            <>
              <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin" />
              正在生成...
            </>
          ) : (
            <>
              <Network size={16} strokeWidth={2.2} />
              生成系列导图
            </>
          )}
        </button>
        {generatingSeriesMindmap && mindmapGenerationProgress ? (
          <div className="motion-fade-up mt-6 w-full max-w-2xl">
            <div className="workspace-elevated-panel rounded-3xl border p-5">
              <p className="text-sm font-medium text-stone-700 dark:text-zinc-300">
                {mindmapGenerationProgress.detail || "正在生成系列思维导图..."}
              </p>
              <div className="mt-3 h-2 w-full rounded-full bg-stone-100 dark:bg-stone-800">
                <div
                  className="h-2 rounded-full bg-accent transition-all duration-500"
                  style={{ width: `${mindmapGenerationProgress.progress ?? 0}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-stone-400">
                {Math.round(mindmapGenerationProgress.progress ?? 0)}%
              </p>
            </div>
          </div>
        ) : null}
      </WorkspaceStateBlock>
    );
  }

  return (
    <div className="workspace-elevated-panel relative h-full min-h-[500px] w-full overflow-hidden rounded-3xl border outline-dashed outline-1 outline-offset-4 outline-stone-200 dark:outline-stone-800">
      <div className="pointer-events-none absolute top-4 left-4 z-10">
        <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Series Mindmap</p>
      </div>
      <div className="pointer-events-auto absolute top-4 right-4 z-10 flex items-center gap-2">
        <button
          type="button"
          onClick={onGenerateSeriesMindmap}
          disabled={generatingSeriesMindmap}
          className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RefreshCw size={14} strokeWidth={2} className={generatingSeriesMindmap ? "animate-spin" : ""} />
          重新生成
        </button>
        <a
          href={`/api/series/${encodeURIComponent(seriesId)}/mindmap/export?format=md`}
          download
          className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors"
        >
          <Download size={14} strokeWidth={2} />
          导出
        </a>
      </div>
      <div className="h-full w-full">
        <MindmapCanvas root={seriesMindmap} selectedNodeId={selectedNode?.id ?? null} onSelectNode={onFocusNode} />
      </div>
    </div>
  );
}
