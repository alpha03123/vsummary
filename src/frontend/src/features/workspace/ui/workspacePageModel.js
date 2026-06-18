import { isGenerationSnapshotActive } from "../model/workspaceState";

export function buildWorkspacePageModel(controller) {
  const seriesQueue = controller.seriesGenerationQueue;
  const seriesQueueActive =
    controller.selectedContextType === "series" &&
    seriesQueue?.seriesId === controller.state.selectedSeriesId &&
    (seriesQueue.status === "running" || seriesQueue.status === "cancelling");
  const seriesQueueProgress =
    seriesQueueActive && !seriesQueue.downloadVideoId && typeof seriesQueue.total === "number" && seriesQueue.total > 0
      ? (seriesQueue.completed / seriesQueue.total) * 100
      : null;
  const seriesQueueSnapshot = seriesQueueActive
    ? {
        status: seriesQueue.status,
        stage: "batch",
        progress: seriesQueueProgress,
        detail: seriesQueue.detail ?? `已完成 ${seriesQueue.completed}/${seriesQueue.total}`,
        error: null,
      }
    : null;
  const generationSnapshot = seriesQueueSnapshot ?? controller.currentGenerationTask?.snapshot ?? null;
  const showGenerationOverlay = isGenerationSnapshotActive(generationSnapshot);
  return {
    shell: {
      state: controller.state,
      ui: controller.ui,
      library: controller.state.library,
      activeSeries: controller.activeSeries,
      selectedVideo: controller.selectedVideo,
      selectedContextType: controller.selectedContextType,
      selectedNode: controller.selectedNode,
      previewUrl: controller.previewUrl,
      playerSeekRequest: controller.playerSeekRequest,
      player: {
        seekToTime: controller.onSeekToTime,
      },
      summary: controller.summary,
      mindmap: controller.mindmap,
      knowledgeCards: controller.knowledgeCards,
      knowledgeCardsGenerating: controller.knowledgeCardsGenerating,
      knowledgeCardsFeedback: controller.knowledgeCardsFeedback,
      notes: controller.notes,
      tools: controller.tools,
    },
    chat: {
      messages: controller.chatMessages,
      sessions: controller.chatSessions,
      activeSessionId: controller.activeChatSessionId,
      pending: controller.chatPending,
      contextUsage: controller.contextUsage,
      contextUsageLoading: controller.contextUsageLoading,
      startNewChat: controller.onStartNewChat,
      selectChatSession: controller.onSelectChatSession,
      openSeekReference: controller.onOpenSeekReference,
      drawerOpen: controller.chatDrawerOpen,
      toggleDrawer: controller.onToggleChatDrawer,
      openDrawer: controller.onOpenChatDrawer,
      closeDrawer: controller.onCloseChatDrawer,
      clearChat: controller.onClearChat,
      submit: controller.onSubmitChat,
    },
    generation: {
      isGeneratingSummary: controller.isGeneratingSelectedVideo,
      isGeneratingSeries: controller.isGeneratingSelectedSeries,
      seriesGenerationQueue: controller.seriesGenerationQueue,
      isGeneratingMindmap: controller.isGeneratingMindmapSelectedVideo,
      knowledgeCardsLoading: controller.knowledgeCardsLoading,
      notesLoading: controller.notesLoading,
      savingNote: controller.savingNote,
      fasterWhisperModels: controller.fasterWhisperModels,
      fasterWhisperModelsLoading: controller.fasterWhisperModelsLoading,
      ragModels: controller.ragModels,
      ragModelsLoading: controller.ragModelsLoading,
      downloadingRagModelKey: controller.downloadingRagModelKey,
      downloadingModelId: controller.downloadingModelId,
      modelDownloadsById: controller.modelDownloadsById,
      modelDownloadStatus: controller.modelDownloadStatus,
      modelDownloadProgress: controller.modelDownloadProgress,
      modelDownloadErrorModelId: controller.modelDownloadErrorModelId,
      modelDownloadError: controller.modelDownloadError,
      progress: generationSnapshot?.progress ?? null,
      snapshot: generationSnapshot,
      showOverlay: showGenerationOverlay,
      videoDownloadProgress: controller.state.videoDownloadProgress ?? null,
      downloadingVideoKey: controller.state.downloadingVideoKey,
    },
    actions: {
      selectSeries: controller.onSelectSeries,
      enterLibraryHome: controller.onEnterLibraryHome,
      selectVideo: controller.onSelectVideo,
      selectSeriesContext: controller.onSelectSeriesContext,
      selectTool: controller.onSelectTool,
      focusNode: controller.onFocusNode,
      generateVideo: controller.onGenerateVideo,
      generateSeries: controller.onGenerateSeries,
      cancelGeneration: controller.onCancelGeneration,
      generateMindmap: controller.onGenerateMindmap,
      generateKnowledgeCards: controller.onGenerateKnowledgeCards,
      clearKnowledgeCardsFeedback: controller.onClearKnowledgeCardsFeedback,
      createNote: controller.onCreateNote,
      updateNote: controller.onUpdateNote,
      deleteNote: controller.onDeleteNote,
      toggleSettingsPanel: controller.onToggleSettingsPanel,
      openSettingsPanel: controller.onOpenSettingsPanel,
      closeSettingsPanel: controller.onCloseSettingsPanel,
      changeSetting: controller.onChangeSetting,
      saveProviderSettings: controller.onSaveProviderSettings,
      saveApiKey: controller.onSaveApiKey,
      revealOpenaiApiKey: controller.onRevealOpenaiApiKey,
      testProviderConnection: controller.onTestProviderConnection,
      downloadFasterWhisperModel: controller.onDownloadFasterWhisperModel,
      downloadRagModel: controller.onDownloadRagModel,
      resetSettings: controller.onResetSettings,
      clearError: controller.onClearError,
      resolveLinkedSeries: controller.onResolveLinkedSeries,
      resolvePlaygroundVideo: controller.onResolvePlaygroundVideo,
      resolveSeriesVideo: controller.onResolveSeriesVideo,
      initBilibiliCookie: controller.onInitBilibiliCookie,
      loadChaoxingStatus: controller.onLoadChaoxingStatus,
      initChaoxing: controller.onInitChaoxing,
      cancelChaoxingInit: controller.onCancelChaoxingInit,
      cancelChaoxingImport: controller.onCancelChaoxingImport,
      loadChaoxingCourses: controller.onLoadChaoxingCourses,
      importChaoxingCourse: controller.onImportChaoxingCourse,
      importLocalSeries: controller.onImportLocalSeries,
      importLocalPlaygroundVideos: controller.onImportLocalPlaygroundVideos,
      importSeriesVideos: controller.onImportSeriesVideos,
      deleteSeries: controller.onDeleteSeries,
      deleteCurrentVideo: controller.onDeleteCurrentVideo,
      downloadVideo: controller.onDownloadVideo,
    },
  };
}
