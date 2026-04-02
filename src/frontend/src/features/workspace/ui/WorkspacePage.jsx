import { useState } from "react";
import { WorkspaceLibraryPanel } from "./WorkspaceLibraryPanel";
import { WorkspaceReadingPane } from "./WorkspaceReadingPane";
import { WorkspaceSeriesGrid } from "./WorkspaceSeriesGrid";
import { WorkspaceSettingsPanel } from "./WorkspaceSettingsPanel";
import { WorkspaceToolbar } from "./WorkspaceToolbar";
import { WorkspaceChatPanel } from "./WorkspaceChatPanel";

export function WorkspacePage({
  state,
  ui,
  library,
  tools,
  summary,
  mindmap,
  activeSeries,
  selectedVideo,
  selectedNode,
  previewUrl,
  isGeneratingMindmapSelectedVideo,
  isGeneratingSelectedVideo,
  onSelectSeries,
  onEnterLibraryHome,
  onSelectVideo,
  onSelectTool,
  onFocusNode,
  onGenerateVideo,
  onGenerateMindmap,
  onToggleSettingsPanel,
  onCloseSettingsPanel,
  onChangeSetting,
  onResetSettings,
}) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  if (state.loading && !summary) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-stone-50">
        <div className="bg-white rounded-3xl p-8 border border-stone-200 shadow-xl max-w-md text-center">
          <p className="text-teal-700 text-sm font-bold tracking-widest uppercase mb-2">Preparing Workspace</p>
          <h1 className="text-2xl font-bold text-stone-900 mb-3">正在载入知识工作台</h1>
          <p className="text-stone-500">正在扫描 `videos/` 目录并构建当前工作区。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-stone-50 p-4 gap-4">
      {/* Left Sidebar (Sources) */}
      <aside 
        className={`shrink-0 flex flex-col bg-white rounded-[2rem] border border-stone-200/80 shadow-sm overflow-hidden relative z-10 transition-all duration-300 ease-in-out ${isSidebarOpen ? "w-[320px] xl:w-[340px] opacity-100 mr-1" : "w-0 opacity-0 border-0 m-0"}`}
      >
        <div className="w-[320px] xl:w-[340px] h-full flex flex-col">
          {activeSeries ? (
            <WorkspaceLibraryPanel
              activeSeries={activeSeries}
              selectedVideo={selectedVideo}
              isGeneratingSelectedVideo={isGeneratingSelectedVideo}
              onEnterLibraryHome={onEnterLibraryHome}
              onSelectVideo={onSelectVideo}
              onGenerateVideo={onGenerateVideo}
            />
          ) : (
            <div className="p-8 flex flex-col h-full bg-stone-50/50">
              <h2 className="text-xl font-bold text-stone-800">所有书架 (Series)</h2>
              <p className="text-stone-500 text-sm mt-3 leading-relaxed">在右侧选择大分类，即可在此浏览该目录下的视频知识源。</p>
              {/* Visual filler to mimic NotebookLM empty sources list */}
              <div className="mt-8 flex flex-col gap-3 opacity-30 pointer-events-none">
                <div className="h-16 rounded-2xl bg-stone-200 w-full animate-pulse"></div>
                <div className="h-16 rounded-2xl bg-stone-200 w-full animate-pulse delay-75"></div>
                <div className="h-16 rounded-2xl bg-stone-200 w-3/4 animate-pulse delay-150"></div>
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* Main Studio Area */}
      <main className="flex-1 min-w-0 flex flex-col relative bg-white rounded-[2rem] border border-stone-200/80 shadow-xl shadow-stone-200/20 overflow-hidden z-10">
        <WorkspaceToolbar
          settingsOpen={state.settingsPanelOpen}
          activeSeries={activeSeries}
          onEnterLibraryHome={onEnterLibraryHome}
          onToggleSettingsPanel={onToggleSettingsPanel}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        />

        {state.error && (
          <div className="mx-6 mt-4 p-4 rounded-2xl bg-red-50 text-red-800 border border-red-100 text-sm flex-shrink-0 relative z-20">
            {state.error}
          </div>
        )}

        <div className="flex-1 min-h-0 relative flex overflow-hidden bg-stone-50/30">
          {!activeSeries ? (
            <div className="flex-1 overflow-auto h-full px-4 xl:px-8 bg-white">
              <WorkspaceSeriesGrid library={library} onOpenSeries={onSelectSeries} />
            </div>
          ) : (
            <>
              {/* Center AI Chat */}
              <section className="flex-1 min-w-[380px] h-full overflow-hidden block">
                 <WorkspaceChatPanel
                   selectedVideo={selectedVideo}
                   selectedToolId={state.selectedToolId}
                   tools={tools}
                   onSelectTool={onSelectTool}
                 />
              </section>

              {/* Right Reading Pane */}
              <section className="w-[45vw] xl:w-[760px] shrink-0 h-full overflow-hidden shadow-[-8px_0_24px_-12px_rgba(0,0,0,0.08)] relative z-10 border-l border-stone-200/60 transition-all">
                <WorkspaceReadingPane
                  ui={ui}
                  tools={tools}
                  library={library}
                  summary={summary}
                  mindmap={mindmap}
                  activeSeries={activeSeries}
                  selectedVideo={selectedVideo}
                  selectedNode={selectedNode}
                  previewUrl={previewUrl}
                  selectedToolId={state.selectedToolId}
                  selectedChapterId={state.selectedChapterId}
                  toolsLoading={state.toolsLoading}
                  summaryLoading={state.summaryLoading}
                  mindmapLoading={state.mindmapLoading}
                  isGeneratingMindmapSelectedVideo={isGeneratingMindmapSelectedVideo}
                  isGeneratingSelectedVideo={isGeneratingSelectedVideo}
                  onSelectTool={onSelectTool}
                  onFocusNode={onFocusNode}
                  onGenerateMindmap={onGenerateMindmap}
                />
              </section>
            </>
          )}
        </div>

        {/* Settings Overlay */}
        {state.settingsPanelOpen && (
          <div className="absolute inset-0 z-50 bg-stone-900/10 backdrop-blur-sm flex justify-end items-start p-6 animate-in fade-in duration-200">
            <WorkspaceSettingsPanel
              ui={ui}
              onChangeSetting={onChangeSetting}
              onResetSettings={onResetSettings}
              onClose={onCloseSettingsPanel}
            />
          </div>
        )}
      </main>
    </div>
  );
}
