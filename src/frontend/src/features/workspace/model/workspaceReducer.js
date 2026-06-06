import {
  appendChatSessionForScope,
  buildSeriesGenerationTaskKey,
  buildChatScopeKey,
  buildChatSessionTitleFromMessage,
  buildVideoGenerationTaskKey,
  createGenerationTaskRecord,
  createInitialWorkspaceState,
  createLibraryHomeState,
  createMindmapLoadedState,
  createNextChatSessionMeta,
  createSummaryLoadedState,
  createWelcomeChatMessages,
  createWorkspaceLoadedState,
  getChatMessagesForScope,
  getChatSessionMetaForScope,
  getContextUsageForScope,
  getGenerationTaskForKey,
  hasRecoveredChatScope,
  markVideoAsReady,
  normalizeUiSettings,
  persistChatSessionIdsByScope,
  removeChatSessionForScope,
  removeScopedValue,
  resolveChatSessionsForScope,
  setChatMessagesForScope,
  setChatSessionIdForScope,
  setContextUsageForScope,
  setGenerationTaskForKey,
  setRecoveredChatScope,
  updateChatSessionMetaForScope,
} from "./workspaceState";
import { applyChatStreamEvent, appendChatThreadMessage } from "./workspaceChatState";
import { PLAYGROUND_SERIES_ID } from "./workspaceControllerConstants";
import { buildVideoKey, updateVideoCardInLibrary } from "./workspaceControllerUtils";

function resolveNextSessionTitle(chatSessionListsByScope, chatBaseScopeKey, sessionId, message) {
  const currentMeta = getChatSessionMetaForScope(chatSessionListsByScope, chatBaseScopeKey, sessionId);
  const currentTitle = currentMeta?.title ?? "";
  if (
    currentTitle &&
    currentTitle !== "当前对话" &&
    !currentTitle.startsWith("新对话")
  ) {
    return currentTitle;
  }
  return buildChatSessionTitleFromMessage(message);
}

function createRunningSnapshot(detail) {
  return {
    status: "running",
    stage: "prepare",
    progress: 0,
    detail,
    error: null,
    startedAt: null,
    stageStartedAt: null,
    elapsedSeconds: 0,
    stageElapsedSeconds: 0,
    estimatedTotalSeconds: null,
    remainingSeconds: null,
  };
}

function resolveSeriesQueueStatus(snapshotStatus, currentStatus) {
  if (snapshotStatus === "cancelling") {
    return "cancelling";
  }
  if (snapshotStatus === "completed" || snapshotStatus === "failed" || snapshotStatus === "cancelled") {
    return snapshotStatus;
  }
  return currentStatus;
}

function matchesCurrentGenerationSelection(state, action) {
  if (action.mode === "video") {
    return (
      state.selectedContextType === "video" &&
      state.selectedSeriesId === action.seriesId &&
      state.selectedVideoId === action.videoId
    );
  }
  if (action.mode === "series") {
    return (
      state.selectedContextType === "series" &&
      state.selectedSeriesId === action.seriesId
    );
  }
  return false;
}

function isTerminalGenerationStatus(status) {
  return status === "completed" || status === "failed" || status === "cancelled";
}

export { createInitialWorkspaceState };

