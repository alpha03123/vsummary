import { WorkspaceReadingPane } from "./WorkspaceReadingPane";

export function WorkspaceVideoScopePane({
  page,
  playbackTime = null,
  followOverviewPlayback = false,
  onFollowOverviewPlaybackChange = () => {},
  onProcessLinkedVideo = null,
  onExternalSeek = null,
  panelToolId = "studio",
  onPanelSelectTool = null,
  embeddedInStudioPanel = false,
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
        if (shell.selectedVideo?.id && Number.isFinite(request?.seconds)) {
          chat.openCitationReference?.({
            videoId: shell.selectedVideo.id,
            seconds: request.seconds,
            endSeconds: request.endSeconds ?? request.seconds,
            chapterTitle: request.chapterTitle ?? "",
          });
        } else {
          shell.player.seekToTime(request);
        }
        onExternalSeek?.(request);
      }}
      toolId={panelToolId}
      embeddedInStudioPanel={embeddedInStudioPanel}
      selectedChapterId={shell.state.selectedChapterId}
      summaryLoading={shell.state.summaryLoading}
      mindmapLoading={shell.state.mindmapLoading}
      knowledgeCardsLoading={generation.knowledgeCardsLoading}
      notesLoading={generation.notesLoading}
      savingNote={generation.savingNote}
      aiSummary={shell.aiSummary}
      aiSummaryLoading={generation.aiSummaryLoading}
      generatingAiSummary={generation.generatingAiSummary}
      isGeneratingMindmapSelectedVideo={generation.isGeneratingMindmap}
      isGeneratingSelectedVideo={generation.isGeneratingSummary}
      onSelectTool={(toolId) => onPanelSelectTool?.(toolId)}
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
      onGenerateAiSummary={actions.generateAiSummary}
      onUpdateAiSummary={actions.updateAiSummary}
      onCreateNote={actions.createNote}
      onUpdateNote={actions.updateNote}
      onDeleteNote={actions.deleteNote}
      onLoadTranscriptMarkdown={actions.loadTranscriptMarkdown}
      onLoadSummaryMarkdown={actions.loadSummaryMarkdown}
      onUpdateSummary={actions.updateSummary}
      onUpdateTranscript={actions.updateTranscript}
      onUploadSrt={actions.uploadSrt}
      onRestoreAutomaticTranscript={actions.restoreAutomaticTranscript}
      onOpenCitationReference={chat.openCitationReference}
    />
  );
}
