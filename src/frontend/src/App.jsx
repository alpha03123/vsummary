import { useWorkspaceController } from "./features/workspace/model/useWorkspaceController";
import { WorkspacePage } from "./features/workspace/ui/WorkspacePage";

export function App() {
  const controller = useWorkspaceController();

  return (
    <WorkspacePage
      state={controller.state}
      summary={controller.summary}
      activeSeries={controller.activeSeries}
      currentVideoTitle={controller.currentVideoTitle}
      selectedNode={controller.selectedNode}
      onToggleMindmapVisibility={controller.onToggleMindmapVisibility}
      onToggleChapterNavVisibility={controller.onToggleChapterNavVisibility}
      onFocusChapter={controller.onFocusChapter}
      onFocusNode={controller.onFocusNode}
    />
  );
}
