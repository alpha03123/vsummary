import { WorkspaceLibraryPanel } from "./WorkspaceLibraryPanel";
import { MindmapCanvas } from "./MindmapCanvas";
import { WorkspaceReadingPane } from "./WorkspaceReadingPane";
import { WorkspaceSettingsPanel } from "./WorkspaceSettingsPanel";
import { WorkspaceToolbar } from "./WorkspaceToolbar";

export function WorkspacePage({
  state,
  ui,
  library,
  summary,
  activeSeries,
  selectedVideo,
  selectedNode,
  isGeneratingSelectedVideo,
  onSelectSeries,
  onSelectVideo,
  onGenerateVideo,
  onToggleMindmapVisibility,
  onToggleSettingsPanel,
  onCloseSettingsPanel,
  onChangeSetting,
  onResetSettings,
  onFocusNode,
}) {
  if (state.loading && !summary) {
    return (
      <div className="loading-screen">
        <div className="loading-card">
          <p className="eyebrow">Preparing Workspace</p>
          <h1>正在载入知识工作台</h1>
          <p>正在扫描 `videos/` 目录并构建当前工作区。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-shell">
      <WorkspaceToolbar
        mindmapVisible={ui.mindmapVisible}
        settingsOpen={state.settingsPanelOpen}
        onToggleMindmapVisibility={onToggleMindmapVisibility}
        onToggleSettingsPanel={onToggleSettingsPanel}
      />

      {state.settingsPanelOpen ? (
        <WorkspaceSettingsPanel
          ui={ui}
          onChangeSetting={onChangeSetting}
          onResetSettings={onResetSettings}
          onClose={onCloseSettingsPanel}
        />
      ) : null}

      {state.error ? <div className="error-banner">{state.error}</div> : null}

      <main className={`document-grid${ui.mindmapVisible ? "" : " is-map-hidden"}`}>
        <aside
          className={`mindmap-pane${ui.mindmapVisible ? "" : " is-hidden"}`}
          aria-hidden={!ui.mindmapVisible}
        >
          <div className="mindmap-pane-head">
            <p className="eyebrow">Mindmap View</p>
            <h2>{summary?.mindmap?.title ?? "思维导图"}</h2>
            <p className="mindmap-pane-copy">
              {selectedNode?.summary || "左侧用于宏观浏览知识结构，点击节点会联动正文对应章节。"}
            </p>
          </div>
          <MindmapCanvas root={summary?.mindmap} selectedNodeId={state.selectedNodeId} onSelectNode={onFocusNode} />
        </aside>

        <WorkspaceReadingPane
          ui={ui}
          library={library}
          summary={summary}
          activeSeries={activeSeries}
          selectedVideo={selectedVideo}
          selectedChapterId={state.selectedChapterId}
          summaryLoading={state.summaryLoading}
          isGeneratingSelectedVideo={isGeneratingSelectedVideo}
        >
          <WorkspaceLibraryPanel
            library={library}
            activeSeries={activeSeries}
            selectedVideo={selectedVideo}
            isGeneratingSelectedVideo={isGeneratingSelectedVideo}
            onSelectSeries={onSelectSeries}
            onSelectVideo={onSelectVideo}
            onGenerateVideo={onGenerateVideo}
          />
        </WorkspaceReadingPane>
      </main>
    </div>
  );
}
