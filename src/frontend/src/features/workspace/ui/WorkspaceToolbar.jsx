import { useEffect, useRef } from "react";
import {
  ArrowLeft,
  BookOpenText,
  Settings2,
  PanelLeftClose,
  PanelLeftOpen
} from "lucide-react";

export function WorkspaceToolbar({
  activeSeries,
  onEnterLibraryHome,
  settingsOpen,
  onToggleSettingsPanel,
  isSidebarOpen,
  onToggleSidebar,
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
    <header className="flex justify-between items-center px-6 py-4 border-b border-stone-200 bg-white/90 backdrop-blur-md sticky top-0 z-20 shrink-0">
      <div className="flex items-center gap-4">
        {/* Sidebar Toggle */}
        <button
          onClick={onToggleSidebar}
          className="flex items-center justify-center w-10 h-10 rounded-xl text-stone-500 hover:bg-stone-100 hover:text-stone-900 transition-colors mr-2"
          aria-label={isSidebarOpen ? "收起文献库" : "展开文献库"}
        >
          {isSidebarOpen ? <PanelLeftClose size={22} /> : <PanelLeftOpen size={22} />}
        </button>

        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-stone-900 text-stone-50 shadow-sm">
            <BookOpenText size={20} strokeWidth={2.1} />
          </div>
          <div>
            <h1 className="text-lg font-bold text-stone-900 leading-tight block">{activeSeries ? activeSeries.title : "Workspace"}</h1>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {activeSeries ? (
          <button
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-stone-200 bg-white text-stone-700 hover:bg-stone-50 hover:text-stone-900 transition-all font-medium text-sm shadow-sm active:scale-95"
            onClick={onEnterLibraryHome}
            type="button"
          >
            <ArrowLeft size={16} strokeWidth={2.1} />
            返回列表
          </button>
        ) : null}
        <button
          ref={settingsButtonRef}
          className={`inline-flex items-center justify-center w-10 h-10 rounded-full transition-all ${settingsOpen ? "bg-teal-50 text-teal-700" : "text-stone-500 hover:bg-stone-100 hover:text-stone-900"}`}
          onClick={onToggleSettingsPanel}
          title="Open Settings"
          aria-label="打开界面设置"
          aria-expanded={settingsOpen}
        >
          <Settings2 size={18} strokeWidth={2.2} />
        </button>
      </div>
    </header>
  );
}
