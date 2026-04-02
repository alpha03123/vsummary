import { useWorkspaceController } from "./features/workspace/model/useWorkspaceController";
import { WorkspacePage } from "./features/workspace/ui/WorkspacePage";

export function App() {
  const controller = useWorkspaceController();

  return (
    <WorkspacePage
      state={controller.state}
      ui={controller.ui}
      library={controller.state.library}
      tools={controller.tools}
      summary={controller.summary}
      mindmap={controller.mindmap}
      activeSeries={controller.activeSeries}
      selectedVideo={controller.selectedVideo}
      selectedNode={controller.selectedNode}
      previewUrl={controller.previewUrl}
      isGeneratingMindmapSelectedVideo={controller.isGeneratingMindmapSelectedVideo}
      isGeneratingSelectedVideo={controller.isGeneratingSelectedVideo}
      onSelectSeries={controller.onSelectSeries}
      onEnterLibraryHome={controller.onEnterLibraryHome}
      onSelectVideo={controller.onSelectVideo}
      onSelectTool={controller.onSelectTool}
      onFocusNode={controller.onFocusNode}
      onGenerateVideo={controller.onGenerateVideo}
      onGenerateMindmap={controller.onGenerateMindmap}
      onToggleSettingsPanel={controller.onToggleSettingsPanel}
      onCloseSettingsPanel={controller.onCloseSettingsPanel}
      onChangeSetting={controller.onChangeSetting}
      onResetSettings={controller.onResetSettings}
    />
  );
}