export function workspaceReducer(state, action) {
  switch (action.type) {
    case "workspace_loaded":
      return createWorkspaceLoadedState(action.library, state);
    case "backend_health_ready":
      return {
        ...state,
        backendReady: true,
        error: "",
      };
    case "library_home_selected":
      return createLibraryHomeState(state.library, state);
    case "workspace_settings_loaded":
      return {
        ...state,
        ui: normalizeUiSettings(action.settings),
      };
    case "workspace_setting_edited":
      return {
        ...state,
        ui: {
          ...state.ui,
          [action.key]: action.value,
        },
      };
    case "provider_settings_loaded":
      return {
        ...state,
        ui: normalizeUiSettings({
          ...state.ui,
          ...action.settings,
        }),
      };
    case "faster_whisper_models_loading_started":
      return {
        ...state,
        fasterWhisperModelsLoading: true,
      };
    case "faster_whisper_model_download_started":
      return {
        ...state,
        downloadingModelId: action.modelId,
        modelDownloadStatus: "running",
        modelDownloadProgress: 0,
        modelDownloadErrorModelId: null,
        modelDownloadError: null,
        fasterWhisperModelsLoading: false,
        error: "",
      };
    case "faster_whisper_model_download_progress_updated":
      return {
        ...state,
        downloadingModelId: action.modelId,
        modelDownloadStatus: action.status ?? state.modelDownloadStatus,
        modelDownloadProgress: action.progress == null ? null : Math.max(0, Math.min(100, action.progress)),
        modelDownloadErrorModelId: null,
        modelDownloadError: null,
      };
    case "faster_whisper_model_download_failed":
      return {
        ...state,
        downloadingModelId: null,
        modelDownloadStatus: "failed",
        modelDownloadProgress: null,
        modelDownloadErrorModelId: action.modelId,
        modelDownloadError: action.message,
        fasterWhisperModelsLoading: false,
      };
    case "faster_whisper_models_loaded":
      return {
        ...state,
        fasterWhisperModels: action.models,
        fasterWhisperModelsLoading: false,
        downloadingModelId: null,
        modelDownloadStatus: null,
        modelDownloadProgress: null,
        modelDownloadErrorModelId: null,
        modelDownloadError: null,
      };
    case "rag_models_loading_started":
      return {
        ...state,
        ragModelsLoading: true,
      };
    case "rag_model_download_started":
      return {
        ...state,
        downloadingRagModelKey: action.modelKey,
        ragModelsLoading: true,
        ragModels: state.ragModels.map((model) => model.key === action.modelKey
          ? {
            ...model,
            status: "running",
            progress: 0,
            error: null,
          }
          : model),
        error: "",
      };
    case "rag_model_download_progress_updated":
      return {
        ...state,
        downloadingRagModelKey: action.modelKey,
        ragModelsLoading: false,
        ragModels: state.ragModels.map((model) => model.key === action.modelKey
          ? {
            ...model,
            status: action.status ?? model.status,
            progress: action.progress == null ? null : Math.max(0, Math.min(100, action.progress)),
            detail: action.detail ?? model.detail,
            error: action.error ?? model.error,
          }
          : model),
      };
    case "rag_model_download_failed":
      return {
        ...state,
        downloadingRagModelKey: null,
        ragModelsLoading: false,
        ragModels: state.ragModels.map((model) => model.key === action.modelKey
          ? {
            ...model,
            status: "failed",
            progress: null,
            error: action.message,
          }
          : model),
      };
    case "rag_models_loaded":
      return {
        ...state,
        ragModels: action.models,
        ragModelsLoading: false,
        downloadingRagModelKey: action.models.some((model) => model.status === "running")
          ? (state.downloadingRagModelKey ?? action.models.find((model) => model.status === "running")?.key ?? null)
          : null,
      };
    case "chaoxing_chromium_loading_started":
      return {
        ...state,
        chaoxingChromiumLoading: true,
      };
    case "chaoxing_chromium_download_started":
      return {
        ...state,
        chaoxingChromiumDownloading: true,
        chaoxingChromiumLoading: true,
        chaoxingChromium: state.chaoxingChromium == null
          ? state.chaoxingChromium
          : {
            ...state.chaoxingChromium,
            status: "running",
            progress: null,
            error: null,
          },
        error: "",
      };
    case "chaoxing_chromium_download_progress_updated":
      return {
        ...state,
        chaoxingChromiumDownloading: action.status === "running",
        chaoxingChromiumLoading: false,
        chaoxingChromium: state.chaoxingChromium == null
          ? state.chaoxingChromium
          : {
            ...state.chaoxingChromium,
            status: action.status ?? state.chaoxingChromium.status,
            progress: null,
            detail: action.detail ?? state.chaoxingChromium.detail,
            error: action.error ?? state.chaoxingChromium.error,
          },
      };
    case "chaoxing_chromium_download_failed":
      return {
        ...state,
        chaoxingChromiumDownloading: false,
        chaoxingChromiumLoading: false,
        chaoxingChromium: state.chaoxingChromium == null
          ? state.chaoxingChromium
          : {
            ...state.chaoxingChromium,
            status: "failed",
            progress: null,
            error: action.message,
          },
      };
    case "chaoxing_chromium_loaded":
      return {
        ...state,
        chaoxingChromium: action.chromium,
        chaoxingChromiumLoading: false,
        chaoxingChromiumDownloading: action.chromium?.status === "running",
      };
    case "load_failed":
      return {
        ...state,
        loading: false,
        toolsLoading: false,
        summaryLoading: false,
        mindmapLoading: false,
        knowledgeCardsLoading: false,
        knowledgeCardsGenerating: false,
        notesLoading: false,
        savingNote: false,
        generatingVideoKey: null,
        generatingSeriesId: null,
        generationMode: null,
        generatingMindmapKey: null,
        generationProgress: null,
        generationSnapshot: null,
        downloadingVideoKey: null,
        videoDownloadProgress: null,
        downloadingModelId: null,
        modelDownloadStatus: null,
        modelDownloadProgress: null,
        downloadingRagModelKey: null,
        chaoxingChromiumDownloading: false,
        contextUsageLoading: false,
        error: action.message,
        fasterWhisperModelsLoading: false,
        ragModelsLoading: false,
        chaoxingChromiumLoading: false,
      };
    case "error_cleared":
      return {
        ...state,
        error: "",
      };
    case "series_selected": {
      const chatBaseScopeKey = buildChatScopeKey("series", action.seriesId, null, "series-home");
      const chatSessionScope = resolveChatSessionsForScope(
        state.chatSessionIdsByScope,
        state.chatSessionListsByScope,
        chatBaseScopeKey,
      );
      persistChatSessionIdsByScope(chatSessionScope.chatSessionIdsByScope, chatSessionScope.chatSessionListsByScope);
      const chatScopeKey = chatSessionScope.activeSessionId;
      return {
        ...state,
        tools: null,
        selectedSeriesId: action.seriesId,
        selectedVideoId: null,
        selectedContextType: "series",
        selectedToolId: "series-home",
        summary: null,
        mindmap: null,
        knowledgeCards: null,
        knowledgeCardsFeedback: null,
        notes: null,
        selectedChapterId: null,
        selectedNodeId: null,
        previewSeekRequest: null,
        generationProgress: null,
        generationSnapshot: null,
        generatingSeriesId: null,
        generationMode: null,
        chatBaseScopeKey,
        chatScopeKey,
        chatSessionIdsByScope: chatSessionScope.chatSessionIdsByScope,
        chatSessionListsByScope: chatSessionScope.chatSessionListsByScope,
        chatMessages: getChatMessagesForScope(state.chatThreads, chatScopeKey),
        chatPending: false,
        contextUsage: getContextUsageForScope(state.contextUsageByScope, chatScopeKey),
        contextUsageLoading: false,
      };
    }
    case "playground_selected":
      return {
        ...state,
        selectedSeriesId: PLAYGROUND_SERIES_ID,
        selectedVideoId: null,
        selectedContextType: "playground",
        selectedToolId: "studio",
        tools: null,
        summary: null,
        mindmap: null,
        knowledgeCards: null,
        knowledgeCardsFeedback: null,
        notes: null,
        selectedChapterId: null,
        selectedNodeId: null,
        previewSeekRequest: null,
        generationProgress: null,
        generationSnapshot: null,
        generatingSeriesId: null,
        generationMode: null,
        downloadingVideoKey: null,
        videoDownloadProgress: null,
        chatBaseScopeKey: null,
        chatScopeKey: null,
        chatMessages: [],
        chatPending: false,
        chatRecoveryLoading: false,
        contextUsage: null,
        contextUsageLoading: false,
      };
    case "video_selected": {
      const chatBaseScopeKey = buildChatScopeKey("video", action.seriesId, action.videoId, "studio");
      const chatSessionScope = resolveChatSessionsForScope(
        state.chatSessionIdsByScope,
        state.chatSessionListsByScope,
        chatBaseScopeKey,
      );
      persistChatSessionIdsByScope(chatSessionScope.chatSessionIdsByScope, chatSessionScope.chatSessionListsByScope);
      const chatScopeKey = chatSessionScope.activeSessionId;
      return {
        ...state,
        selectedSeriesId: action.seriesId,
        selectedVideoId: action.videoId,
        selectedContextType: "video",
        selectedToolId: "studio",
        tools: null,
        summary: null,
        mindmap: null,
        knowledgeCards: null,
        knowledgeCardsFeedback: null,
        notes: null,
        selectedChapterId: null,
        selectedNodeId: null,
        previewSeekRequest: null,
        generationProgress: null,
        generationSnapshot: null,
        generatingSeriesId: null,
        generationMode: null,
        downloadingVideoKey: null,
        videoDownloadProgress: null,
        chatBaseScopeKey,
        chatScopeKey,
        chatSessionIdsByScope: chatSessionScope.chatSessionIdsByScope,
        chatSessionListsByScope: chatSessionScope.chatSessionListsByScope,
        chatMessages: getChatMessagesForScope(state.chatThreads, chatScopeKey),
        chatPending: false,
        contextUsage: getContextUsageForScope(state.contextUsageByScope, chatScopeKey),
        contextUsageLoading: false,
      };
    }
    case "tool_selected":
      return {
        ...state,
        selectedToolId: action.toolId,
        knowledgeCardsFeedback: action.toolId === "knowledge-cards" ? state.knowledgeCardsFeedback : null,
        error: "",
      };
    case "series_context_selected": {
      const chatBaseScopeKey = buildChatScopeKey("series", state.selectedSeriesId, null, "series-home");
      const chatSessionScope = resolveChatSessionsForScope(
        state.chatSessionIdsByScope,
        state.chatSessionListsByScope,
        chatBaseScopeKey,
      );
      persistChatSessionIdsByScope(chatSessionScope.chatSessionIdsByScope, chatSessionScope.chatSessionListsByScope);
      const chatScopeKey = chatSessionScope.activeSessionId;
      return {
        ...state,
        selectedContextType: "series",
        selectedVideoId: null,
        selectedToolId: "series-home",
        tools: null,
        summary: null,
        mindmap: null,
        knowledgeCards: null,
        knowledgeCardsFeedback: null,
        notes: null,
        selectedChapterId: null,
        selectedNodeId: null,
        previewSeekRequest: null,
        generationProgress: null,
        generationSnapshot: null,
        downloadingVideoKey: null,
        videoDownloadProgress: null,
        chatBaseScopeKey,
        chatScopeKey,
        chatSessionIdsByScope: chatSessionScope.chatSessionIdsByScope,
        chatSessionListsByScope: chatSessionScope.chatSessionListsByScope,
        chatMessages: getChatMessagesForScope(state.chatThreads, chatScopeKey),
        chatPending: false,
        contextUsage: getContextUsageForScope(state.contextUsageByScope, chatScopeKey),
        contextUsageLoading: false,
      };
    }
    case "tools_loading_started":
      return {
        ...state,
        toolsLoading: true,
        error: "",
      };
    case "tools_loaded":
      return {
        ...state,
        tools: action.tools,
        toolsLoading: false,
        error: "",
      };
    case "summary_loading_started":
      return {
        ...state,
        summaryLoading: true,
        error: "",
      };
    case "summary_loaded":
      return createSummaryLoadedState(action.summary, {
        ...state,
        error: "",
      });
    case "summary_cleared":
      return {
        ...state,
        summary: null,
        summaryLoading: false,
        selectedChapterId: null,
      };
    case "mindmap_loading_started":
      return {
        ...state,
        mindmapLoading: true,
        error: "",
      };
    case "mindmap_loaded":
      return createMindmapLoadedState(action.mindmap, {
        ...state,
        error: "",
      });
    case "mindmap_cleared":
      return {
        ...state,
        mindmap: null,
        mindmapLoading: false,
        selectedNodeId: null,
      };
    case "knowledge_cards_loading_started":
      return {
        ...state,
        knowledgeCardsLoading: true,
        knowledgeCardsGenerating: false,
        error: "",
      };
    case "knowledge_cards_generation_started":
      return {
        ...state,
        knowledgeCardsLoading: true,
        knowledgeCardsGenerating: true,
        knowledgeCardsFeedback: null,
        error: "",
      };
    case "knowledge_cards_loaded":
      return {
        ...state,
        knowledgeCards: action.cards,
        knowledgeCardsLoading: false,
        knowledgeCardsGenerating: false,
        knowledgeCardsFeedback:
          action.feedbackMessage == null
            ? state.knowledgeCardsFeedback
            : {
              tone: action.feedbackTone ?? "success",
              message: action.feedbackMessage,
            },
        tools: state.tools == null
          ? state.tools
          : {
            ...state.tools,
            knowledgeCards: {
              ...state.tools.knowledgeCards,
              available: true,
              generated: true,
              status: "ready",
            },
          },
      };
    case "knowledge_cards_cleared":
      return {
        ...state,
        knowledgeCards: null,
        knowledgeCardsLoading: false,
        knowledgeCardsGenerating: false,
        knowledgeCardsFeedback: null,
      };
    case "knowledge_cards_feedback_cleared":
      return {
        ...state,
        knowledgeCardsFeedback: null,
      };
    case "notes_loading_started":
      return {
        ...state,
        notesLoading: true,
        error: "",
      };
    case "notes_loaded":
      return {
        ...state,
        notes: action.notes,
        notesLoading: false,
        error: "",
      };
    case "notes_cleared":
      return {
        ...state,
        notes: null,
        notesLoading: false,
      };
    case "note_save_started":
      return {
        ...state,
        savingNote: true,
        error: "",
      };
    case "note_created":
      return {
        ...state,
        savingNote: false,
        notes: state.notes == null
          ? {
            seriesId: action.seriesId,
            videoId: action.videoId,
            title: action.videoTitle,
            notes: [action.note],
          }
          : {
            ...state.notes,
            notes: [action.note, ...state.notes.notes],
          },
      };
    case "note_updated":
      return {
        ...state,
        savingNote: false,
        notes: state.notes == null
          ? state.notes
          : {
            ...state.notes,
            notes: state.notes.notes.map((note) => (note.id === action.note.id ? action.note : note)),
          },
      };
    case "note_deleted":
      return {
        ...state,
        savingNote: false,
        notes: state.notes == null
          ? state.notes
          : {
            ...state.notes,
            notes: state.notes.notes.filter((note) => note.id !== action.noteId),
          },
      };
    case "chapter_selected":
      return {
        ...state,
        selectedChapterId: action.chapterId,
      };
    case "node_selected":
      return {
        ...state,
        selectedNodeId: action.nodeId,
        selectedChapterId: action.chapterId ?? state.selectedChapterId,
      };
    case "preview_seek_requested":
      return {
        ...state,
        previewSeekRequest: {
          seconds: action.seconds,
          endSeconds: action.endSeconds ?? null,
          query: action.query ?? "",
          matchedText: action.matchedText ?? "",
          chapterTitle: action.chapterTitle ?? "",
          requestId: action.requestId,
        },
      };
    case "settings_panel_toggled":
      return {
        ...state,
        settingsPanelOpen: !state.settingsPanelOpen,
        settingsPanelInitialTab: "general",
      };
    case "settings_panel_opened":
      return {
        ...state,
        settingsPanelOpen: true,
        settingsPanelInitialTab: action.initialTab ?? "general",
      };
    case "chat_request_started": {
      const nextState = appendChatThreadMessage(state, action.chatScopeKey, {
        id: action.userMessageId,
        role: "user",
        content: action.message,
        meta: "You • Just now",
      }, true);
      const nextSessionListsByScope = updateChatSessionMetaForScope(
        nextState.chatSessionListsByScope,
        nextState.chatBaseScopeKey,
        action.chatScopeKey,
        {
          title: resolveNextSessionTitle(nextState.chatSessionListsByScope, nextState.chatBaseScopeKey, action.chatScopeKey, action.message),
          updatedAt: Date.now(),
        },
      );
      persistChatSessionIdsByScope(nextState.chatSessionIdsByScope, nextSessionListsByScope);
      return {
        ...nextState,
        chatSessionListsByScope: nextSessionListsByScope,
      };
    }
    case "chat_stream_event_received":
      return applyChatStreamEvent(state, action.chatScopeKey, action.requestId, action.event);
    case "chat_response_received":
      return appendChatThreadMessage(state, action.chatScopeKey, {
        id: action.assistantMessageId,
        role: "assistant",
        content: action.message,
        meta: action.meta ?? "Notebook Assistant • Just now",
      }, false);
    case "chat_tool_trace_recorded":
      return appendChatThreadMessage(state, action.chatScopeKey, {
        id: action.messageId,
        role: "assistant",
        kind: "tool-trace",
        content: action.summary,
        toolTrace: {
          steps: action.steps,
          durationMs: action.durationMs,
        },
        meta: action.meta ?? "Notebook Assistant • Tool Chain",
      }, true);
    case "settings_panel_closed":
      return {
        ...state,
        settingsPanelOpen: false,
      };
    case "generation_started":
      return {
        ...state,
        generatingVideoKey: action.videoKey,
        generatingSeriesId: null,
        generationMode: "video",
        generationProgress: 0,
        generationSnapshot: createRunningSnapshot("任务已开始"),
        generationTasksByKey: setGenerationTaskForKey(
          state.generationTasksByKey,
          createGenerationTaskRecord({
            taskKey: buildVideoGenerationTaskKey(action.seriesId, action.videoId),
            mode: "video",
            seriesId: action.seriesId,
            videoId: action.videoId,
            snapshot: createRunningSnapshot("任务已开始"),
          }),
        ),
        error: "",
      };
    case "video_generation_cancelling": {
      const taskKey = buildVideoGenerationTaskKey(action.seriesId, action.videoId);
      const existing = state.generationTasksByKey?.[taskKey];
      if (!existing) return state;
      return {
        ...state,
        generationTasksByKey: setGenerationTaskForKey(
          state.generationTasksByKey,
          createGenerationTaskRecord({
            ...existing,
            snapshot: { ...(existing.snapshot ?? {}), status: "cancelling", detail: "正在停止当前任务" },
          }),
        ),
      };
    }
    case "series_generation_queue_started":
      return {
        ...state,
        seriesGenerationQueue: {
          seriesId: action.seriesId,
          total: action.total,
          completed: 0,
          currentIndex: 0,
          currentVideoId: null,
          currentVideoTitle: null,
          activeVideos: [],
          detail: `已结束 0/${action.total}`,
          status: "running",
        },
        error: "",
      };
    case "series_generation_queue_item_started":
      return {
        ...state,
        seriesGenerationQueue:
          state.seriesGenerationQueue?.seriesId !== action.seriesId
            ? state.seriesGenerationQueue
            : {
                ...state.seriesGenerationQueue,
                currentIndex: action.currentIndex,
                currentVideoId: action.videoId,
                currentVideoTitle: action.videoTitle,
                activeVideos: [
                  ...(state.seriesGenerationQueue.activeVideos ?? []).filter((video) => video.id !== action.videoId),
                  { id: action.videoId, title: action.videoTitle, index: action.currentIndex },
                ],
                status: "running",
              },
      };
    case "series_generation_queue_item_finished":
      return {
        ...state,
        seriesGenerationQueue:
          state.seriesGenerationQueue?.seriesId !== action.seriesId
            ? state.seriesGenerationQueue
            : {
                ...state.seriesGenerationQueue,
                activeVideos: (state.seriesGenerationQueue.activeVideos ?? []).filter(
                  (video) => video.id !== action.videoId,
                ),
              },
      };
    case "series_generation_queue_item_completed":
      return {
        ...state,
        seriesGenerationQueue:
          state.seriesGenerationQueue?.seriesId !== action.seriesId
            ? state.seriesGenerationQueue
            : {
                ...state.seriesGenerationQueue,
                completed: Math.min(state.seriesGenerationQueue.total, state.seriesGenerationQueue.completed + 1),
              },
      };
    case "series_generation_queue_cancelling":
      return {
        ...state,
        seriesGenerationQueue:
          state.seriesGenerationQueue?.seriesId !== action.seriesId
            ? state.seriesGenerationQueue
            : {
                ...state.seriesGenerationQueue,
                status: "cancelling",
              },
      };
    case "series_generation_queue_finished":
      return {
        ...state,
        seriesGenerationQueue:
          state.seriesGenerationQueue?.seriesId !== action.seriesId
            ? state.seriesGenerationQueue
            : {
                ...state.seriesGenerationQueue,
                status: action.status ?? "completed",
                currentVideoId: null,
                currentVideoTitle: null,
              },
      };
    case "series_generation_started":
      return {
        ...state,
        generatingSeriesId: action.seriesId,
        generatingVideoKey: null,
        generationMode: "series",
        generationProgress: 0,
        generationSnapshot: createRunningSnapshot("系列任务已开始"),
        generationTasksByKey: setGenerationTaskForKey(
          state.generationTasksByKey,
          createGenerationTaskRecord({
            taskKey: buildSeriesGenerationTaskKey(action.seriesId),
            mode: "series",
            seriesId: action.seriesId,
            snapshot: createRunningSnapshot("系列任务已开始"),
          }),
        ),
        error: "",
      };
    case "generation_progress_updated":
      {
        const boundedProgress = action.progress == null ? null : Math.max(0, Math.min(100, action.progress));
        const isCurrentSelection = matchesCurrentGenerationSelection(state, action);
        const isTerminal = isTerminalGenerationStatus(action.snapshot?.status);
        const nextState = {
          ...state,
          generatingVideoKey:
            isCurrentSelection && isTerminal && action.mode === "video"
              ? null
              : state.generatingVideoKey,
          generatingSeriesId:
            isCurrentSelection && isTerminal && action.mode === "series"
              ? null
              : state.generatingSeriesId,
          generationMode:
            isCurrentSelection && isTerminal
              ? null
              : state.generationMode,
          generationProgress:
            isCurrentSelection && isTerminal ? null : boundedProgress,
          generationSnapshot:
            isCurrentSelection && isTerminal ? null : action.snapshot,
          generationTasksByKey: setGenerationTaskForKey(
            state.generationTasksByKey,
            createGenerationTaskRecord({
              taskKey: action.taskKey,
              mode: action.mode,
              seriesId: action.seriesId,
              videoId: action.videoId ?? null,
              snapshot: action.snapshot,
              subscriptionActive: action.subscriptionActive ?? false,
            }),
          ),
        };
        if (action.mode !== "series" || state.seriesGenerationQueue?.seriesId !== action.seriesId) {
          return nextState;
        }
        const total = state.seriesGenerationQueue.total;
        const completed = boundedProgress == null
          ? state.seriesGenerationQueue.completed
          : Math.min(total, Math.floor((boundedProgress / 100) * total));
        return {
          ...nextState,
          seriesGenerationQueue: {
            ...state.seriesGenerationQueue,
            completed,
            detail: action.snapshot?.detail ?? state.seriesGenerationQueue.detail,
            status: resolveSeriesQueueStatus(action.snapshot?.status, state.seriesGenerationQueue.status),
            currentVideoId: isTerminal ? null : state.seriesGenerationQueue.currentVideoId,
            currentVideoTitle: isTerminal ? null : state.seriesGenerationQueue.currentVideoTitle,
          },
        };
      }
    case "generation_status_loaded":
      {
        const isTerminal = isTerminalGenerationStatus(action.snapshot?.status);
        const isCurrentSelection = matchesCurrentGenerationSelection(state, action);
        return {
          ...state,
          generatingVideoKey:
            isTerminal && isCurrentSelection && action.mode === "video"
              ? null
              : state.generatingVideoKey,
          generatingSeriesId:
            isTerminal && isCurrentSelection && action.mode === "series"
              ? null
              : state.generatingSeriesId,
          generationMode:
            isTerminal && isCurrentSelection ? null : state.generationMode,
          generationProgress:
            isTerminal && isCurrentSelection ? null : state.generationProgress,
          generationSnapshot:
            isTerminal && isCurrentSelection ? null : state.generationSnapshot,
          seriesGenerationQueue:
            action.mode === "series" &&
            state.seriesGenerationQueue?.seriesId === action.seriesId &&
            isTerminal
              ? {
                  ...state.seriesGenerationQueue,
                  status: action.snapshot?.status ?? state.seriesGenerationQueue.status,
                  currentVideoId: null,
                  currentVideoTitle: null,
                }
              : state.seriesGenerationQueue,
          generationTasksByKey: setGenerationTaskForKey(
            state.generationTasksByKey,
            createGenerationTaskRecord({
              taskKey: action.taskKey,
              mode: action.mode,
              seriesId: action.seriesId,
              videoId: action.videoId ?? null,
              snapshot: action.snapshot,
              subscriptionActive: Boolean(action.subscriptionActive),
            }),
          ),
        };
      }
    case "generation_cancelled":
      return {
        ...state,
        generatingVideoKey: null,
        generatingSeriesId: null,
        generationMode: null,
        generationProgress: null,
        generationSnapshot: null,
        seriesGenerationQueue:
          action.mode === "series" && state.seriesGenerationQueue?.seriesId === action.seriesId
            ? {
                ...state.seriesGenerationQueue,
                status: "cancelled",
                currentVideoId: null,
                currentVideoTitle: null,
              }
            : state.seriesGenerationQueue,
        generationTasksByKey: setGenerationTaskForKey(
          state.generationTasksByKey,
          createGenerationTaskRecord({
            taskKey: action.taskKey,
            mode: action.mode,
            seriesId: action.seriesId,
            videoId: action.videoId ?? null,
            snapshot: action.snapshot ?? { status: "cancelled", stage: "cancelled", progress: null, detail: "任务已取消", error: null },
            subscriptionActive: false,
          }),
        ),
      };
    case "generation_succeeded":
      {
        const isCurrentVideo =
          state.selectedContextType === "video" &&
          state.selectedSeriesId === action.seriesId &&
          state.selectedVideoId === action.videoId;
        const nextState = {
          ...state,
          library: markVideoAsReady(state.library, action.seriesId, action.videoId),
          tools: !isCurrentVideo || state.tools == null
            ? state.tools
            : {
              ...state.tools,
              overview: {
                ...state.tools.overview,
                generated: true,
                status: "ready",
              },
              mindmap: {
                ...state.tools.mindmap,
                available: true,
                generated: false,
                status: "available",
              },
              knowledgeCards: {
                ...state.tools.knowledgeCards,
                available: true,
                generated: false,
                status: "available",
              },
            },
          generatingVideoKey: null,
          generatingSeriesId: null,
          generationMode: null,
          generationProgress: null,
          generationSnapshot: null,
          generationTasksByKey: setGenerationTaskForKey(
            state.generationTasksByKey,
            createGenerationTaskRecord({
              taskKey: action.taskKey ?? buildVideoGenerationTaskKey(action.seriesId, action.videoId),
              mode: "video",
              seriesId: action.seriesId,
              videoId: action.videoId,
              snapshot: {
                status: "completed",
                stage: "completed",
                progress: 100,
                detail: "AI 概况已生成",
                error: null,
              },
              subscriptionActive: false,
            }),
          ),
        };
        return isCurrentVideo ? createSummaryLoadedState(action.summary, nextState) : nextState;
      }
    case "series_generation_succeeded":
      return {
        ...state,
        library: action.library ?? state.library,
        generatingSeriesId: null,
        generatingVideoKey: null,
        generationMode: null,
        generationProgress: null,
        generationSnapshot: null,
        generationTasksByKey: setGenerationTaskForKey(
          state.generationTasksByKey,
          createGenerationTaskRecord({
            taskKey: action.taskKey ?? buildSeriesGenerationTaskKey(action.seriesId),
            mode: "series",
            seriesId: action.seriesId,
            snapshot: {
              status: "completed",
              stage: "completed",
              progress: 100,
              detail: "系列任务已完成",
              error: null,
            },
            subscriptionActive: false,
          }),
        ),
      };
    case "video_download_started":
      return {
        ...state,
        downloadingVideoKey: buildVideoKey(action.seriesId, action.videoId),
        videoDownloadProgress: 0,
        library: updateVideoCardInLibrary(
          state.library,
          action.seriesId,
          action.videoId,
          (video) => ({
            ...video,
            status: "downloading",
          }),
        ),
        error: "",
      };
    case "video_download_progress_updated":
      return state.downloadingVideoKey !== buildVideoKey(action.seriesId, action.videoId)
        ? state
        : {
            ...state,
            videoDownloadProgress:
              action.progress == null ? state.videoDownloadProgress : Math.max(0, Math.min(100, action.progress)),
          };
    case "video_download_completed":
      return {
        ...state,
        downloadingVideoKey: null,
        videoDownloadProgress: null,
        library: action.library,
      };
    case "video_download_failed":
      return {
        ...state,
        downloadingVideoKey: null,
        videoDownloadProgress: null,
      };
    case "mindmap_generation_started":
      return {
        ...state,
        generatingMindmapKey: action.videoKey,
        error: "",
      };
    case "mindmap_generation_succeeded":
      return createMindmapLoadedState(action.mindmap, {
        ...state,
        tools: state.tools == null
          ? state.tools
          : {
            ...state.tools,
            mindmap: {
              ...state.tools.mindmap,
              available: true,
              generated: true,
              status: "ready",
            },
          },
        generatingMindmapKey: null,
      });
    case "chat_pending_cleared":
      return {
        ...state,
        chatPending: false,
      };
    case "chat_recovery_started":
      return {
        ...state,
        chatRecoveryLoading: true,
      };
    case "chat_recovery_loaded": {
      const nextMessages =
        action.restored && action.messages.length ? action.messages : getChatMessagesForScope(state.chatThreads, action.chatScopeKey);
      return {
        ...state,
        chatRecoveryLoading: false,
        chatRecoveryByScope: setRecoveredChatScope(state.chatRecoveryByScope, action.chatScopeKey, true),
        chatThreads: action.restored && action.messages.length
          ? setChatMessagesForScope(state.chatThreads, action.chatScopeKey, action.messages)
          : state.chatThreads,
        chatMessages: state.chatScopeKey === action.chatScopeKey ? nextMessages : state.chatMessages,
      };
    }
    case "chat_session_started": {
      const chatSessionIdsByScope = setChatSessionIdForScope(
        state.chatSessionIdsByScope,
        action.chatBaseScopeKey,
        action.sessionId,
      );
      const chatSessionListsByScope = appendChatSessionForScope(
        state.chatSessionListsByScope,
        action.chatBaseScopeKey,
        action.sessionMeta,
      );
      persistChatSessionIdsByScope(chatSessionIdsByScope, chatSessionListsByScope);
      return {
        ...state,
        chatSessionIdsByScope,
        chatSessionListsByScope,
        chatBaseScopeKey: action.chatBaseScopeKey,
        chatScopeKey: action.sessionId,
        chatMessages: createWelcomeChatMessages(),
        chatThreads: setChatMessagesForScope(state.chatThreads, action.sessionId, createWelcomeChatMessages()),
        chatRecoveryByScope: setRecoveredChatScope(state.chatRecoveryByScope, action.sessionId, true),
        chatPending: false,
        contextUsage: null,
        contextUsageLoading: false,
        error: "",
      };
    }
    case "chat_session_selected": {
      const chatSessionIdsByScope = setChatSessionIdForScope(
        state.chatSessionIdsByScope,
        action.chatBaseScopeKey,
        action.sessionId,
      );
      persistChatSessionIdsByScope(chatSessionIdsByScope, state.chatSessionListsByScope);
      return {
        ...state,
        chatSessionIdsByScope,
        chatBaseScopeKey: action.chatBaseScopeKey,
        chatScopeKey: action.sessionId,
        chatMessages: getChatMessagesForScope(state.chatThreads, action.sessionId),
        chatPending: false,
        chatRecoveryLoading: false,
        contextUsage: getContextUsageForScope(state.contextUsageByScope, action.sessionId),
        contextUsageLoading: false,
      };
    }
    case "chat_session_removed": {
      const nextSessionListsByScope = removeChatSessionForScope(
        state.chatSessionListsByScope,
        action.chatBaseScopeKey,
        action.sessionId,
      );
      const nextChatThreads = removeScopedValue(state.chatThreads, action.sessionId);
      const nextChatRecoveryByScope = removeScopedValue(state.chatRecoveryByScope, action.sessionId);
      const nextContextUsageByScope = removeScopedValue(state.contextUsageByScope, action.sessionId);
      const resolvedSessions = resolveChatSessionsForScope(
        state.chatSessionIdsByScope,
        nextSessionListsByScope,
        action.chatBaseScopeKey,
      );
      persistChatSessionIdsByScope(resolvedSessions.chatSessionIdsByScope, resolvedSessions.chatSessionListsByScope);
      return {
        ...state,
        chatPending: false,
        chatSessionIdsByScope: resolvedSessions.chatSessionIdsByScope,
        chatSessionListsByScope: resolvedSessions.chatSessionListsByScope,
        chatScopeKey: resolvedSessions.activeSessionId,
        chatMessages: getChatMessagesForScope(nextChatThreads, resolvedSessions.activeSessionId),
        chatThreads: nextChatThreads,
        chatRecoveryByScope: nextChatRecoveryByScope,
        contextUsageByScope: nextContextUsageByScope,
        contextUsage: getContextUsageForScope(nextContextUsageByScope, resolvedSessions.activeSessionId),
        contextUsageLoading: false,
        chatRecoveryLoading: false,
        error: "",
      };
    }
    case "context_usage_loading_started":
      return {
        ...state,
        contextUsageLoading: state.chatScopeKey != null,
      };
    case "context_usage_loaded":
      return {
        ...state,
        contextUsageLoading: false,
        contextUsage:
          action.currentScopeKey === action.chatScopeKey
            ? action.usage
            : state.contextUsage,
        contextUsageByScope: setContextUsageForScope(state.contextUsageByScope, action.chatScopeKey, action.usage),
      };
    case "knowledge_memory_status_loaded":
      return {
        ...state,
        knowledgeMemorySnapshot: action.snapshot,
      };
    default:
      return state;
  }
}
