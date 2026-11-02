import {
  BookOpenText,
  MessageSquare,
  Settings2,
  PanelLeftClose,
  PanelLeftOpen,
  BarChart3,
} from "lucide-react";



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
  toolbarExtras,
  toolbarTrailing,
  toolbarButtons,
  brand,
}) {

  return (
    <header className="workspace-toolbar-surface flex justify-between items-center gap-2 px-3 py-2 border-b border-line/80 sticky top-0 z-20 shrink-0 md:px-6 md:py-2.5">
      <div className="flex min-w-0 items-center gap-2 md:gap-4">
        {/* Sidebar Toggle: only inside a series; the home page has no sidebar. */}
        {onToggleSidebar ? (
          <button
            onClick={onToggleSidebar}
            className="flex items-center justify-center w-9 h-9 rounded-xl text-subtle hover:bg-soft hover:text-strong transition-colors md:mr-2"
            aria-label={isSidebarOpen ? "收起视频列表" : "展开视频列表"}
          >
            {isSidebarOpen ? <PanelLeftClose size={20} /> : <PanelLeftOpen size={20} />}
          </button>
        ) : null}

        {brand && activeSeries && onEnterLibraryHome ? (
          <button type="button" onClick={onEnterLibraryHome} aria-label="回到首页" className="rounded-xl transition-opacity hover:opacity-75">{brand}</button>
        ) : brand ?? <div className="flex min-w-0 items-center gap-4">
          <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-surface text-strong shadow-sm border border-line">
            <BookOpenText size={17} strokeWidth={2.1} />
          </div>
          <div className="min-w-0">
            {/* 侧栏展开时它的头部就在左边显示当前系列名，这里再复述一次会让
                "同一句话"在一屏里出现两次。所以工具栏只在侧栏收起、上下文
                丢失时兜底显示系列名，其余时候显示应用身份。 */}
            <h1 className="block truncate text-lg font-bold leading-tight text-strong">
              {isSidebarOpen || !activeSeries ? "知识工作台" : activeSeries.title}
            </h1>
          </div>
        </div>}
      </div>

      <div className="flex shrink-0 items-center gap-1 md:gap-3">
        {toolbarExtras}
        {onToggleChatDrawer ? (
          <button
            type="button"
            className={`inline-flex h-10 w-10 items-center justify-center rounded-full transition-colors ${chatDrawerOpen ? "bg-softer text-strong" : "text-subtle hover:bg-soft hover:text-strong"}`}
            onClick={onToggleChatDrawer}
            title={toolbarButtons?.assistant?.label ?? "打开分析助手"}
            aria-label={toolbarButtons?.assistant?.label ?? "打开分析助手"}
            aria-expanded={chatDrawerOpen}
          >
            {toolbarButtons?.assistant?.icon ?? <MessageSquare size={18} strokeWidth={2.2} />}
          </button>
        ) : null}
        {/* Host items that belong after the assistant button (renderToolbar items go before it). */}
        {toolbarTrailing}
        {onOpenUsagePage && (<button
          className={`inline-flex h-10 items-center justify-center gap-1.5 rounded-full transition-colors hover:bg-soft hover:text-strong text-subtle ${toolbarButtons?.usage?.text ? "w-10 md:w-auto md:px-3" : "w-10"}`}
          onClick={onOpenUsagePage}
          title={toolbarButtons?.usage?.label ?? "打开用量统计"}
          aria-label={toolbarButtons?.usage?.label ?? "打开用量统计"}
        >
          {toolbarButtons?.usage?.icon ?? <BarChart3 size={18} strokeWidth={2.2} />}
          {/* Hosts can spell out an entry that matters to them (e.g. daily check-in); icon-only on phones. */}
          {toolbarButtons?.usage?.text ? <span className="hidden text-sm font-semibold md:inline">{toolbarButtons.usage.text}</span> : null}
        </button>)}
        {onToggleSettingsPanel && (<button
          className={`inline-flex items-center justify-center w-10 h-10 rounded-full transition-colors ${settingsOpen ? "bg-softer text-strong border border-line-strong shadow-sm" : "text-subtle hover:bg-soft hover:text-strong"}`}
          onClick={onToggleSettingsPanel}
          title={toolbarButtons?.settings?.label ?? "设置"}
          aria-label={toolbarButtons?.settings?.label ?? "设置"}
          aria-expanded={settingsOpen}
        >
          {toolbarButtons?.settings?.icon ?? <Settings2 size={18} strokeWidth={2.2} />}
        </button>)}
      </div>
    </header>
  );
}
