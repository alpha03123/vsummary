import { WorkspaceLibraryPanel } from "./WorkspaceLibraryPanel";
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
  isGeneratingSelectedVideo,
  onSelectSeries,
  onSelectVideo,
  onGenerateVideo,
  onToggleSettingsPanel,
  onCloseSettingsPanel,
  onChangeSetting,
  onResetSettings,
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
      <WorkspaceToolbar settingsOpen={state.settingsPanelOpen} onToggleSettingsPanel={onToggleSettingsPanel} />

      {state.settingsPanelOpen ? (
        <WorkspaceSettingsPanel
          ui={ui}
          onChangeSetting={onChangeSetting}
          onResetSettings={onResetSettings}
          onClose={onCloseSettingsPanel}
        />
      ) : null}

      {state.error ? <div className="error-banner">{state.error}</div> : null}

      <main className="document-grid">
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
