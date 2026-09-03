import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { LoaderCircle, Network, Download, RefreshCw } from "lucide-react";

import { MINDMAP_DEPTH_OPTIONS } from "../../model/mindmapDepthOptions";
import { MindmapCanvas } from "../MindmapCanvas";
import { WorkspaceProviderSelect } from "../shared/WorkspaceSettingsControls";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";
import { exportMindmapAsSVG } from "../mindmapSVGExport";
import { useOutsidePointerUp } from "../../../../shared/lib/useOutsidePointerUp";

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
  const [exportOpen, setExportOpen] = useState(false);
  const [maxDepth, setMaxDepth] = useState(null);
  const [liveElapsedSeconds, setLiveElapsedSeconds] = useState(0);
  const exportRef = useRef(null);
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

  useOutsidePointerUp(exportOpen, [exportRef], () => setExportOpen(false));

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
    <div className="flex flex-wrap items-center justify-end gap-2">
      <label className="inline-flex">
        <span className="sr-only">导图层级</span>
        <WorkspaceProviderSelect ariaLabel="导图层级" value={maxDepth === null ? "auto" : String(maxDepth)} onChange={(value) => setMaxDepth(value === "auto" ? null : Number(value))} options={MINDMAP_DEPTH_OPTIONS} disabled={generatingSeriesMindmap} hideGroupLabels className="w-24" />
      </label>
      <button type="button" onClick={() => onGenerateSeriesMindmap(maxDepth)} disabled={generatingSeriesMindmap} className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 transition-colors hover:bg-accent/10 hover:text-accent disabled:cursor-not-allowed disabled:opacity-40">
        <RefreshCw size={14} strokeWidth={2} className={generatingSeriesMindmap ? "animate-spin" : ""} />{generatingSeriesMindmap ? `正在生成 · ${Math.round(liveElapsedSeconds)}s` : "重新生成"}
      </button>
      <div className="relative" ref={exportRef}>
        <button type="button" onClick={() => setExportOpen(!exportOpen)} className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 transition-colors hover:bg-accent/10 hover:text-accent"><Download size={14} strokeWidth={2} />导出</button>
        {exportOpen ? (
          <div className="absolute right-0 top-full z-20 mt-1 min-w-[130px] rounded-xl border border-stone-200 bg-white py-1 shadow-lg dark:bg-neutral-900">
            <a href={`/api/series/${encodeURIComponent(seriesId)}/mindmap/export?format=md`} download className="block px-4 py-2 text-xs text-stone-700 hover:bg-stone-50 dark:text-zinc-300 dark:hover:bg-neutral-800" onClick={() => setExportOpen(false)}>Markdown (.md)</a>
            <a href={`/api/series/${encodeURIComponent(seriesId)}/mindmap/export?format=html`} download className="block px-4 py-2 text-xs text-stone-700 hover:bg-stone-50 dark:text-zinc-300 dark:hover:bg-neutral-800" onClick={() => setExportOpen(false)}>HTML (.html)</a>
            <button type="button" className="block w-full px-4 py-2 text-left text-xs text-stone-700 hover:bg-stone-50 dark:text-zinc-300 dark:hover:bg-neutral-800" onClick={() => { setExportOpen(false); markmapRef.current && exportMindmapAsSVG(markmapRef.current, `series-mindmap-${seriesId}.svg`); }}>SVG (.svg)</button>
          </div>
        ) : null}
      </div>
    </div>
  );
  const headerActionHost = typeof document === "undefined" ? null : document.getElementById("workspace-tool-header-actions");
  const actionSlot = headerActionHost
    ? createPortal(actionBar, headerActionHost)
    : <div className="mb-3 flex justify-end">{actionBar}</div>;

  return (
    <>
      {actionSlot}
      <div className="workspace-elevated-panel relative h-full min-h-[500px] w-full overflow-hidden rounded-3xl border outline-dashed outline-1 outline-offset-4 outline-stone-200 dark:outline-stone-800">
        <div className="pointer-events-none absolute left-4 top-4 z-10">
          <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Series Mindmap</p>
        </div>
        <MindmapCanvas root={seriesMindmap} selectedNodeId={selectedNode?.id ?? null} onSelectNode={onFocusNode} markmapRef={markmapRef} theme={theme} />
      </div>
    </>
  );
}
