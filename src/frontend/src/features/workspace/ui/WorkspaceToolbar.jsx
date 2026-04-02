import { useEffect, useRef } from "react";
import {
  BookOpenText,
  PanelLeft,
  Settings2,
} from "lucide-react";

export function WorkspaceToolbar({
  mindmapVisible,
  settingsOpen,
  onToggleMindmapVisibility,
  onToggleSettingsPanel,
}) {
  const settingsButtonRef = useRef(null);

  useEffect(() => {
    if (!settingsOpen) {
      return undefined;
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        settingsButtonRef.current?.click();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [settingsOpen]);

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
        <button
          ref={settingsButtonRef}
          className={`panel-toggle${settingsOpen ? " is-active" : ""}`}
          onClick={onToggleSettingsPanel}
          title="Open Settings"
          aria-label="打开界面设置"
          aria-expanded={settingsOpen}
        >
          <Settings2 size={20} strokeWidth={2.2} />
        </button>
      </div>
    </header>
  );
}
