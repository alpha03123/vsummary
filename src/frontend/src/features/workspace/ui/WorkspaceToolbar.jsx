import {
  BookOpenText,
  PanelLeft,
} from "lucide-react";

export function WorkspaceToolbar({
  mindmapVisible,
  onToggleMindmapVisibility,
}) {
  return (
    <header className="topbar">
      <div className="brand-block">
        <div className="brand-icon">
          <BookOpenText size={24} strokeWidth={2.1} />
        </div>
        <div>
          <p className="eyebrow">Editorial Knowledge Workspace</p>
          <h1 className="brand-title">Video Include</h1>
        </div>
      </div>

      <div className="toolbar">
        <button
          className={`panel-toggle${mindmapVisible ? " is-active" : ""}`}
          onClick={onToggleMindmapVisibility}
          title="Toggle Mindmap"
          aria-label="切换思维导图面板"
          aria-pressed={mindmapVisible}
        >
          <PanelLeft size={20} strokeWidth={2.2} />
        </button>
      </div>
    </header>
  );
}
