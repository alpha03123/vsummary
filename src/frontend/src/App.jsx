import { useState, useEffect } from "react";
import { useWorkspaceController } from "./features/workspace/model/useWorkspaceController";
import { WorkspacePage } from "./features/workspace/ui/WorkspacePage";
import { MotionShowcase } from "./tests/MotionShowcase";

export function App() {
  const controller = useWorkspaceController();
  const [isTestMode, setIsTestMode] = useState(window.location.hash === '#test');

  useEffect(() => {
    const onHashChange = () => {
      setIsTestMode(window.location.hash === '#test');
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  if (isTestMode) {
    return <MotionShowcase />;
  }

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
      previewSeekRequest={controller.previewSeekRequest}
      chatMessages={controller.chatMessages}
      chatPending={controller.chatPending}
      fasterWhisperModels={controller.fasterWhisperModels}
      fasterWhisperModelsLoading={controller.fasterWhisperModelsLoading}
      downloadingModelId={controller.downloadingModelId}
      modelDownloadProgress={controller.modelDownloadProgress}
      isGeneratingMindmapSelectedVideo={controller.isGeneratingMindmapSelectedVideo}
      isGeneratingSelectedVideo={controller.isGeneratingSelectedVideo}
      selectedContextType={controller.selectedContextType}
      onSelectSeries={controller.onSelectSeries}
      onEnterLibraryHome={controller.onEnterLibraryHome}
      onSelectVideo={controller.onSelectVideo}
      onSelectSeriesContext={controller.onSelectSeriesContext}
      onSelectTool={controller.onSelectTool}
      onFocusNode={controller.onFocusNode}
      onSubmitChat={controller.onSubmitChat}
      onGenerateVideo={controller.onGenerateVideo}
      onGenerateMindmap={controller.onGenerateMindmap}
      onToggleSettingsPanel={controller.onToggleSettingsPanel}
      onCloseSettingsPanel={controller.onCloseSettingsPanel}
      onChangeSetting={controller.onChangeSetting}
      onDownloadFasterWhisperModel={controller.onDownloadFasterWhisperModel}
      onCancelFasterWhisperModelDownload={controller.onCancelFasterWhisperModelDownload}
      onResetSettings={controller.onResetSettings}
    />
  );
}
