import { useWorkspaceController } from "./features/workspace/model/useWorkspaceController";
import { WorkspacePage } from "./features/workspace/ui/WorkspacePage";

export function App() {
  const controller = useWorkspaceController();

  return (
    <WorkspacePage
      state={controller.state}
      ui={controller.ui}
      summary={controller.summary}
      activeSeries={controller.activeSeries}
      selectedNode={controller.selectedNode}
      onToggleMindmapVisibility={controller.onToggleMindmapVisibility}
      onToggleSettingsPanel={controller.onToggleSettingsPanel}
      onCloseSettingsPanel={controller.onCloseSettingsPanel}
      onChangeSetting={controller.onChangeSetting}
      onResetSettings={controller.onResetSettings}
      onFocusNode={controller.onFocusNode}
    />
  );
}
