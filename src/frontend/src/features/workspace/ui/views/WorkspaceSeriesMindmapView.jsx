import { useState, useEffect, useRef } from "react";
import { LoaderCircle, Network, Download, RefreshCw } from "lucide-react";

import { MINDMAP_DEPTH_OPTIONS } from "../../model/mindmapDepthOptions";
import { MindmapCanvas } from "../MindmapCanvas";
import { WorkspaceProviderSelect } from "../shared/WorkspaceSettingsControls";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";
import { exportMindmapAsSVG } from "../mindmapSVGExport";

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
  theme,
}) {
  const [maxDepth, setMaxDepth] = useState(null);
  const [liveElapsedSeconds, setLiveElapsedSeconds] = useState(0);
  const markmapRef = useRef(null);

  useEffect(() => {
    const progress = mindmapGenerationProgress;
    if (!progress || progress.status !== "running") {
      setLiveElapsedSeconds(0);
      return undefined;
    }

    const getElapsedSeconds = () => {
      const snapshotElapsed = Number(progress.elapsed_seconds) || 0;
      const startedAt = Number(progress.started_at);
      const clockElapsed = Number.isFinite(startedAt) ? Math.max(0, Date.now() / 1000 - startedAt) : 0;
      return Math.max(snapshotElapsed, clockElapsed);
    };

    const updateElapsed = () => setLiveElapsedSeconds(getElapsedSeconds());
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [mindmapGenerationProgress]);


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
        <div className="flex flex-wrap items-center justify-center gap-3">
          <label className="inline-flex items-center gap-2 text-sm font-medium text-stone-600 dark:text-stone-300">
            层级
            <WorkspaceProviderSelect
              ariaLabel="导图层级"
              value={maxDepth === null ? "auto" : String(maxDepth)}
              onChange={(value) => setMaxDepth(value === "auto" ? null : Number(value))}
              options={MINDMAP_DEPTH_OPTIONS}
              disabled={generatingSeriesMindmap}
              hideGroupLabels
              className="w-24"
            />
          </label>
          <button
            type="button"
            onClick={() => onGenerateSeriesMindmap(maxDepth)}
            disabled={generatingSeriesMindmap}
            className={`inline-flex items-center gap-2 rounded-2xl px-5 py-3 text-sm font-semibold transition-all ${
              generatingSeriesMindmap
                ? "motion-busy-button cursor-not-allowed bg-stone-200 text-stone-600"
                : "bg-accent text-white shadow-sm hover:bg-accent/90"
            }`}
          >
            {generatingSeriesMindmap ? (
              <>
                <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin" />
                正在生成
              </>
            ) : (
              <>
                <Network size={16} strokeWidth={2.2} />
                生成系列导图
              </>
            )}
          </button>
        </div>
        {generatingSeriesMindmap && mindmapGenerationProgress ? (
          <div className="motion-fade-up mt-6 w-full max-w-2xl">
            <div className="workspace-elevated-panel rounded-3xl border p-5 flex items-center gap-3">
              <LoaderCircle size={18} strokeWidth={2.2} className="animate-spin text-accent" />
              <p className="text-sm text-stone-600 dark:text-zinc-400">
                {mindmapGenerationProgress.detail || "正在生成系列思维导图"}
                <span className="mx-2 text-stone-300 dark:text-zinc-600">·</span>
                <span className="font-medium text-stone-700 dark:text-zinc-200">
                  已用 {Math.round(liveElapsedSeconds)} 秒
                </span>
              </p>
            </div>
          </div>
        ) : null}
      </WorkspaceStateBlock>
    );
  }

  const actionBar = (
    <div className="workspace-elevated-panel absolute right-4 top-4 z-10 flex items-center gap-1 rounded-xl border p-1.5 shadow-lg">
      <label className="inline-flex">
        <span className="sr-only">导图层级</span>
        <WorkspaceProviderSelect ariaLabel="导图层级" value={maxDepth === null ? "auto" : String(maxDepth)} onChange={(value) => setMaxDepth(value === "auto" ? null : Number(value))} options={MINDMAP_DEPTH_OPTIONS} disabled={generatingSeriesMindmap} hideGroupLabels className="w-24" />
      </label>
      <button type="button" onClick={() => onGenerateSeriesMindmap(maxDepth)} disabled={generatingSeriesMindmap} className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 transition-colors hover:bg-accent/10 hover:text-accent disabled:cursor-not-allowed disabled:opacity-40" title={generatingSeriesMindmap ? "正在重新生成全局思维导图" : "重新生成全局思维导图"} aria-label={generatingSeriesMindmap ? "正在重新生成全局思维导图" : "重新生成全局思维导图"}>
        <RefreshCw size={14} strokeWidth={2} className={generatingSeriesMindmap ? "animate-spin" : ""} />
      </button>
      <button type="button" className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 transition-colors hover:bg-accent/10 hover:text-accent" onClick={() => markmapRef.current && exportMindmapAsSVG(markmapRef.current, `series-mindmap-${seriesId}.svg`)} title="导出 SVG" aria-label="导出 SVG"><Download size={14} strokeWidth={2} /></button>
    </div>
  );
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="relative min-h-0 flex-1 w-full overflow-hidden">
        <MindmapCanvas root={seriesMindmap} selectedNodeId={selectedNode?.id ?? null} onSelectNode={onFocusNode} markmapRef={markmapRef} theme={theme} />
        {actionBar}
      </div>
    </div>
  );
}
