import { useEffect, useMemo, useReducer, useRef } from "react";

import { getVideoPreviewUrl } from "./workspaceApi";
import { findChapterForNode, findNodeById } from "./workspaceTree";
import {
  createInitialWorkspaceState,
  findSeriesById,
  findVideoById,
  getChatSessionListForScope,
  getGenerationTaskForSelection,
  isGenerationSnapshotActive,
} from "./workspaceState";
import { PLAYGROUND_SERIES_ID } from "./workspaceControllerConstants";
import { buildVideoKey } from "./workspaceControllerUtils";
import { workspaceReducer } from "./workspaceReducer";
import { useWorkspaceDataEffects } from "./useWorkspaceDataEffects";
import { createWorkspaceContentActions } from "./workspaceContentActions";
import { createWorkspaceChatActions } from "./workspaceChatActions";
import { createWorkspaceSettingsActions } from "./workspaceSettingsActions";

export function useWorkspaceController() {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, createInitialWorkspaceState);
  const chatAbortControllerRef = useRef(null);

  useWorkspaceDataEffects(state, dispatch);

  useEffect(() => {
    if (!state.error) {
      return undefined;
    }
    const timeoutId = window.setTimeout(() => {
      dispatch({ type: "error_cleared" });
    }, 6000);
    return () => window.clearTimeout(timeoutId);
  }, [state.error]);

  const activeSeries = findSeriesById(state.library, state.selectedSeriesId);
  const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
  const summary = state.summary;
  const mindmap = state.mindmap;
  const seriesMindmap = state.seriesMindmap;
  const seriesMindmapLoading = state.seriesMindmapLoading;
  const seriesOverviewSummariesByVideoId = state.seriesOverviewSummariesByVideoId;
  const seriesOverviewLoading = state.seriesOverviewLoading;
  const generatingSeriesMindmap = state.generatingSeriesMindmap;
  const mindmapGenerationProgress = state.mindmapGenerationProgress;

  const seriesMindmapAvailable = useMemo(() => {
    if (!activeSeries || activeSeries.id === PLAYGROUND_SERIES_ID) return false;
    const videos = activeSeries.videos ?? [];
    if (videos.length === 0) return false;
    return videos.some(v => v.processed === true);
  }, [activeSeries]);

  const tools = state.tools;
  const currentGenerationTask = getGenerationTaskForSelection(state);
  const selectedNode = useMemo(
    () => findNodeById(mindmap, state.selectedNodeId),
    [mindmap, state.selectedNodeId],
  );
  const isGeneratingSelectedVideo =
    currentGenerationTask?.mode === "video" &&
    isGenerationSnapshotActive(currentGenerationTask.snapshot);
  const isGeneratingSelectedSeries =
    state.seriesGenerationQueue?.seriesId === state.selectedSeriesId &&
    (state.seriesGenerationQueue.status === "running" || state.seriesGenerationQueue.status === "cancelling");
  const isGeneratingMindmapSelectedVideo =
    state.generatingMindmapKey != null &&
    state.generatingMindmapKey === buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
  const selectedVideoIsLinked = selectedVideo?.isLinked === true || selectedVideo?.status === "linked";
  const previewUrl = state.selectedSeriesId && state.selectedVideoId && !selectedVideoIsLinked
    ? getVideoPreviewUrl(state.selectedSeriesId, state.selectedVideoId)
    : null;

  const contentActions = createWorkspaceContentActions({
    state,
    dispatch,
    selectedVideo,
  });
  const chatActions = createWorkspaceChatActions({
    state,
    dispatch,
    contentActions,
    chatAbortControllerRef,
  });
  const settingsActions = createWorkspaceSettingsActions({
    state,
    dispatch,
  });

  function onSelectSeries(seriesId) {
    if (seriesId === PLAYGROUND_SERIES_ID) {
      dispatch({ type: "playground_selected" });
      return;
    }
    dispatch({ type: "series_selected", seriesId });
  }

  function onEnterLibraryHome() {
    dispatch({ type: "library_home_selected" });
  }

  function onSelectVideo(seriesId, videoId) {
    dispatch({ type: "video_selected", seriesId, videoId });
  }

  function onSelectSeriesContext() {
    if (state.selectedSeriesId === PLAYGROUND_SERIES_ID) {
      dispatch({ type: "playground_selected" });
      return;
    }
    dispatch({ type: "series_context_selected" });
  }

  function onSelectTool(toolId) {
    dispatch({ type: "tool_selected", toolId });
  }

  function onFocusNode(node) {
    const chapterId = findChapterForNode(state.summary?.chapters ?? [], node)?.id ?? null;
    dispatch({
      type: "node_selected",
      nodeId: node.id,
      chapterId,
    });

    onSeekToTime({
      seconds: node.start_seconds,
      endSeconds: node.end_seconds,
      chapterTitle: node.title,
    });

  }

  function onClearError() {
    dispatch({ type: "error_cleared" });
  }

  function onSeekToTime({ seconds, endSeconds = null, chapterTitle = "" } = {}) {
    if (!Number.isFinite(seconds)) {
      return;
    }
    dispatch({
      type: "player_seek_requested",
      seconds,
      endSeconds,
      chapterTitle,
      requestId: `${Date.now()}-${seconds}`,
    });
  }

  function onOpenOverviewAtTime(seconds) {
    if (!Number.isFinite(seconds)) {
      return;
    }
    dispatch({
      type: "overview_opened_at_time",
      seconds,
      requestId: `${Date.now()}-${seconds}`,
    });
  }

  function onToggleChatDrawer() {
    dispatch({ type: "chat_drawer_toggled" });
  }

  function onOpenChatDrawer() {
    dispatch({ type: "chat_drawer_opened" });
  }

  function onCloseChatDrawer() {
    dispatch({ type: "chat_drawer_closed" });
  }

  return {
    state,
    currentGenerationTask,
    seriesGenerationQueue: state.seriesGenerationQueue,
    ui: state.ui,
    fasterWhisperModels: state.fasterWhisperModels,
    fasterWhisperModelsLoading: state.fasterWhisperModelsLoading,
    ragModels: state.ragModels,
    ragModelsLoading: state.ragModelsLoading,
    downloadingRagModelKey: state.downloadingRagModelKey,
    downloadingModelId: state.downloadingModelId,
    modelDownloadsById: state.modelDownloadsById,
    modelDownloadStatus: state.modelDownloadStatus,
    modelDownloadProgress: state.modelDownloadProgress,
    modelDownloadErrorModelId: state.modelDownloadErrorModelId,
    modelDownloadError: state.modelDownloadError,
    tools,
    summary,
    mindmap,
    seriesMindmap,
    seriesMindmapAvailable,
    seriesMindmapLoading,
    seriesOverviewSummariesByVideoId,
    seriesOverviewLoading,
    generatingSeriesMindmap,
    mindmapGenerationProgress,
    knowledgeCards: state.knowledgeCards,
    knowledgeCardsGenerating: state.knowledgeCardsGenerating,
    knowledgeCardsFeedback: state.knowledgeCardsFeedback,
    notes: state.notes,
    activeSeries,
    selectedVideo,
    selectedNode,
    previewUrl,
    playerSeekRequest: state.playerSeekRequest,
    citationFocus: state.citationFocus,
    chatMessages: state.chatMessages,
    chatSessions: getChatSessionListForScope(state.chatSessionListsByScope, state.chatBaseScopeKey),
    activeChatSessionId: state.chatScopeKey,
    chatPending: state.chatPending,
    chatRecoveryLoading: state.chatRecoveryLoading,
    chatDrawerOpen: state.chatDrawerOpen,
    contextUsage: state.contextUsage,
    contextUsageLoading: state.contextUsageLoading,
    isGeneratingMindmapSelectedVideo,
    isGeneratingSelectedVideo,
    isGeneratingSelectedSeries,
    knowledgeCardsLoading: state.knowledgeCardsLoading,
    notesLoading: state.notesLoading,
    savingNote: state.savingNote,
    selectedContextType: state.selectedContextType,
    onSelectSeries,
    onEnterLibraryHome,
    onSelectVideo,
    onSelectSeriesContext,
    onSelectTool,
    onFocusNode,
    onSubmitChat: chatActions.onSubmitChat,
    onCancelChat: chatActions.onCancelChat,
    onStartNewChat: chatActions.onStartNewChat,
    onSelectChatSession: chatActions.onSelectChatSession,
    onOpenSeekReference: chatActions.onOpenSeekReference,
    onOpenCitationReference: chatActions.onOpenCitationReference,
    onClearChat: chatActions.onClearChat,
    onGenerateVideo: contentActions.onGenerateVideo,
    onUploadSrt: contentActions.onUploadSrt,
    onRestoreAutomaticTranscript: contentActions.onRestoreAutomaticTranscript,
    onGenerateMindmap: contentActions.onGenerateMindmap,
    onGenerateSeriesMindmap: contentActions.onGenerateSeriesMindmap,
    onGenerateSeries: contentActions.onGenerateSeries,
    onCancelGeneration: contentActions.onCancelGeneration,
    onGenerateKnowledgeCards: contentActions.onGenerateKnowledgeCards,
    onClearKnowledgeCardsFeedback: contentActions.onClearKnowledgeCardsFeedback,
    onCreateNote: contentActions.onCreateNote,
    onUpdateNote: contentActions.onUpdateNote,
    onDeleteNote: contentActions.onDeleteNote,
    onLoadTranscriptMarkdown: contentActions.onLoadTranscriptMarkdown,
    onLoadSummaryMarkdown: contentActions.onLoadSummaryMarkdown,
    onUpdateSummary: contentActions.onUpdateSummary,
    onUpdateTranscript: contentActions.onUpdateTranscript,
    onToggleSettingsPanel: settingsActions.onToggleSettingsPanel,
    onOpenSettingsPanel: settingsActions.onOpenSettingsPanel,
    onCloseSettingsPanel: settingsActions.onCloseSettingsPanel,
    onOpenUsagePage: settingsActions.onOpenUsagePage,
    onCloseUsagePage: settingsActions.onCloseUsagePage,
    onCheckApplicationUpdate: settingsActions.onCheckApplicationUpdate,
    onScheduleApplicationUpdate: settingsActions.onScheduleApplicationUpdate,
    onChangeProviderUsageRange: settingsActions.onChangeProviderUsageRange,
    onChangeSetting: settingsActions.onChangeSetting,
    onSaveProviderSettings: settingsActions.onSaveProviderSettings,
    onSelectProviderModel: settingsActions.onSelectProviderModel,
    onDiscoverProviderModels: settingsActions.onDiscoverProviderModels,
    onSaveApiKey: settingsActions.onSaveApiKey,
    onSaveAsrSettings: settingsActions.onSaveAsrSettings,
    onRevealAsrApiKey: settingsActions.onRevealAsrApiKey,
    onTestAsrConnection: settingsActions.onTestAsrConnection,
    onRevealOpenaiApiKey: settingsActions.onRevealOpenaiApiKey,
    onTestProviderConnection: settingsActions.onTestProviderConnection,
    onDownloadFasterWhisperModel: settingsActions.onDownloadFasterWhisperModel,
    onCancelFasterWhisperModelDownload: settingsActions.onCancelFasterWhisperModelDownload,
    onDownloadRagModel: settingsActions.onDownloadRagModel,
    onResetSettings: settingsActions.onResetSettings,
    onClearError,
    onSeekToTime,
    onOpenOverviewAtTime,
    onToggleChatDrawer,
    onOpenChatDrawer,
    onCloseChatDrawer,
    onResolveLinkedSeries: contentActions.onResolveLinkedSeries,
    onSelectLocalMedia: contentActions.onSelectLocalMedia,
    onResolvePlaygroundVideo: contentActions.onResolvePlaygroundVideo,
    onResolveSeriesVideo: contentActions.onResolveSeriesVideo,
    onInitBilibiliCookie: contentActions.onInitBilibiliCookie,
    onLoadChaoxingStatus: contentActions.onLoadChaoxingStatus,
    onInitChaoxing: contentActions.onInitChaoxing,
    onCancelChaoxingInit: contentActions.onCancelChaoxingInit,
    onCancelChaoxingImport: contentActions.onCancelChaoxingImport,
    onLoadChaoxingCourses: contentActions.onLoadChaoxingCourses,
    onImportChaoxingCourse: contentActions.onImportChaoxingCourse,
    onImportLocalSeries: contentActions.onImportLocalSeries,
    onImportLocalPlaygroundVideos: contentActions.onImportLocalPlaygroundVideos,
    onImportSeriesVideos: contentActions.onImportSeriesVideos,
    onDeleteSeries: contentActions.onDeleteSeries,
    onRenameSeries: contentActions.onRenameSeries,
    onDeleteCurrentVideo: contentActions.onDeleteCurrentVideo,
    onRenameCurrentVideo: contentActions.onRenameCurrentVideo,
    onDeleteVideos: contentActions.onDeleteVideos,
    onDownloadVideo: contentActions.onDownloadVideo,
  };
}
