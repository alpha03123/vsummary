import { BrainCircuit, FileText, GripVertical, ListChecks, MessageSquare, Network, PanelBottom, PanelRight, PlaySquare, StickyNote, X } from "lucide-react";
import { Mosaic, MosaicWindow } from "react-mosaic-component";

import { WorkspaceStateBlock } from "./shared/WorkspaceStateBlock";
import { getPanelType } from "./workspaceLayout";

const PANEL_META = {
  studio: { label: "工具页", icon: FileText },
  preview: { label: "视频预览", icon: PlaySquare },
  overview: { label: "AI 整理逐字稿", icon: FileText },
  "ai-summary": { label: "AI 概括", icon: ListChecks },
  mindmap: { label: "思维导图", icon: Network },
  "knowledge-cards": { label: "知识卡片", icon: BrainCircuit },
  notes: { label: "笔记", icon: StickyNote },
  "ai-chat": { label: "AI 对话", icon: MessageSquare },
  "series-overview": { label: "全局 AI 概况", icon: FileText },
  "series-mindmap": { label: "全局思维导图", icon: Network },
};

export function WorkspaceStudioPanels({ layout, panelTools, focusedPanel, onFocus, onClose, onSplit, onLayoutChange, renderPanel, renderPanelActions, renderPanelLeadingActions }) {
  return (
    <div className="flex h-full w-full min-w-0 bg-stone-50/40 p-1 dark:bg-neutral-950/30">
      <Mosaic
        value={layout}
        onChange={onLayoutChange}
        className="workspace-mosaic"
        resize={{ minimumPaneSizePercentage: 12 }}
        zeroStateView={<WorkspaceStateBlock title="暂无打开的面板" description="点击顶部加号添加面板。" dashed />}
        renderTile={(panelId, path) => {
          const type = panelTools[panelId] ?? getPanelType(panelId);
          const meta = PANEL_META[type] ?? PANEL_META.studio;
          const Icon = meta.icon;
          const panelActions = renderPanelActions?.(panelId, type);
          const panelLeadingActions = renderPanelLeadingActions?.(panelId, type);
          const isFocused = focusedPanel === panelId;

          return (
            <MosaicWindow
              path={path}
              title={meta.label}
              className={`workspace-mosaic-window ${isFocused ? "workspace-mosaic-window-focused" : ""}`}
              onDragStart={() => onFocus(panelId)}
              renderPreview={() => <div className="workspace-mosaic-drag-preview" aria-hidden="true" />}
              renderToolbar={() => (
                <header className="flex h-full min-w-0 items-center justify-between border-b border-stone-200/80 px-3 py-2 dark:border-stone-800">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <button type="button" onClick={() => onFocus(panelId)} className="inline-flex min-w-0 items-center gap-2 text-left">
                      <GripVertical size={15} className="shrink-0 text-stone-400" aria-hidden="true" />
                      {type === "studio" ? null : <><Icon size={16} className="shrink-0 text-accent" /><span className="truncate text-sm font-bold text-stone-800 dark:text-stone-100">{meta.label}</span></>}
                    </button>
                    {panelLeadingActions ? <div className="shrink-0" onPointerDown={(event) => event.stopPropagation()}>{panelLeadingActions}</div> : null}
                  </div>
                  <div className="ml-auto flex shrink-0 items-center gap-1" onPointerDown={(event) => event.stopPropagation()}>
                    {panelActions}
                    <button type="button" onClick={() => onSplit(panelId, "row")} className="workspace-mosaic-action" title="在右侧拆分面板" aria-label="在右侧拆分面板"><PanelRight size={15} /></button>
                    <button type="button" onClick={() => onSplit(panelId, "column")} className="workspace-mosaic-action" title="在下方拆分面板" aria-label="在下方拆分面板"><PanelBottom size={15} /></button>
                    <button type="button" onClick={() => onClose(panelId)} className="workspace-mosaic-action text-stone-500 hover:bg-danger-subtle hover:text-danger dark:text-stone-400 dark:hover:text-danger" title={`关闭${meta.label}`} aria-label={`关闭${meta.label}`}><X size={15} /></button>
                  </div>
                </header>
              )}
            >
              <div className="h-full min-h-0 overflow-hidden">{renderPanel(panelId, type)}</div>
            </MosaicWindow>
          );
        }}
      />
    </div>
  );
}
