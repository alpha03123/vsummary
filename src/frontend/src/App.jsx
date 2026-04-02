import { useWorkspaceController } from "./features/workspace/model/useWorkspaceController";
import { WorkspacePage } from "./features/workspace/ui/WorkspacePage";

export function App() {
  const controller = useWorkspaceController();

  return (
    <WorkspacePage
      state={controller.state}
      ui={controller.ui}
      library={controller.state.library}
      summary={controller.summary}
      activeSeries={controller.activeSeries}
      selectedVideo={controller.selectedVideo}
      isGeneratingSelectedVideo={controller.isGeneratingSelectedVideo}
      onSelectSeries={controller.onSelectSeries}
      onSelectVideo={controller.onSelectVideo}
      onGenerateVideo={controller.onGenerateVideo}
      onToggleSettingsPanel={controller.onToggleSettingsPanel}
      onCloseSettingsPanel={controller.onCloseSettingsPanel}
      onChangeSetting={controller.onChangeSetting}
      onResetSettings={controller.onResetSettings}
    />
  );
}
