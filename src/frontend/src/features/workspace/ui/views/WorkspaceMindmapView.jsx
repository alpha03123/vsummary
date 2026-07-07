import { LoaderCircle, Network } from "lucide-react";

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
}) {
  const hasMindmap = Boolean(mindmap);

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
        {isGeneratingMindmapSelectedVideo ? (
          <div className="motion-fade-up mt-6 w-full max-w-2xl">
            <div className="workspace-elevated-panel rounded-3xl border p-5">
              <div className="motion-shimmer h-4 w-28 rounded-full bg-stone-100 dark:bg-stone-800"></div>
              <div className="motion-shimmer mt-5 h-[220px] w-full rounded-[1.5rem] bg-stone-100 dark:bg-stone-800"></div>
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
      <div className="h-full w-full">
        <MindmapCanvas root={mindmap} selectedNodeId={selectedNode?.id ?? null} onSelectNode={onFocusNode} />
      </div>
    </div>
  );
}
