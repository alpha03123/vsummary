import { useEffect, useRef } from "react";
import {
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
    <header className="workspace-toolbar-surface flex justify-between items-center px-6 py-4 border-b border-stone-200/80 dark:border-stone-800 sticky top-0 z-20 shrink-0">
      <div className="flex items-center gap-4">
        {/* Sidebar Toggle */}
        <button
          onClick={onToggleSidebar}
          className="flex items-center justify-center w-10 h-10 rounded-xl text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-900 dark:hover:text-stone-100 transition-colors mr-2"
          aria-label={isSidebarOpen ? "收起文献库" : "展开文献库"}
        >
          {isSidebarOpen ? <PanelLeftClose size={22} /> : <PanelLeftOpen size={22} />}
        </button>

        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-white text-black shadow-sm dark:bg-neutral-900 dark:text-white border border-stone-200 dark:border-white/10">
            <BookOpenText size={20} strokeWidth={2.1} />
          </div>
          <div>
            <h1 className="text-lg font-bold text-stone-900 dark:text-stone-100 leading-tight block">{activeSeries ? activeSeries.title : "Workspace"}</h1>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          ref={settingsButtonRef}
          className={`inline-flex items-center justify-center w-10 h-10 rounded-full transition-colors ${settingsOpen ? "bg-stone-200 dark:bg-stone-800 text-stone-900 dark:text-white border border-stone-300 dark:border-stone-700 shadow-sm" : "text-stone-500 dark:text-zinc-400 hover:bg-stone-100 dark:hover:bg-neutral-900 hover:text-stone-900 dark:hover:text-white"}`}
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
