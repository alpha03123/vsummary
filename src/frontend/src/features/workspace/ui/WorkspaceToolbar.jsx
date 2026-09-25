import {
  BookOpenText,
  MessageSquare,
  Settings2,
  PanelLeftClose,
  PanelLeftOpen,
  BarChart3,
} from "lucide-react";
import { useEffect, useState } from "react";
import { loadApplicationUpdateStatus } from "../../../local-features/api/localWorkspaceApi";

export function WorkspaceToolbar({
  activeSeries,
  onEnterLibraryHome,
  settingsOpen,
  onToggleSettingsPanel,
  isSidebarOpen,
  onToggleSidebar,
  onToggleChatDrawer,
  chatDrawerOpen = false,
  onOpenUsagePage,
  onOpenUpdate,
}) {
  const [versionStatus, setVersionStatus] = useState({ version: "Source", state: "source" });

  useEffect(() => {
    let cancelled = false;
    loadApplicationUpdateStatus()
      .then((status) => {
        if (cancelled) {
          return;
        }
        setVersionStatus({
          version: status.installationKind === "source" ? "Source" : status.currentVersion,
          state: status.updateAvailable ? "available" : status.installationKind === "source" ? "source" : "current",
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <header className="workspace-toolbar-surface flex justify-between items-center px-6 py-2.5 border-b border-stone-200/80 dark:border-stone-800 sticky top-0 z-20 shrink-0">
      <div className="flex items-center gap-4">
        {/* Sidebar Toggle */}
        <button
          onClick={onToggleSidebar}
          className="flex items-center justify-center w-9 h-9 rounded-xl text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-900 dark:hover:text-stone-100 transition-colors mr-2"
          aria-label={isSidebarOpen ? "收起文献库" : "展开文献库"}
        >
          {isSidebarOpen ? <PanelLeftClose size={20} /> : <PanelLeftOpen size={20} />}
        </button>

        <div className="flex min-w-0 items-center gap-4">
          <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-white text-black shadow-sm dark:bg-neutral-900 dark:text-white border border-stone-200 dark:border-white/10">
            <BookOpenText size={17} strokeWidth={2.1} />
          </div>
          <div className="min-w-0">
            {/* 侧栏展开时它的头部就在左边显示当前系列名，这里再复述一次会让
                "同一句话"在一屏里出现两次。所以工具栏只在侧栏收起、上下文
                丢失时兜底显示系列名，其余时候显示应用身份。 */}
            <h1 className="block truncate text-lg font-bold leading-tight text-stone-900 dark:text-stone-100">
              {isSidebarOpen || !activeSeries ? "知识工作台" : activeSeries.title}
            </h1>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex items-center gap-1">
        {versionStatus.state === "available" ? (
          <button
            type="button"
            onClick={onOpenUpdate}
            title="发现新版本，打开更新页面"
            aria-label={`发现新版本，当前 ${versionStatus.version}，打开更新页面`}
            className="rounded-full border border-accent/30 bg-accent/10 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-accent transition-colors hover:bg-accent/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 dark:border-accent/40 dark:bg-accent/15 dark:hover:bg-accent/20"
          >
            {versionStatus.version}
          </button>
        ) : (
          <span className="rounded-full border border-stone-200/80 bg-stone-50 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-stone-600 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-400">
            {versionStatus.version}
          </span>
        )}
        </div>
        {onToggleChatDrawer ? (
          <button
            type="button"
            className={`inline-flex h-10 w-10 items-center justify-center rounded-full transition-colors ${chatDrawerOpen ? "bg-stone-200 text-stone-900 dark:bg-stone-800 dark:text-white" : "text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-zinc-400 dark:hover:bg-neutral-900 dark:hover:text-white"}`}
            onClick={onToggleChatDrawer}
            title="打开分析助手"
            aria-label="打开分析助手"
            aria-expanded={chatDrawerOpen}
          >
            <MessageSquare size={18} strokeWidth={2.2} />
          </button>
        ) : null}
        <button
          className="inline-flex items-center justify-center w-10 h-10 rounded-full transition-colors hover:bg-stone-100 dark:hover:bg-neutral-900 hover:text-stone-900 dark:hover:text-white text-stone-600 dark:text-zinc-400"
          onClick={onOpenUsagePage}
          title="打开用量统计"
          aria-label="打开用量统计"
        >
          <BarChart3 size={18} strokeWidth={2.2} />
        </button>
        <button
          className={`inline-flex items-center justify-center w-10 h-10 rounded-full transition-colors ${settingsOpen ? "bg-stone-200 dark:bg-stone-800 text-stone-900 dark:text-white border border-stone-300 dark:border-stone-700 shadow-sm" : "text-stone-600 dark:text-zinc-400 hover:bg-stone-100 dark:hover:bg-neutral-900 hover:text-stone-900 dark:hover:text-white"}`}
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
