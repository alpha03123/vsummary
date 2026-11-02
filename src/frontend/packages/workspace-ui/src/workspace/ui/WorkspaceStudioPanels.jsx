import { useEffect, useState } from "react";
import { BrainCircuit, FileText, GripVertical, ListChecks, MessageSquare, Network, PanelBottom, PanelRight, PlaySquare, Plus, StickyNote, X } from "lucide-react";
import { Mosaic, MosaicWindow } from "react-mosaic-component";

import { WorkspaceStateBlock } from "./shared/WorkspaceStateBlock";
import { getPanelType, getStudioPanelIds } from "./workspaceLayout";

const PANEL_META = {
  studio: { label: "工具页", icon: FileText },
  preview: { label: "视频预览", icon: PlaySquare },
  overview: { label: "AI 整理逐字稿", icon: FileText },
  "ai-summary": { label: "AI 概括", icon: ListChecks },
  mindmap: { label: "思维导图", icon: Network },
  "knowledge-cards": { label: "知识卡片", icon: BrainCircuit },
  notes: { label: "笔记", icon: StickyNote },
  "ai-chat": { label: "AI 对话", icon: MessageSquare },
  "series-overview": { label: "全局 AI 概括", icon: FileText },
  "series-mindmap": { label: "全局思维导图", icon: Network },
};

export function WorkspaceStudioPanels({ layout, panelTools, focusedPanel, onFocus, onClose, onSplit, onAddPanel, onLayoutChange, renderPanel, renderPanelActions, renderPanelLeadingActions, renderPanelTrailingActions, narrow = false }) {
  const [mosaicLayout, setMosaicLayout] = useState(layout);

  useEffect(() => {
    setMosaicLayout(layout);
  }, [layout]);

  const addPanel = (
    <button type="button" onClick={onAddPanel} className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-on-accent transition-colors hover:bg-accent/90">
      <Plus size={16} aria-hidden="true" />
      添加一个面板
    </button>
  );
  const zeroState = (
    <WorkspaceStateBlock title="暂无打开的面板" description="添加一个面板以开始工作。" dashed>
      {addPanel}
    </WorkspaceStateBlock>
  );

  // Phones show one pane at a time. The saved layout is still the desktop one — tabs only change
  // which pane is visible, so a two-column arrangement made on a laptop never squeezes into 390px.
  if (narrow) {
    const panelIds = getStudioPanelIds(layout);
    if (!panelIds.length) {
      return <div className="flex h-full w-full min-w-0 bg-muted/40 p-1">{zeroState}</div>;
    }
    const activePanelId = panelIds.includes(focusedPanel) ? focusedPanel : panelIds[0];
    const activeType = panelTools[activePanelId] ?? getPanelType(activePanelId);
    const meta = PANEL_META[activeType] ?? PANEL_META.studio;
    return (
      <div className="flex h-full w-full min-w-0 flex-col bg-muted/40">
        <header className="flex shrink-0 items-center gap-1 border-b border-line/80 px-1.5 py-1.5">
          <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
            {panelIds.map((panelId) => {
              const type = panelTools[panelId] ?? getPanelType(panelId);
              const panelMeta = PANEL_META[type] ?? PANEL_META.studio;
              const PanelIcon = panelMeta.icon;
              const active = panelId === activePanelId;
              return (
                <button key={panelId} type="button" onClick={() => onFocus(panelId)} aria-pressed={active} title={panelMeta.label}
                  className={`inline-flex h-9 shrink-0 items-center gap-1.5 rounded-xl px-2.5 text-xs font-semibold transition-colors ${active ? "bg-accent/10 text-accent" : "text-subtle hover:bg-soft"}`}>
                  <PanelIcon size={15} className="shrink-0" aria-hidden="true" />
                  <span className="max-w-[9rem] truncate">{panelMeta.label}</span>
                </button>
              );
            })}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {renderPanelLeadingActions?.(activePanelId, activeType)}
            {renderPanelActions?.(activePanelId, activeType)}
            {renderPanelTrailingActions?.(activePanelId, activeType)}
            {panelIds.length > 1 ? <button type="button" onClick={() => onClose(activePanelId)} className="workspace-mosaic-action text-faint hover:bg-danger-subtle hover:text-danger dark:hover:text-danger" title={`关闭${meta.label}`} aria-label={`关闭${meta.label}`}><X size={15} /></button> : null}
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-hidden">{renderPanel(activePanelId, activeType)}</div>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full min-w-0 bg-muted/40 p-1">
      <Mosaic
        value={mosaicLayout}
        onChange={setMosaicLayout}
        onRelease={onLayoutChange}
        className="workspace-mosaic"
        resize={{ minimumPaneSizePercentage: 12 }}
        zeroStateView={zeroState}
        renderTile={(panelId, path) => {
          const type = panelTools[panelId] ?? getPanelType(panelId);
          const meta = PANEL_META[type] ?? PANEL_META.studio;
          const Icon = meta.icon;
          const panelActions = renderPanelActions?.(panelId, type);
          const panelLeadingActions = renderPanelLeadingActions?.(panelId, type);
          const panelTrailingActions = renderPanelTrailingActions?.(panelId, type);
          const isFocused = focusedPanel === panelId;

          return (
            <MosaicWindow
              path={path}
              title={meta.label}
              className={`workspace-mosaic-window ${isFocused ? "workspace-mosaic-window-focused" : ""}`}
              onDragStart={() => onFocus(panelId)}
              renderPreview={() => <div className="workspace-mosaic-drag-preview" aria-hidden="true" />}
              renderToolbar={() => (
                <header className="flex h-full min-w-0 items-center justify-between border-b border-line/80 px-3 py-2">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <button type="button" onClick={() => onFocus(panelId)} className="inline-flex min-w-0 items-center gap-2 text-left">
                      <GripVertical size={15} className="shrink-0 text-faint" aria-hidden="true" />
                      {type === "studio" ? null : <><Icon size={16} className="shrink-0 text-accent" /><span className="truncate text-sm font-bold text-body">{meta.label}</span></>}
                    </button>
                    {panelLeadingActions ? <div className="shrink-0" onPointerDown={(event) => event.stopPropagation()}>{panelLeadingActions}</div> : null}
                  </div>
                  <div className="ml-auto flex min-w-0 flex-1 items-center" onPointerDown={(event) => event.stopPropagation()}>
                    <div className="ml-auto flex shrink-0 items-center gap-1">
                      {panelActions}
                      <button type="button" onClick={() => onSplit(panelId, "row")} className="workspace-mosaic-action workspace-mosaic-split" title="在右侧拆分面板" aria-label="在右侧拆分面板"><PanelRight size={15} /></button>
                      <button type="button" onClick={() => onSplit(panelId, "column")} className="workspace-mosaic-action workspace-mosaic-split" title="在下方拆分面板" aria-label="在下方拆分面板"><PanelBottom size={15} /></button>
                      <button type="button" onClick={() => onClose(panelId)} className="workspace-mosaic-action text-faint hover:bg-danger-subtle hover:text-danger dark:hover:text-danger" title={`关闭${meta.label}`} aria-label={`关闭${meta.label}`}><X size={15} /></button>
                    </div>
                    {panelTrailingActions ? <div className="ml-2 shrink-0">{panelTrailingActions}</div> : null}
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
