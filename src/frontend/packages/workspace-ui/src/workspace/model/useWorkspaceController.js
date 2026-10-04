import {useWorkspaceRuntime} from "../../runtime/WorkspaceProvider";
import { useEffect, useMemo, useReducer, useRef } from "react";

import { findChapterForNode, findNodeById } from "./workspaceTree";
import {
  createInitialWorkspaceState,
  findSeriesById,
  findVideoById,
  getChatSessionListForScope,
  getGenerationTaskForSelection,
  isGenerationSnapshotActive,
} from "./workspaceState";
import { isPlaygroundSeries, PLAYGROUND_SERIES_ID } from "./workspaceControllerConstants";
import { buildVideoKey } from "./workspaceControllerUtils";
import { workspaceReducer } from "./workspaceReducer";
import { createWorkspaceChatActions } from "./workspaceChatActions";

export function useWorkspaceController() {
  const {host,api,useDataEffects,createContentActions}=useWorkspaceRuntime();
  const [state, dispatch] = useReducer(workspaceReducer, {storage:host.storage, ui:host.initialUi}, createInitialWorkspaceState);
  const {getVideoPreviewUrl}=api;
  const chatAbortControllerRef = useRef(null);

  useDataEffects(state, dispatch);

  const activeSeries = findSeriesById(state.library, state.selectedSeriesId)
    ?? (state.selectedContextType === "playground" && state.selectedSeriesId === PLAYGROUND_SERIES_ID
      ? { id: PLAYGROUND_SERIES_ID, title: "Playground", videos: [], kind: "playground" }
      : null);
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
    if (!activeSeries || isPlaygroundSeries(activeSeries)) return false;
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

  const contentActions = createContentActions({
    state,
    dispatch,
    selectedVideo,
  });
  const chatActions = createWorkspaceChatActions({
    api,
    state,
    dispatch,
    contentActions,
    chatAbortControllerRef,
  });
  const hostActions=host.createActions?.({state,dispatch,contentActions,coreApi:api})??{};
  const settingsActions={
    onToggleSettingsPanel:()=>dispatch({type:'settings_panel_toggled'}),
    onOpenSettingsPanel:initialTab=>dispatch({type:'settings_panel_opened',initialTab}),
    onCloseSettingsPanel:()=>dispatch({type:'settings_panel_closed'}),
    onOpenUsagePage:()=>dispatch({type:'usage_page_opened'}),
    onCloseUsagePage:()=>dispatch({type:'usage_page_closed'}),
    onChangeSetting:(key,value)=>dispatch({type:'workspace_setting_edited',key,value}),
  };

  function onSelectSeries(seriesId) {
    const series = findSeriesById(state.library, seriesId);
    if (seriesId === PLAYGROUND_SERIES_ID || isPlaygroundSeries(series)) {
      dispatch({ type: "playground_selected", seriesId });
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
    if (isPlaygroundSeries(activeSeries)) {
      dispatch({ type: "playground_selected", seriesId: activeSeries.id });
      return;
    }
    dispatch({ type: "series_context_selected" });
  }

  function onFocusNode(node) {
    const chapterId = findChapterForNode(state.summary?.chapters ?? [], node)?.id ?? null;
    dispatch({
      type: "node_selected",
      nodeId: node.id,
      chapterId,
    });

    // 复用 citation 的定位通道：让已经打开的「AI 概况」卡片滚动到对应章节与转写段落。
    // 仅在视频作用域下发 —— 系列导图的节点时间分属各个视频，用当前视频的概况去匹配会跳错章节。
    if (state.selectedContextType === "video") {
      dispatch({
        type: "citation_focus_requested",
        focus: {
          seconds: node.start_seconds,
          endSeconds: node.end_seconds,
          chapterId,
          requestId: `${Date.now()}-${node.id}`,
        },
      });
    }

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

  function onFocusOverviewAtTime(seconds) {
    if (!Number.isFinite(seconds)) {
      return;
    }
    dispatch({
      type: "overview_focus_requested",
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
    dispatch,
    processingMode: state.processingMode,
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
    knowledgeCardsGenerationProgress: state.knowledgeCardsGenerationProgress,
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
    aiSummary: state.aiSummary,
    aiSummaryLoading: state.aiSummaryLoading,
    generatingAiSummary: state.generatingAiSummary,
    savingNote: state.savingNote,
    selectedContextType: state.selectedContextType,
    onRefreshLibrary:library=>dispatch({type:"workspace_loaded",library}),
    onSelectSeries,
    onEnterLibraryHome,
    onSelectVideo,
    onSelectSeriesContext,
    onFocusNode,
    onSubmitChat: chatActions.onSubmitChat,
    onCancelChat: chatActions.onCancelChat,
    onStartNewChat: chatActions.onStartNewChat,
    onSelectChatSession: chatActions.onSelectChatSession,
    onOpenSeekReference: chatActions.onOpenSeekReference,
    onOpenCitationReference: chatActions.onOpenCitationReference,
    onClearChat: chatActions.onClearChat,
    onGenerateVideo: contentActions.onGenerateVideo,
    onChangeProcessingMode: contentActions.onChangeProcessingMode,
    onProcessLinkedVideo: contentActions.onProcessLinkedVideo,
    onUploadSrt: contentActions.onUploadSrt,
    onRestoreAutomaticTranscript: contentActions.onRestoreAutomaticTranscript,
    onGenerateMindmap: contentActions.onGenerateMindmap,
    onGenerateSeriesMindmap: contentActions.onGenerateSeriesMindmap,
    onGenerateSeries: contentActions.onGenerateSeries,
    onCancelGeneration: contentActions.onCancelGeneration,
    onGenerateKnowledgeCards: contentActions.onGenerateKnowledgeCards,
    onClearKnowledgeCardsFeedback: contentActions.onClearKnowledgeCardsFeedback,
    onCreateNote: contentActions.onCreateNote,
    onGenerateAiSummary: contentActions.onGenerateAiSummary,
    onUpdateAiSummary: contentActions.onUpdateAiSummary,
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










    onChangeSetting: settingsActions.onChangeSetting,













    onClearError,
    onSeekToTime,
    onFocusOverviewAtTime,
    onToggleChatDrawer,
    onOpenChatDrawer,
    onCloseChatDrawer,
    onResolveLinkedSeries: contentActions.onResolveLinkedSeries,
    onResolvePlaygroundVideo: contentActions.onResolvePlaygroundVideo,
    onResolveSeriesVideo: contentActions.onResolveSeriesVideo,
    onResolveBilibiliInboxVideo: contentActions.onResolveBilibiliInboxVideo,
    onDeleteSeries: contentActions.onDeleteSeries,
    onDeleteSeriesByIds: contentActions.onDeleteSeriesByIds,
    onRenameSeries: contentActions.onRenameSeries,
    onDeleteCurrentVideo: contentActions.onDeleteCurrentVideo,
    onRenameCurrentVideo: contentActions.onRenameCurrentVideo,
    onDeleteVideos: contentActions.onDeleteVideos,
    onDownloadVideo: contentActions.onDownloadVideo,
    ...hostActions,
  };
}
