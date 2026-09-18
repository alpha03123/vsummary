import { useState } from "react";
import { BrainCircuit, FileText, GripVertical, MessageSquare, Network, PlaySquare, StickyNote, X } from "lucide-react";

import { WorkspaceStateBlock } from "./shared/WorkspaceStateBlock";
import { getPanelType, WORKSPACE_LAYOUT_LIMITS } from "./workspaceLayout";

const PANEL_META = {
  studio: { label: "工具页", icon: FileText },
  preview: { label: "视频预览", icon: PlaySquare },
  overview: { label: "AI 整理逐字稿", icon: FileText },
  "ai-summary": { label: "AI 概括", icon: FileText },
  mindmap: { label: "思维导图", icon: Network },
  "knowledge-cards": { label: "知识卡片", icon: BrainCircuit },
  notes: { label: "笔记", icon: StickyNote },
  "ai-chat": { label: "AI 对话", icon: MessageSquare },
  "series-overview": { label: "全局 AI 概况", icon: FileText },
  "series-mindmap": { label: "全局思维导图", icon: Network },
};

export function WorkspaceStudioPanels({ panels, panelWidths, panelTools, focusedPanel, onFocus, onClose, onResizeStart, onReorder, renderPanel, renderPanelActions, renderPanelLeadingActions }) {
  const [draggedPanelId, setDraggedPanelId] = useState(null);

  function handleDrop(targetPanelId) {
    if (draggedPanelId && draggedPanelId !== targetPanelId) {
      onReorder(draggedPanelId, targetPanelId);
    }
    setDraggedPanelId(null);
  }

  return (
    <div className="flex h-full w-full min-w-0 bg-stone-50/40 dark:bg-neutral-950/30">
      {panels.length ? (
        <div className="flex h-full min-h-0 min-w-0 flex-1 overflow-x-auto">
          {panels.map((panel, index) => {
            const type = panelTools[panel] ?? getPanelType(panel);
            const meta = PANEL_META[type] ?? PANEL_META.studio;
            const Icon = meta.icon;
            const panelActions = renderPanelActions?.(panel, type);
            const panelLeadingActions = renderPanelLeadingActions?.(panel, type);
            return (
              <div key={panel} className={`flex h-full min-h-0 min-w-[320px] flex-1 transition-opacity ${draggedPanelId === panel ? "opacity-45" : ""}`} style={{ flexBasis: `${panelWidths[panel] ?? WORKSPACE_LAYOUT_LIMITS.panelDefaultWidth}px` }} onDragOver={(event) => event.preventDefault()} onDrop={() => handleDrop(panel)}>
                <section className="workspace-panel flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden border">
                  <header draggable onDragStart={(event) => { event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", panel); setDraggedPanelId(panel); }} onDragEnd={() => setDraggedPanelId(null)} className="flex shrink-0 cursor-grab items-center justify-between border-b border-stone-200/80 px-4 py-2.5 active:cursor-grabbing dark:border-stone-800">
                    <div className="flex min-w-0 items-center gap-1.5">
                      <button type="button" onClick={() => onFocus(panel)} className="inline-flex min-w-0 items-center gap-2 text-left">
                        <GripVertical size={15} className="shrink-0 text-stone-400" aria-hidden="true" />
                        {type === "studio" ? null : <><Icon size={16} className="shrink-0 text-accent" /><span className="truncate text-sm font-bold text-stone-800 dark:text-stone-100">{meta.label}</span></>}
                      </button>
                      {panelLeadingActions ? <div className="shrink-0" onPointerDown={(event) => event.stopPropagation()}>{panelLeadingActions}</div> : null}
                    </div>
                    <div className="ml-auto flex shrink-0 items-center gap-1" onPointerDown={(event) => event.stopPropagation()}>
                      {panelActions}
                      <button type="button" draggable={false} onClick={(event) => { event.stopPropagation(); onClose(panel); }} className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-stone-500 transition hover:bg-danger-subtle hover:text-danger dark:text-stone-400 dark:hover:text-danger" title={`关闭${meta.label}`} aria-label={`关闭${meta.label}`}><X size={15} /></button>
                    </div>
                  </header>
                  <div className="min-h-0 flex-1 overflow-hidden">{renderPanel(panel, type)}</div>
                </section>
                {index < panels.length - 1 ? <div role="separator" aria-orientation="vertical" aria-label="调整面板宽度" onPointerDown={(event) => onResizeStart(panel, event)} className="group relative z-20 -mx-1 w-5 shrink-0 cursor-col-resize touch-none"><div className="absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 rounded-full bg-stone-200 transition group-hover:bg-accent dark:bg-stone-800 dark:group-hover:bg-accent" /></div> : null}
              </div>
            );
          })}
        </div>
      ) : <div className="flex min-h-0 flex-1 items-center justify-center p-8"><WorkspaceStateBlock title="暂无打开的面板" description="点击顶部加号添加面板。" dashed /></div>}
    </div>
  );
}
