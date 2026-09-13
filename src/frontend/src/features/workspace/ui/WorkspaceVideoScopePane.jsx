import { WorkspaceReadingPane } from "./WorkspaceReadingPane";

export function WorkspaceVideoScopePane({
  page,
  playbackTime = null,
  followOverviewPlayback = false,
  onFollowOverviewPlaybackChange = () => {},
  onRequestAiNote = () => {},
  onProcessLinkedVideo = null,
  onOpenChat = null,
  onExternalSeek = null,
}) {
  const { shell, generation, actions, chat } = page;

  return (
    <WorkspaceReadingPane
      ui={shell.ui}
      tools={shell.tools}
      library={shell.library}
      chat={chat}
      summary={shell.summary}
      playbackTime={playbackTime}
      followOverviewPlayback={followOverviewPlayback}
      onFollowOverviewPlaybackChange={onFollowOverviewPlaybackChange}
      mindmap={shell.mindmap}
      seriesMindmap={shell.seriesMindmap}
      seriesMindmapAvailable={shell.seriesMindmapAvailable}
      seriesMindmapLoading={generation.seriesMindmapLoading}
      seriesOverviewSummariesByVideoId={shell.seriesOverviewSummariesByVideoId}
      seriesOverviewLoading={generation.seriesOverviewLoading}
      generatingSeriesMindmap={generation.generatingSeriesMindmap}
      mindmapGenerationProgress={generation.mindmapGenerationProgress}
      knowledgeCards={shell.knowledgeCards}
      knowledgeCardsGenerating={shell.knowledgeCardsGenerating}
      knowledgeCardsFeedback={shell.knowledgeCardsFeedback}
      notes={shell.notes}
      activeSeries={shell.activeSeries}
      selectedVideo={shell.selectedVideo}
      selectedContextType={shell.selectedContextType}
      selectedNode={shell.selectedNode}
      previewUrl={shell.previewUrl}
      playerSeekRequest={shell.playerSeekRequest}
      citationFocus={shell.citationFocus}
      onSeek={(request) => {
        shell.player.seekToTime(request);
        onExternalSeek?.(request);
      }}
      selectedToolId={shell.state.selectedToolId}
      selectedChapterId={shell.state.selectedChapterId}
      summaryLoading={shell.state.summaryLoading}
      mindmapLoading={shell.state.mindmapLoading}
      knowledgeCardsLoading={generation.knowledgeCardsLoading}
      notesLoading={generation.notesLoading}
      savingNote={generation.savingNote}
      isGeneratingMindmapSelectedVideo={generation.isGeneratingMindmap}
      isGeneratingSelectedVideo={generation.isGeneratingSummary}
      onSelectTool={(toolId) => {
        if (toolId === "chat-management" && onOpenChat) {
          onOpenChat();
          return;
        }
        if (
          toolId === "overview" &&
          onProcessLinkedVideo &&
          shell.tools?.overview?.generated !== true &&
          !generation.isGeneratingSummary
        ) {
          void onProcessLinkedVideo();
        }
        actions.selectTool(toolId);
      }}
      onSelectVideo={actions.selectVideo}
      onFocusNode={(node) => {
        actions.focusNode(node);
        if (Number.isFinite(node?.start_seconds)) {
          onExternalSeek?.({
            seconds: node.start_seconds,
            endSeconds: node.end_seconds,
            chapterTitle: node.title,
          });
        }
      }}
      onGenerateMindmap={actions.generateMindmap}
      onGenerateSeriesMindmap={actions.generateSeriesMindmap}
      onGenerateKnowledgeCards={actions.generateKnowledgeCards}
      onClearKnowledgeCardsFeedback={actions.clearKnowledgeCardsFeedback}
      onRequestAiNote={onRequestAiNote}
      onCreateNote={actions.createNote}
      onUpdateNote={actions.updateNote}
      onDeleteNote={actions.deleteNote}
      onLoadTranscriptMarkdown={actions.loadTranscriptMarkdown}
      onLoadSummaryMarkdown={actions.loadSummaryMarkdown}
      onUpdateSummary={actions.updateSummary}
      onUpdateTranscript={actions.updateTranscript}
      onUploadSrt={actions.uploadSrt}
      onRestoreAutomaticTranscript={actions.restoreAutomaticTranscript}
    />
  );
}
