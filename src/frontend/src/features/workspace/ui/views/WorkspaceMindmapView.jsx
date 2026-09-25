import { useState, useEffect, useRef } from "react";
import { ChevronDown, ChevronUp, LoaderCircle, Network, Download, RefreshCw } from "lucide-react";

import { MINDMAP_DEPTH_OPTIONS } from "../../model/mindmapDepthOptions";
import { MindmapCanvas } from "../MindmapCanvas";
import { exportMindmapAsSVG } from "../mindmapSVGExport";
import { WorkspaceProviderSelect } from "../shared/WorkspaceSettingsControls";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function WorkspaceMindmapView({
  tools,
  mindmap,
  selectedNode,
  mindmapLoading,
  isGeneratingMindmapSelectedVideo,
  onFocusNode,
  onGenerateMindmap,
  seriesId,
  videoId,
  mindmapGenerationProgress,
  theme,
}) {
  const hasMindmap = Boolean(mindmap);

  const [maxDepth, setMaxDepth] = useState(null);
  const [controlsOpen, setControlsOpen] = useState(false);
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


  if (!tools?.mindmap.available) {
    return (
      <WorkspaceStateBlock
        eyebrow="Mindmap"
        title="需要先生成 AI 概况"
        description="导图依赖已生成的概况数据。先生成 AI 概况，再回到这里单独触发导图生成。"
      />
    );
  }

  if (!tools.mindmap.generated) {
    return (
      <WorkspaceStateBlock
        eyebrow="Mindmap Tool"
        title="导图未生成"
        description="思维导图需要单独生成。系统将分析当前 AI 概况，为您构建可视化的知识导图。"
      >
        <div className="flex flex-wrap items-center justify-center gap-3">
          <label className="inline-flex items-center gap-2 text-sm font-medium text-stone-600 dark:text-stone-300">
            层级
            <WorkspaceProviderSelect
              ariaLabel="导图层级"
              value={maxDepth === null ? "auto" : String(maxDepth)}
              onChange={(value) => setMaxDepth(value === "auto" ? null : Number(value))}
              options={MINDMAP_DEPTH_OPTIONS}
              disabled={isGeneratingMindmapSelectedVideo}
              hideGroupLabels
              className="w-24"
            />
          </label>
          <button
            type="button"
            onClick={() => onGenerateMindmap(maxDepth)}
            disabled={isGeneratingMindmapSelectedVideo}
            className={`inline-flex items-center gap-2 rounded-2xl px-5 py-3 text-sm font-semibold transition-all ${
              isGeneratingMindmapSelectedVideo
                ? "motion-busy-button cursor-not-allowed bg-stone-200 text-stone-600"
                : "bg-accent text-white shadow-sm hover:bg-accent/90"
            }`}
          >
            {isGeneratingMindmapSelectedVideo ? (
              <>
                <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin" />
                正在生成
              </>
            ) : (
              <>
                <Network size={16} strokeWidth={2.2} />
                生成思维导图
              </>
            )}
          </button>
        </div>
        {isGeneratingMindmapSelectedVideo && mindmapGenerationProgress ? (
          <div className="motion-fade-up mt-6 w-full max-w-2xl">
            <div className="workspace-elevated-panel rounded-3xl border p-5 flex items-center gap-3">
              <LoaderCircle size={18} strokeWidth={2.2} className="animate-spin text-accent" />
              <p className="text-sm text-stone-600 dark:text-zinc-400">
                {mindmapGenerationProgress.detail || "正在生成思维导图"}
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

  if (mindmapLoading) {
    return (
      <WorkspaceStateBlock
        eyebrow="Mindmap"
        title="载入思维导图"
        description="正在读取已生成的导图。"
        loading
      />
    );
  }

  if (!hasMindmap) {
    return null;
  }

  const actionBar = controlsOpen ? (
    <div className="absolute inset-x-0 top-0 z-10 flex justify-end border-b border-stone-200/80 bg-white/90 px-3 py-1.5 backdrop-blur dark:border-stone-800 dark:bg-neutral-950/90">
      <div className="flex items-center gap-1">
          <label className="inline-flex">
            <span className="sr-only">导图层级</span>
            <WorkspaceProviderSelect
              ariaLabel="导图层级"
              value={maxDepth === null ? "auto" : String(maxDepth)}
              onChange={(value) => setMaxDepth(value === "auto" ? null : Number(value))}
              options={MINDMAP_DEPTH_OPTIONS}
              disabled={isGeneratingMindmapSelectedVideo}
              hideGroupLabels
              className="w-24"
            />
          </label>
          <button
            type="button"
            onClick={() => onGenerateMindmap(maxDepth)}
            disabled={isGeneratingMindmapSelectedVideo}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 transition-colors hover:bg-accent/10 hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
            title={isGeneratingMindmapSelectedVideo ? "正在重新生成思维导图" : "重新生成思维导图"}
            aria-label={isGeneratingMindmapSelectedVideo ? "正在重新生成思维导图" : "重新生成思维导图"}
          >
            <RefreshCw size={14} strokeWidth={2} className={isGeneratingMindmapSelectedVideo ? "animate-spin" : ""} />
          </button>
          <button type="button" className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 transition-colors hover:bg-accent/10 hover:text-accent" onClick={() => markmapRef.current && exportMindmapAsSVG(markmapRef.current, `mindmap-${videoId}.svg`)} title="导出 SVG" aria-label="导出 SVG">
            <Download size={14} strokeWidth={2} />
          </button>
          <button type="button" onClick={() => setControlsOpen(false)} className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-accent/10 hover:text-accent" title="收起导图工具" aria-label="收起导图工具" aria-expanded="true">
            <ChevronUp size={16} />
          </button>
      </div>
    </div>
  ) : (
    <button type="button" onClick={() => setControlsOpen(true)} className="absolute left-1/2 top-0 z-10 inline-flex h-6 w-12 -translate-x-1/2 items-center justify-center rounded-b-lg border border-t-0 border-stone-200/80 bg-white/90 text-stone-500 backdrop-blur transition-colors hover:bg-accent/10 hover:text-accent dark:border-stone-800 dark:bg-neutral-950/90" title="展开导图工具" aria-label="展开导图工具" aria-expanded="false">
      <ChevronDown size={16} />
    </button>
  );
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="relative min-h-0 flex-1 w-full overflow-hidden">
        <MindmapCanvas root={mindmap} selectedNodeId={selectedNode?.id ?? null} onSelectNode={onFocusNode} markmapRef={markmapRef} theme={theme} />
        {actionBar}
      </div>
    </div>
  );
}
