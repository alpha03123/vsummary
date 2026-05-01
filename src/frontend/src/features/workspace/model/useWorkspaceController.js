import { useMemo, useReducer } from "react";

import { getVideoPreviewUrl } from "./workspaceApi";
import { findChapterForNode, findNodeById } from "./workspaceTree";
import {
  createInitialWorkspaceState,
  findSeriesById,
  findVideoById,
  getChatSessionListForScope,
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

  useWorkspaceDataEffects(state, dispatch);

  const activeSeries = findSeriesById(state.library, state.selectedSeriesId);
  const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
  const summary = state.summary;
  const mindmap = state.mindmap;
  const tools = state.tools;
  const selectedNode = useMemo(
    () => findNodeById(mindmap, state.selectedNodeId),
    [mindmap, state.selectedNodeId],
  );
  const isGeneratingSelectedVideo =
    state.generatingVideoKey != null &&
    state.generatingVideoKey === buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
  const isGeneratingSelectedSeries = state.generatingSeriesId != null && state.generatingSeriesId === state.selectedSeriesId;
  const isGeneratingMindmapSelectedVideo =
    state.generatingMindmapKey != null &&
    state.generatingMindmapKey === buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
  const selectedVideoIsLinked = selectedVideo?.isLinked === true || selectedVideo?.status === "linked";
  const previewUrl = state.selectedSeriesId && state.selectedVideoId
    ? (selectedVideoIsLinked ? null : getVideoPreviewUrl(state.selectedSeriesId, state.selectedVideoId))
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

    requestAnimationFrame(() => {
      if (chapterId) {
        document.getElementById(chapterId)?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  function onOpenCard(card) {
    const primarySource = Array.isArray(card?.sourceRefs) ? card.sourceRefs[0] : null;
    const startSeconds = typeof card?.startSeconds === "number"
      ? card.startSeconds
      : primarySource?.startSeconds;
    const endSeconds = typeof card?.endSeconds === "number"
      ? card.endSeconds
      : primarySource?.endSeconds;
    if (typeof startSeconds !== "number") {
      return;
    }
    dispatch({ type: "tool_selected", toolId: "preview" });
    dispatch({
      type: "preview_seek_requested",
      seconds: startSeconds,
      endSeconds: typeof endSeconds === "number" ? endSeconds : null,
      chapterTitle: typeof card.title === "string" ? card.title : "",
      requestId: `${Date.now()}-${card.id}`,
    });
  }

  function onClearError() {
    dispatch({ type: "error_cleared" });
  }

  return {
    state,
    ui: state.ui,
    fasterWhisperModels: state.fasterWhisperModels,
    fasterWhisperModelsLoading: state.fasterWhisperModelsLoading,
    downloadingModelId: state.downloadingModelId,
    modelDownloadProgress: state.modelDownloadProgress,
    tools,
    summary,
    mindmap,
    knowledgeCards: state.knowledgeCards,
    knowledgeCardsGenerating: state.knowledgeCardsGenerating,
    knowledgeCardsFeedback: state.knowledgeCardsFeedback,
    notes: state.notes,
    activeSeries,
    selectedVideo,
    selectedNode,
    previewUrl,
    previewSeekRequest: state.previewSeekRequest,
    chatMessages: state.chatMessages,
    chatSessions: getChatSessionListForScope(state.chatSessionListsByScope, state.chatBaseScopeKey),
    activeChatSessionId: state.chatScopeKey,
    chatPending: state.chatPending,
    chatRecoveryLoading: state.chatRecoveryLoading,
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
    onOpenCard,
    onSubmitChat: chatActions.onSubmitChat,
    onStartNewChat: chatActions.onStartNewChat,
    onSelectChatSession: chatActions.onSelectChatSession,
    onOpenSeekReference: chatActions.onOpenSeekReference,
    onClearChat: chatActions.onClearChat,
    onGenerateVideo: contentActions.onGenerateVideo,
    onGenerateMindmap: contentActions.onGenerateMindmap,
    onGenerateSeries: contentActions.onGenerateSeries,
    onCancelGeneration: contentActions.onCancelGeneration,
    onGenerateKnowledgeCards: contentActions.onGenerateKnowledgeCards,
    onCreateNote: contentActions.onCreateNote,
    onUpdateNote: contentActions.onUpdateNote,
    onDeleteNote: contentActions.onDeleteNote,
    onToggleSettingsPanel: settingsActions.onToggleSettingsPanel,
    onCloseSettingsPanel: settingsActions.onCloseSettingsPanel,
    onChangeSetting: settingsActions.onChangeSetting,
    onSaveApiKey: settingsActions.onSaveApiKey,
    onDownloadFasterWhisperModel: settingsActions.onDownloadFasterWhisperModel,
    onCancelFasterWhisperModelDownload: settingsActions.onCancelFasterWhisperModelDownload,
    onResetSettings: settingsActions.onResetSettings,
    onClearError,
    onResolveLinkedSeries: contentActions.onResolveLinkedSeries,
    onResolvePlaygroundVideo: contentActions.onResolvePlaygroundVideo,
    onResolveSeriesVideo: contentActions.onResolveSeriesVideo,
    onImportLocalSeries: contentActions.onImportLocalSeries,
    onImportLocalPlaygroundVideos: contentActions.onImportLocalPlaygroundVideos,
    onImportSeriesVideos: contentActions.onImportSeriesVideos,
    onDeleteSeries: contentActions.onDeleteSeries,
    onDeleteCurrentVideo: contentActions.onDeleteCurrentVideo,
    onDownloadVideo: contentActions.onDownloadVideo,
  };
}
