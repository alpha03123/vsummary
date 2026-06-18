import { useState, useEffect, useRef } from "react";
import { LoaderCircle, Network, Download, RefreshCw } from "lucide-react";

import { MindmapCanvas } from "../MindmapCanvas";
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
}) {
  const hasMindmap = Boolean(mindmap);

  const [exportOpen, setExportOpen] = useState(false);
  const exportRef = useRef(null);

  useEffect(() => {
    if (!exportOpen) return;
    const handler = (e) => {
      if (exportRef.current && !exportRef.current.contains(e.target)) {
        setExportOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [exportOpen]);

  function handleExportPNG(filename) {
    const svgEl = document.querySelector(".workspace-elevated-panel svg");
    if (!svgEl) return;
    const svgData = new XMLSerializer().serializeToString(svgEl);
    const canvas = document.createElement("canvas");
    canvas.width = svgEl.clientWidth * 2;
    canvas.height = svgEl.clientHeight * 2;
    const ctx = canvas.getContext("2d");
    ctx.scale(2, 2);
    const img = new Image();
    img.onload = () => {
      ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--color-bg") || "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      const a = document.createElement("a");
      a.download = filename;
      a.href = canvas.toDataURL("image/png");
      a.click();
    };
    img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(svgData)));
  }

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
        description="思维导图不是默认产物。点击下面按钮后，后端会基于当前 AI 概况单独生成 `mindmap.json`。"
      >
        <button
          type="button"
          onClick={onGenerateMindmap}
          disabled={isGeneratingMindmapSelectedVideo}
          className={`inline-flex items-center gap-2 rounded-2xl px-5 py-3 text-sm font-semibold transition-all ${
            isGeneratingMindmapSelectedVideo
              ? "motion-busy-button cursor-not-allowed bg-stone-200 text-stone-500"
              : "bg-accent text-white shadow-sm hover:bg-accent/90"
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
        {isGeneratingMindmapSelectedVideo && mindmapGenerationProgress ? (
          <div className="motion-fade-up mt-6 w-full max-w-2xl">
            <div className="workspace-elevated-panel rounded-3xl border p-5 flex items-center gap-3">
              <LoaderCircle size={18} strokeWidth={2.2} className="animate-spin text-accent" />
              <p className="text-sm text-stone-600 dark:text-zinc-400">
                {mindmapGenerationProgress.detail || "正在生成思维导图"}
                <span className="mx-2 text-stone-300 dark:text-zinc-600">·</span>
                <span className="font-medium text-stone-700 dark:text-zinc-200">
                  已用 {Math.round(mindmapGenerationProgress.elapsed_seconds ?? 0)} 秒
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

  return (
    <div className="workspace-elevated-panel relative h-full min-h-[500px] w-full overflow-hidden rounded-3xl border outline-dashed outline-1 outline-offset-4 outline-stone-200 dark:outline-stone-800">
      <div className="pointer-events-none absolute top-4 left-4 z-10">
        <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Mindmap</p>
      </div>
      <div className="pointer-events-auto absolute top-4 right-4 z-10 flex items-center gap-2">
        <button
          type="button"
          onClick={onGenerateMindmap}
          disabled={isGeneratingMindmapSelectedVideo}
          className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RefreshCw size={14} strokeWidth={2} className={isGeneratingMindmapSelectedVideo ? "animate-spin" : ""} />
          重新生成
        </button>
        <div className="relative" ref={exportRef}>
          <button
            type="button"
            onClick={() => setExportOpen(!exportOpen)}
            className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-accent hover:bg-accent/10 transition-colors"
          >
            <Download size={14} strokeWidth={2} />
            导出
          </button>
          {exportOpen && (
            <div className="absolute right-0 top-full mt-1 z-20 rounded-xl border border-stone-200 bg-white dark:bg-neutral-900 shadow-lg py-1 min-w-[130px]">
              <a
                href={`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap/export?format=md`}
                download
                className="block px-4 py-2 text-xs text-stone-700 dark:text-zinc-300 hover:bg-stone-50 dark:hover:bg-neutral-800"
                onClick={() => setExportOpen(false)}
              >
                Markdown (.md)
              </a>
              <a
                href={`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap/export?format=html`}
                download
                className="block px-4 py-2 text-xs text-stone-700 dark:text-zinc-300 hover:bg-stone-50 dark:hover:bg-neutral-800"
                onClick={() => setExportOpen(false)}
              >
                HTML (.html)
              </a>
              <button
                type="button"
                className="block w-full text-left px-4 py-2 text-xs text-stone-700 dark:text-zinc-300 hover:bg-stone-50 dark:hover:bg-neutral-800"
                onClick={() => {
                  setExportOpen(false);
                  handleExportPNG(`mindmap-${videoId}.png`);
                }}
              >
                PNG (.png)
              </button>
            </div>
          )}
        </div>
      </div>
      <div className="h-full w-full">
        <MindmapCanvas root={mindmap} selectedNodeId={selectedNode?.id ?? null} onSelectNode={onFocusNode} />
      </div>
    </div>
  );
}
