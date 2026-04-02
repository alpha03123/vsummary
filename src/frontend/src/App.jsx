import { useWorkspaceController } from "./features/workspace/model/useWorkspaceController";
import { WorkspacePage } from "./features/workspace/ui/WorkspacePage";

export function App() {
  const controller = useWorkspaceController();

  return (
    <WorkspacePage
      state={controller.state}
      summary={controller.summary}
      activeSeries={controller.activeSeries}
      selectedNode={controller.selectedNode}
      onToggleMindmapVisibility={controller.onToggleMindmapVisibility}
      onFocusNode={controller.onFocusNode}
    />
  );
}
