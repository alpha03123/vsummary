import { useEffect, useRef } from "react";
import {
  BookOpenText,
  Settings2,
} from "lucide-react";

export function WorkspaceToolbar({
  settingsOpen,
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
      <div className="topbar-main">
        <div className="brand-block">
          <div className="brand-icon">
            <BookOpenText size={24} strokeWidth={2.1} />
          </div>
          <div>
            <p className="eyebrow">Videos Library Workspace</p>
            <h1 className="brand-title">Video Include</h1>
          </div>
        </div>
        <div className="topbar-copy">
          <strong>videos / series / video</strong>
          <span>主页先浏览素材库，再进入单个视频的生成结果与阅读。</span>
        </div>
      </div>

      <div className="toolbar">
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
