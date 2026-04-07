import { useEffect, useMemo, useReducer } from "react";

import {
  clearAgentSession,
  cancelFasterWhisperModelDownload,
  createVideoNote,
  deleteVideoNote,
  downloadFasterWhisperModel,
  generateVideoKnowledgeCards,
  generateVideoMindmap,
  generateVideoSummary,
  getVideoPreviewUrl,
  loadAgentContextUsage,
  loadAgentSessionRecovery,
  loadFasterWhisperModels,
  loadProviderSettings,
  loadVideoKnowledgeCards,
  loadVideoMindmap,
  loadVideoNotes,
  loadVideoSummary,
  streamAgentChat,
  loadWorkspaceSettings,
  loadVideoTools,
  loadWorkspaceLibrary,
  subscribeFasterWhisperModelDownloadProgress,
  subscribeVideoGenerationProgress,
  updateVideoNote,
  updateProviderSettings,
  updateWorkspaceSettings,
} from "./workspaceApi";
import { findChapterForNode, findNodeById } from "./workspaceTree";
import {
  createWelcomeChatMessages,
  createInitialWorkspaceState,
  createMindmapLoadedState,
  createSummaryLoadedState,
  createWorkspaceLoadedState,
  findSeriesById,
  findVideoById,
  getChatSessionIdForScope,
  getContextUsageForScope,
  getChatMessagesForScope,
  hasRecoveredChatScope,
  markVideoAsReady,
  normalizeUiSettings,
  persistChatSessionIdsByScope,
  resetUiSettings,
  buildChatScopeKey,
  setChatSessionIdForScope,
  setRecoveredChatScope,
  setContextUsageForScope,
  setChatMessagesForScope,
} from "./workspaceState";

function workspaceReducer(state, action) {
  switch (action.type) {
    case "workspace_loaded":
      return createWorkspaceLoadedState(action.library, state);
    case "workspace_settings_loaded":
      return {
        ...state,
        ui: normalizeUiSettings(action.settings),
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
        modelDownloadProgress: 0,
        fasterWhisperModelsLoading: true,
        error: "",
      };
    case "faster_whisper_model_download_progress_updated":
      return {
        ...state,
        downloadingModelId: action.modelId,
        modelDownloadProgress: action.progress == null ? null : Math.max(0, Math.min(100, action.progress)),
      };
    case "faster_whisper_model_download_cancelled":
      return {
        ...state,
        downloadingModelId: null,
        modelDownloadProgress: null,
        fasterWhisperModelsLoading: false,
      };
    case "faster_whisper_models_loaded":
      return {
        ...state,
        fasterWhisperModels: action.models,
        fasterWhisperModelsLoading: false,
        downloadingModelId: null,
        modelDownloadProgress: null,
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
        generatingMindmapKey: null,
        generationProgress: null,
        generationSnapshot: null,
        downloadingModelId: null,
        modelDownloadProgress: null,
        contextUsageLoading: false,
        error: action.message,
        fasterWhisperModelsLoading: false,
      };
    case "series_selected": {
      const chatBaseScopeKey = buildChatScopeKey("series", action.seriesId, null, "series-home");
      const chatScopeKey = getChatSessionIdForScope(state.chatSessionIdsByScope, chatBaseScopeKey);
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
        chatBaseScopeKey,
        chatScopeKey,
        chatMessages: getChatMessagesForScope(state.chatThreads, chatScopeKey),
        chatPending: false,
        contextUsage: getContextUsageForScope(state.contextUsageByScope, chatScopeKey),
        contextUsageLoading: false,
      };
    }
    case "video_selected": {
      const chatBaseScopeKey = buildChatScopeKey("video", action.seriesId, action.videoId, "studio");
      const chatScopeKey = getChatSessionIdForScope(state.chatSessionIdsByScope, chatBaseScopeKey);
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
        chatBaseScopeKey,
        chatScopeKey,
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
      const chatScopeKey = getChatSessionIdForScope(state.chatSessionIdsByScope, chatBaseScopeKey);
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
        chatBaseScopeKey,
        chatScopeKey,
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
      };
    case "summary_loading_started":
      return {
        ...state,
        summaryLoading: true,
        error: "",
      };
    case "summary_loaded":
      return createSummaryLoadedState(action.summary, state);
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
      return createMindmapLoadedState(action.mindmap, state);
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
      };
    case "chat_request_started":
      return appendChatThreadMessage(state, action.chatScopeKey, {
        id: action.userMessageId,
        role: "user",
        content: action.message,
        meta: "You • Just now",
      }, true);
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
        generationProgress: 0,
        generationSnapshot: {
          status: "running",
          stage: "prepare",
          progress: 0,
          detail: "任务已开始",
          error: null,
          startedAt: null,
          stageStartedAt: null,
          elapsedSeconds: 0,
          stageElapsedSeconds: 0,
          estimatedTotalSeconds: null,
          remainingSeconds: null,
        },
        error: "",
      };
    case "generation_progress_updated":
      return {
        ...state,
        generationProgress: action.progress == null ? null : Math.max(0, Math.min(100, action.progress)),
        generationSnapshot: action.snapshot,
      };
    case "generation_succeeded":
      return createSummaryLoadedState(action.summary, {
        ...state,
        library: markVideoAsReady(state.library, action.seriesId, action.videoId),
        tools: state.tools == null
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
        generationProgress: null,
        generationSnapshot: null,
      });
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
      persistChatSessionIdsByScope(chatSessionIdsByScope);
      return {
        ...state,
        chatSessionIdsByScope,
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
    case "chat_session_cleared":
      return {
        ...state,
        chatPending: false,
        chatMessages: createWelcomeChatMessages(),
        chatThreads: setChatMessagesForScope(state.chatThreads, action.sessionId, createWelcomeChatMessages()),
        contextUsage: null,
        contextUsageLoading: false,
        error: "",
      };
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
    default:
      return state;
  }
}

function applyChatThreadUpdate(state, chatScopeKey, nextMessages, chatPending) {
  return {
    ...state,
    chatPending,
    chatMessages: state.chatScopeKey === chatScopeKey ? nextMessages : state.chatMessages,
    chatThreads: setChatMessagesForScope(state.chatThreads, chatScopeKey, nextMessages),
    error: "",
  };
}

function appendChatThreadMessage(state, chatScopeKey, message, chatPending) {
  const currentMessages = getChatMessagesForScope(state.chatThreads, chatScopeKey);
  return applyChatThreadUpdate(state, chatScopeKey, [...currentMessages, message], chatPending);
}

function transformChatThreadMessages(state, chatScopeKey, transform, chatPending = state.chatPending) {
  const currentMessages = getChatMessagesForScope(state.chatThreads, chatScopeKey);
  return applyChatThreadUpdate(state, chatScopeKey, transform(currentMessages), chatPending);
}

function applyChatStreamEvent(state, chatScopeKey, requestId, event) {
  switch (event?.type) {
    case "thinking_started":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(
          messages,
          buildThinkingMessage(
            requestId,
            {
              ...event.payload,
              previous_summary: messages.find((message) => message.id === `thought-${requestId}`)?.thoughtTrace?.summary ?? "",
            },
            { status: "running" },
          ),
        ), true);
    case "thinking_delta":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, appendThinkingDelta(messages, requestId, event.payload?.delta)), true);
    case "thinking_completed":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, buildThinkingMessage(requestId, event.payload, { status: "completed" })), true);
    case "tool_started":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, buildToolTraceMessage(requestId, messages, event, false)), true);
    case "tool_completed":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, buildToolTraceMessage(requestId, messages, event, false)), true);
    case "tool_chain_completed":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, buildToolTraceMessage(requestId, messages, event, true)), true);
    case "answer_started":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, buildStreamingAnswerMessage(requestId, "", "running", null)), true);
    case "answer_delta":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, appendStreamingAnswerDelta(messages, requestId, event.payload?.delta)), true);
    case "answer_completed":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(
          messages,
          buildStreamingAnswerMessage(
            requestId,
            typeof event.payload?.message === "string" ? event.payload.message : getMessageContent(messages, `assistant-${requestId}`),
            "completed",
            event.payload?.duration_ms,
          ),
        ), false);
    default:
      return state;
  }
}

function upsertChatMessage(messages, nextMessage) {
  const nextMessages = [...messages];
  const index = nextMessages.findIndex((message) => message.id === nextMessage.id);
  if (index === -1) {
    nextMessages.push(nextMessage);
    return nextMessages;
  }
  nextMessages[index] = {
    ...nextMessages[index],
    ...nextMessage,
  };
  return nextMessages;
}

function getMessageContent(messages, messageId) {
  return messages.find((message) => message.id === messageId)?.content ?? "";
}

function buildThinkingMessage(requestId, payload, { status }) {
  const previousSummary = typeof payload?.previous_summary === "string" ? payload.previous_summary : "";
  const durationMs = typeof payload?.duration_ms === "number" ? payload.duration_ms : null;
  const summary = typeof payload?.summary === "string" && payload.summary
    ? payload.summary
    : previousSummary;
  return {
    id: `thought-${requestId}`,
    role: "assistant",
    kind: "thought-trace",
    content: status === "running" ? "思考中" : "思路已完成",
    thoughtTrace: {
      status,
      summary,
      durationMs,
    },
    meta: status === "running"
      ? "Notebook Assistant • 思考中"
      : buildStatusMeta("思路", durationMs),
  };
}

function buildToolTraceMessage(requestId, messages, event, completed) {
  const messageId = `tool-trace-${requestId}`;
  const previous = messages.find((message) => message.id === messageId);
  const previousSteps = Array.isArray(previous?.toolTrace?.steps) ? previous.toolTrace.steps : [];

  let nextSteps = previousSteps;
  if (event.type === "tool_started" || event.type === "tool_completed") {
    const step = buildToolTraceStep(event);
    nextSteps = upsertToolStep(previousSteps, step);
  }
  if (completed) {
    nextSteps = nextSteps.map((step) => ({
      ...step,
      status: "completed",
    }));
  }

  const durationMs = sumVisibleToolDurations(nextSteps);
  const status = completed
    ? "completed"
    : nextSteps.some((step) => step.status === "running")
      ? "running"
      : "idle";
  const stepCount = nextSteps.length;

  return {
    id: messageId,
    role: "assistant",
    kind: "tool-trace",
    content: status === "running"
      ? `正在调用 ${Math.max(stepCount, 1)} 个工具`
      : `已调用 ${stepCount} 个工具`,
    toolTrace: {
      status,
      steps: nextSteps,
      durationMs: typeof durationMs === "number" ? durationMs : null,
      stageDurationMs: event.type === "tool_chain_completed" && typeof event.payload?.duration_ms === "number"
        ? event.payload.duration_ms
        : previous?.toolTrace?.stageDurationMs ?? null,
    },
    meta: completed
      ? buildStatusMeta("工具链", durationMs)
      : status === "running"
        ? "Notebook Assistant • 正在调用工具"
        : "Notebook Assistant • 等待下一步",
  };
}

function upsertToolStep(steps, nextStep) {
  const nextSteps = [...steps];
  const index = nextSteps.findIndex((step) => step.id === nextStep.id);
  if (index === -1) {
    nextSteps.push(nextStep);
    return nextSteps;
  }
  nextSteps[index] = {
    ...nextSteps[index],
    ...nextStep,
  };
  return nextSteps;
}

function buildToolTraceStep(event) {
  const payload = event.payload ?? {};
  const normalized = normalizeAgentToolTraceStep({
    tool_name: payload.tool_name ?? event.payload?.tool_name,
    payload: payload.payload ?? payload,
  });
  return {
    id: typeof payload.tool_call_id === "string" ? payload.tool_call_id : `${payload.tool_name ?? "tool"}-${payload.index ?? 0}`,
    toolName: normalized.toolName,
    label: normalized.label,
    target: normalized.target,
    status: event.type === "tool_started" ? "running" : "completed",
    durationMs: typeof payload.duration_ms === "number" ? payload.duration_ms : null,
  };
}

function sumVisibleToolDurations(steps) {
  const durations = steps
    .map((step) => step.durationMs)
    .filter((durationMs) => typeof durationMs === "number" && durationMs >= 0);
  if (!durations.length) {
    return null;
  }
  return durations.reduce((total, durationMs) => total + durationMs, 0);
}

function appendStreamingAnswerDelta(messages, requestId, delta) {
  const currentContent = getMessageContent(messages, `assistant-${requestId}`);
  return buildStreamingAnswerMessage(
    requestId,
    `${currentContent}${typeof delta === "string" ? delta : ""}`,
    "running",
    null,
  );
}

function appendThinkingDelta(messages, requestId, delta) {
  const messageId = `thought-${requestId}`;
  const currentMessage = messages.find((message) => message.id === messageId);
  const currentSummary = currentMessage?.thoughtTrace?.summary ?? "";
  const nextSummary = `${currentSummary}${typeof delta === "string" ? delta : ""}`;
  return buildThinkingMessage(
    requestId,
    {
      summary: nextSummary,
      duration_ms: currentMessage?.thoughtTrace?.durationMs ?? null,
    },
    { status: "running" },
  );
}

function buildStreamingAnswerMessage(requestId, content, status, durationMs) {
  return {
    id: `assistant-${requestId}`,
    role: "assistant",
    content,
    streamingStatus: status,
    meta: status === "running"
      ? "Notebook Assistant • 输出中"
      : buildAssistantChatMeta(durationMs),
  };
}

function buildStatusMeta(label, durationMs) {
  const durationLabel = formatDurationLabel(durationMs);
  if (!durationLabel) {
    return `Notebook Assistant • ${label}完成`;
  }
  return `Notebook Assistant • ${label}用时 ${durationLabel}`;
}

export function useWorkspaceController() {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, createInitialWorkspaceState);

  useEffect(() => {
    let cancelled = false;

    loadWorkspaceLibrary()
      .then((library) => {
        if (!cancelled) {
          dispatch({ type: "workspace_loaded", library });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: "faster_whisper_models_loading_started" });
    loadFasterWhisperModels()
      .then((models) => {
        if (!cancelled) {
          dispatch({ type: "faster_whisper_models_loaded", models });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "语音模型列表加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    loadWorkspaceSettings()
      .then((settings) => {
        if (!cancelled) {
          dispatch({ type: "workspace_settings_loaded", settings });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "设置加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!state.settingsPanelOpen) {
      return;
    }

    let cancelled = false;
    loadProviderSettings()
      .then((settings) => {
        if (!cancelled) {
          dispatch({ type: "workspace_settings_loaded", settings: { ...state.ui, ...settings } });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "供应商设置加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.settingsPanelOpen]);

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    document.documentElement.classList.toggle("dark", state.ui.theme === "dark");
  }, [state.ui.theme]);

  useEffect(() => {
    if (!state.library || !state.chatScopeKey || !state.chatBaseScopeKey) {
      return;
    }
    const sessionId = state.chatScopeKey;
    if (hasRecoveredChatScope(state.chatRecoveryByScope, sessionId)) {
      return;
    }
    const context = buildAgentChatContextPayload(
      state.library,
      state.selectedContextType,
      state.selectedSeriesId,
      state.selectedVideoId,
      state.selectedToolId,
    );

    let cancelled = false;
    dispatch({ type: "chat_recovery_started" });
    loadAgentSessionRecovery(sessionId, context)
      .then((recovery) => {
        if (!cancelled) {
          dispatch({
            type: "chat_recovery_loaded",
            chatScopeKey: sessionId,
            restored: recovery.restored,
            messages: recovery.messages,
          });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "会话恢复失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    state.library,
    state.chatScopeKey,
    state.chatBaseScopeKey,
    state.selectedContextType,
    state.selectedSeriesId,
    state.selectedVideoId,
    state.selectedToolId,
    state.chatRecoveryByScope,
  ]);

  useEffect(() => {
    if (!state.library || !state.chatScopeKey || !state.chatBaseScopeKey) {
      return;
    }
    const sessionId = state.chatScopeKey;
    const context = buildAgentChatContextPayload(
      state.library,
      state.selectedContextType,
      state.selectedSeriesId,
      state.selectedVideoId,
      state.selectedToolId,
    );

    let cancelled = false;
    dispatch({ type: "context_usage_loading_started" });
    loadAgentContextUsage(sessionId, context)
      .then((usage) => {
        if (!cancelled) {
          dispatch({
            type: "context_usage_loaded",
            chatScopeKey: sessionId,
            currentScopeKey: state.chatScopeKey,
            usage,
          });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "上下文预算加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    state.library,
    state.chatScopeKey,
    state.chatBaseScopeKey,
    state.selectedContextType,
    state.selectedSeriesId,
    state.selectedVideoId,
    state.selectedToolId,
  ]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (!selectedVideo || state.selectedContextType !== "video") {
      dispatch({ type: "tools_loaded", tools: null });
      return;
    }

    let cancelled = false;
    dispatch({ type: "tools_loading_started" });
    loadVideoTools(state.selectedSeriesId, state.selectedVideoId)
      .then((tools) => {
        if (!cancelled) {
          dispatch({ type: "tools_loaded", tools });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (!selectedVideo || state.selectedContextType !== "video") {
      dispatch({ type: "summary_cleared" });
      return;
    }
    if (!state.tools?.overview.generated) {
      dispatch({ type: "summary_cleared" });
      return;
    }

    let cancelled = false;
    dispatch({ type: "summary_loading_started" });
    loadVideoSummary(state.selectedSeriesId, state.selectedVideoId)
      .then((summary) => {
        if (!cancelled) {
          dispatch({ type: "summary_loaded", summary });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType, state.tools?.overview.generated]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (
      !selectedVideo ||
      state.selectedContextType !== "video" ||
      state.selectedToolId !== "mindmap" ||
      !state.tools?.mindmap.generated
    ) {
      dispatch({ type: "mindmap_cleared" });
      return;
    }

    let cancelled = false;
    dispatch({ type: "mindmap_loading_started" });
    loadVideoMindmap(state.selectedSeriesId, state.selectedVideoId)
      .then((mindmap) => {
        if (!cancelled) {
          dispatch({ type: "mindmap_loaded", mindmap });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType, state.selectedToolId, state.tools?.mindmap.generated]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (
      !selectedVideo ||
      state.selectedContextType !== "video" ||
      state.selectedToolId !== "knowledge-cards" ||
      !state.tools?.knowledgeCards.generated
    ) {
      dispatch({ type: "knowledge_cards_cleared" });
      return;
    }

    let cancelled = false;
    dispatch({ type: "knowledge_cards_loading_started" });
    loadVideoKnowledgeCards(state.selectedSeriesId, state.selectedVideoId)
      .then((cards) => {
        if (!cancelled) {
          dispatch({ type: "knowledge_cards_loaded", cards });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "知识卡片加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType, state.selectedToolId, state.tools?.knowledgeCards.generated]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (
      !selectedVideo ||
      state.selectedContextType !== "video" ||
      state.selectedToolId !== "notes"
    ) {
      dispatch({ type: "notes_cleared" });
      return;
    }

    let cancelled = false;
    dispatch({ type: "notes_loading_started" });
    loadVideoNotes(state.selectedSeriesId, state.selectedVideoId)
      .then((notes) => {
        if (!cancelled) {
          dispatch({ type: "notes_loaded", notes });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "笔记加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType, state.selectedToolId]);

  const summary = state.summary;
  const mindmap = state.mindmap;
  const tools = state.tools;
  const activeSeries = findSeriesById(state.library, state.selectedSeriesId);
  const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
  const selectedNode = useMemo(
    () => findNodeById(mindmap, state.selectedNodeId),
    [mindmap, state.selectedNodeId],
  );
  const isGeneratingSelectedVideo =
    state.generatingVideoKey != null &&
    state.generatingVideoKey === buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
  const isGeneratingMindmapSelectedVideo =
    state.generatingMindmapKey != null &&
    state.generatingMindmapKey === buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
  const previewUrl = state.selectedSeriesId && state.selectedVideoId
    ? getVideoPreviewUrl(state.selectedSeriesId, state.selectedVideoId)
    : null;

  function onSelectSeries(seriesId) {
    dispatch({ type: "series_selected", seriesId });
  }

  function onEnterLibraryHome() {
    dispatch({ type: "workspace_loaded", library: state.library });
  }

  function onSelectVideo(seriesId, videoId) {
    dispatch({ type: "video_selected", seriesId, videoId });
  }

  function onSelectSeriesContext() {
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

  async function onGenerateKnowledgeCards() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    dispatch({ type: "knowledge_cards_generation_started" });
    try {
      const cards = await generateVideoKnowledgeCards(state.selectedSeriesId, state.selectedVideoId);
      dispatch({
        type: "knowledge_cards_loaded",
        cards,
        feedbackTone: "success",
        feedbackMessage:
          Array.isArray(cards?.cards) && cards.cards.length
            ? `已生成 ${cards.cards.length} 张知识卡片`
            : "知识卡片已生成，但这次没有抽取出稳定卡片",
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "知识卡片生成失败",
      });
    }
  }

  function onToggleSettingsPanel() {
    dispatch({ type: "settings_panel_toggled" });
  }

  function onCloseSettingsPanel() {
    dispatch({ type: "settings_panel_closed" });
  }

  async function onChangeSetting(key, value) {
    const nextUi = normalizeUiSettings({
      ...state.ui,
      [key]: value,
    });
    dispatch({ type: "workspace_settings_loaded", settings: nextUi });

    try {
      if (key === "llmProvider" || key === "openaiBaseUrl" || key === "openaiModel" || key === "openaiApiKey") {
        const savedProviderSettings = await updateProviderSettings(nextUi);
        dispatch({
          type: "workspace_settings_loaded",
          settings: {
            ...nextUi,
            ...savedProviderSettings,
            openaiApiKey: "",
          },
        });
      } else {
        const savedSettings = await updateWorkspaceSettings(nextUi);
        dispatch({
          type: "workspace_settings_loaded",
          settings: {
            ...state.ui,
            ...savedSettings,
          },
        });
        const models = await loadFasterWhisperModels();
        dispatch({ type: "faster_whisper_models_loaded", models });
      }
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "设置保存失败",
      });
    }
  }

  async function onResetSettings() {
    const nextUi = normalizeUiSettings({
      ...state.ui,
      ...resetUiSettings(),
      llmProvider: state.ui.llmProvider,
      openaiBaseUrl: state.ui.openaiBaseUrl,
      openaiModel: state.ui.openaiModel,
      hasOpenaiApiKey: state.ui.hasOpenaiApiKey,
      openaiApiKeyMasked: state.ui.openaiApiKeyMasked,
      openaiApiKey: "",
    });
    dispatch({ type: "workspace_settings_loaded", settings: nextUi });

    try {
      const savedSettings = await updateWorkspaceSettings(nextUi);
      dispatch({
        type: "workspace_settings_loaded",
        settings: {
          ...nextUi,
          ...savedSettings,
        },
      });
      const models = await loadFasterWhisperModels();
      dispatch({ type: "faster_whisper_models_loaded", models });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "设置保存失败",
      });
    }
  }

  async function onDownloadFasterWhisperModel(modelId) {
    dispatch({ type: "faster_whisper_model_download_started", modelId });
    const unsubscribe = subscribeFasterWhisperModelDownloadProgress(modelId, (snapshot) => {
      if (snapshot.status === "running" || snapshot.status === "completed") {
        dispatch({
          type: "faster_whisper_model_download_progress_updated",
          modelId,
          progress: snapshot.progress,
        });
      }

      if (snapshot.status === "failed") {
        dispatch({
          type: "load_failed",
          message: snapshot.error ?? "语音模型下载失败",
        });
      }
      if (snapshot.status === "cancelled") {
        dispatch({ type: "faster_whisper_model_download_cancelled" });
      }
    });
    try {
      await downloadFasterWhisperModel(modelId);
      const savedSettings = await updateWorkspaceSettings({
        ...state.ui,
        asrModelQuality: modelId,
      });
      dispatch({ type: "workspace_settings_loaded", settings: savedSettings });
      const models = await loadFasterWhisperModels();
      dispatch({ type: "faster_whisper_models_loaded", models });
    } catch (error) {
      if (error instanceof Error && error.message.includes("409")) {
        dispatch({ type: "faster_whisper_model_download_cancelled" });
        return;
      }
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "语音模型下载失败",
      });
    } finally {
      unsubscribe();
    }
  }

  async function onCancelFasterWhisperModelDownload(modelId) {
    try {
      await cancelFasterWhisperModelDownload(modelId);
      dispatch({ type: "faster_whisper_model_download_cancelled" });
      const models = await loadFasterWhisperModels();
      dispatch({ type: "faster_whisper_models_loaded", models });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "取消语音模型下载失败",
      });
    }
  }

  async function onGenerateVideo() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    const seriesId = state.selectedSeriesId;
    const videoId = state.selectedVideoId;
    const videoKey = buildVideoKey(seriesId, videoId);
    dispatch({ type: "generation_started", videoKey });

    const unsubscribe = subscribeVideoGenerationProgress(seriesId, videoId, (snapshot) => {
      if (snapshot.status === "running" || snapshot.status === "completed") {
        dispatch({
          type: "generation_progress_updated",
          progress: snapshot.progress,
          snapshot,
        });
      }

      if (snapshot.status === "failed") {
        dispatch({
          type: "load_failed",
          message: snapshot.error ?? "生成失败",
        });
      }
    });

    try {
      const summaryResult = await generateVideoSummary(seriesId, videoId, {
        transcriptEnhancementEnabled: state.ui.transcriptEnhancementEnabled,
      });
      dispatch({
        type: "generation_succeeded",
        seriesId,
        videoId,
        summary: summaryResult,
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "生成失败",
      });
    } finally {
      unsubscribe();
    }
  }

  async function onGenerateMindmap() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    const videoKey = buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
    dispatch({ type: "mindmap_generation_started", videoKey });
    try {
      const mindmapResult = await generateVideoMindmap(state.selectedSeriesId, state.selectedVideoId);
      dispatch({
        type: "mindmap_generation_succeeded",
        mindmap: mindmapResult,
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "生成失败",
      });
    }
  }

  async function onCreateNote(note) {
    if (!state.selectedSeriesId || !state.selectedVideoId || !selectedVideo) {
      return;
    }

    dispatch({ type: "note_save_started" });
    try {
      const createdNote = await createVideoNote(state.selectedSeriesId, state.selectedVideoId, {
        title: note.title,
        content: note.content,
        source: note.source ?? "manual",
      });
      dispatch({
        type: "note_created",
        seriesId: state.selectedSeriesId,
        videoId: state.selectedVideoId,
        videoTitle: selectedVideo.title,
        note: createdNote,
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "笔记保存失败",
      });
    }
  }

  async function onUpdateNote(noteId, note) {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    dispatch({ type: "note_save_started" });
    try {
      const updatedNote = await updateVideoNote(state.selectedSeriesId, state.selectedVideoId, noteId, {
        title: note.title,
        content: note.content,
      });
      dispatch({ type: "note_updated", note: updatedNote });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "笔记更新失败",
      });
    }
  }

  async function onDeleteNote(noteId) {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    dispatch({ type: "note_save_started" });
    try {
      await deleteVideoNote(state.selectedSeriesId, state.selectedVideoId, noteId);
      dispatch({ type: "note_deleted", noteId });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "笔记删除失败",
      });
    }
  }

  async function onSubmitChat(message) {
    const trimmedMessage = message.trim();
    if (!trimmedMessage || state.chatPending) {
      return;
    }

    const sessionId = state.chatScopeKey;
    if (!sessionId) {
      throw new Error("当前未处于 series 或 video 上下文，无法发起 AI 对话。");
    }
    const context = buildAgentChatContextPayload(
      state.library,
      state.selectedContextType,
      state.selectedSeriesId,
      state.selectedVideoId,
      state.selectedToolId,
    );

    const requestId = Date.now();

    dispatch({
      type: "chat_request_started",
      chatScopeKey: sessionId,
      userMessageId: `user-${requestId}`,
      message: trimmedMessage,
    });

    try {
      await streamAgentChat(sessionId, trimmedMessage, context, async (event) => {
        dispatch({
          type: "chat_stream_event_received",
          chatScopeKey: sessionId,
          requestId,
          event,
        });

        await applyAgentStreamSideEffects(event);
      });
      const usage = await loadAgentContextUsage(sessionId, context);
      dispatch({
        type: "context_usage_loaded",
        chatScopeKey: sessionId,
        currentScopeKey: state.chatScopeKey,
        usage,
      });
    } catch (error) {
      dispatch({ type: "chat_pending_cleared" });
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "AI 对话失败",
      });
    }
  }

  function onStartNewChat() {
    const chatBaseScopeKey = state.chatBaseScopeKey;
    if (!chatBaseScopeKey) {
      throw new Error("当前未处于 series 或 video 上下文，无法新建对话。");
    }
    const sessionId = `${chatBaseScopeKey}::${Date.now()}`;
    dispatch({
      type: "chat_session_started",
      chatBaseScopeKey,
      sessionId,
    });
  }

  async function onClearChat() {
    const sessionId = state.chatScopeKey;
    if (!sessionId) {
      throw new Error("当前未处于 series 或 video 上下文，无法清空对话。");
    }
    const context = buildAgentChatContextPayload(
      state.library,
      state.selectedContextType,
      state.selectedSeriesId,
      state.selectedVideoId,
      state.selectedToolId,
    );
    try {
      await clearAgentSession(sessionId, context);
      dispatch({
        type: "chat_session_cleared",
        sessionId,
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "清空对话失败",
      });
    }
  }

  async function applyAgentStreamSideEffects(event) {
    if (event?.type !== "tool_completed") {
      return;
    }

    const payload = event.payload?.payload ?? {};

    if (payload.selected_tool) {
      const nextToolId = normalizeAgentToolId(payload.selected_tool);
      if (nextToolId) {
        dispatch({ type: "tool_selected", toolId: nextToolId });
      }
    }

    if (typeof payload.seek_seconds === "number") {
      dispatch({
        type: "preview_seek_requested",
        seconds: payload.seek_seconds,
        endSeconds: typeof payload.match_end_seconds === "number" ? payload.match_end_seconds : null,
        query: typeof payload.query === "string" ? payload.query : "",
        matchedText: typeof payload.matched_text === "string" ? payload.matched_text : "",
        chapterTitle: typeof payload.chapter_title === "string" ? payload.chapter_title : "",
        requestId: `${Date.now()}-${payload.seek_seconds}`,
      });
    }

    if (payload.action === "generate_overview") {
      void onGenerateVideo();
    }

    if (payload.action === "generate_mindmap") {
      void onGenerateMindmap();
    }

    if (
      payload.action === "save_note" &&
      typeof payload.note_title === "string" &&
      typeof payload.note_content === "string"
    ) {
      await onCreateNote({
        title: payload.note_title,
        content: payload.note_content,
        source: typeof payload.note_source === "string" ? payload.note_source : "agent",
      });
    }
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
    chatPending: state.chatPending,
    chatRecoveryLoading: state.chatRecoveryLoading,
    contextUsage: state.contextUsage,
    contextUsageLoading: state.contextUsageLoading,
    isGeneratingMindmapSelectedVideo,
    isGeneratingSelectedVideo,
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
    onSubmitChat,
    onStartNewChat,
    onClearChat,
    onGenerateVideo,
    onGenerateMindmap,
    onGenerateKnowledgeCards,
    onCreateNote,
    onUpdateNote,
    onDeleteNote,
    onToggleSettingsPanel,
    onCloseSettingsPanel,
    onChangeSetting,
    onDownloadFasterWhisperModel,
    onCancelFasterWhisperModelDownload,
    onResetSettings,
  };
}

function buildVideoKey(seriesId, videoId) {
  if (!seriesId || !videoId) {
    return null;
  }
  return `${seriesId}/${videoId}`;
}

function buildAgentChatContextPayload(library, selectedContextType, seriesId, videoId, selectedToolId) {
  if (selectedContextType !== "series" && selectedContextType !== "video") {
    throw new Error("Agent 对话上下文必须是 series 或 video。");
  }
  const activeSeries = findSeriesById(library, seriesId);
  const selectedVideo = findVideoById(library, seriesId, videoId);
  return {
    scope_type: selectedContextType,
    series_id: activeSeries?.id ?? null,
    series_title: activeSeries?.title ?? null,
    video_id: selectedVideo?.id ?? null,
    video_title: selectedVideo?.title ?? null,
    selected_tool: selectedToolId ?? null,
  };
}

function normalizeAgentToolId(toolId) {
  if (toolId === "video") {
    return "preview";
  }
  if (
    toolId === "series-overview" ||
    toolId === "overview" ||
    toolId === "cards" ||
    toolId === "knowledge-cards" ||
    toolId === "mindmap" ||
    toolId === "notes" ||
    toolId === "preview" ||
    toolId === "series-home"
  ) {
    return toolId;
  }
  return null;
}

function normalizeAgentToolTraceStep(result) {
  const payload = result?.payload ?? {};
  switch (result?.tool_name) {
    case "list_series_videos":
      return createToolTraceStep(result.tool_name, "读取系列视频列表", payload.series_title ?? payload.series_id);
    case "open_series_overview":
      return createToolTraceStep(result.tool_name, "打开系列概览");
    case "get_video_summary":
      return createToolTraceStep(result.tool_name, "读取视频概况", payload.title ?? payload.video_id);
    case "get_video_tools":
      return createToolTraceStep(result.tool_name, "读取视频工具状态", payload.video_id);
    case "open_series_home":
      return createToolTraceStep(result.tool_name, "打开系列首页");
    case "open_overview":
      return createToolTraceStep(result.tool_name, "打开 AI 概况");
    case "open_mindmap":
      return createToolTraceStep(result.tool_name, "打开思维导图");
    case "open_knowledge_cards":
      return createToolTraceStep(result.tool_name, "打开知识卡片");
    case "open_notes":
      return createToolTraceStep(result.tool_name, "打开笔记");
    case "open_video":
      return createToolTraceStep(result.tool_name, "打开视频预览");
    case "video_seek":
      return createToolTraceStep(
        result.tool_name,
        typeof payload.seek_seconds === "number" ? `跳转视频到 ${formatSeconds(payload.seek_seconds)}` : "跳转视频",
      );
    case "generate_overview":
      return createToolTraceStep(result.tool_name, "生成 AI 概况");
    case "generate_mindmap":
      return createToolTraceStep(result.tool_name, "生成思维导图");
    case "save_note":
      return createToolTraceStep(result.tool_name, "保存笔记", payload.note_title);
    case "get_video_transcript":
      return createToolTraceStep(result.tool_name, "读取视频转写全文", payload.title ?? payload.video_id);
    default:
      return createToolTraceStep(result?.tool_name ?? "unknown_tool", "执行工作流步骤");
  }
}

function createToolTraceStep(toolName, label, target = "") {
  return {
    toolName,
    label,
    target: normalizeToolTarget(target),
  };
}

function normalizeToolTarget(value) {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  return value.trim();
}

function formatSeconds(seconds) {
  const totalSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
}

function buildAssistantChatMeta(durationMs) {
  const durationLabel = formatDurationLabel(durationMs);
  if (!durationLabel) {
    return "Notebook Assistant • Just now";
  }
  return `Notebook Assistant • 用时 ${durationLabel}`;
}

function formatDurationLabel(durationMs) {
  if (typeof durationMs !== "number" || Number.isNaN(durationMs) || durationMs < 0) {
    return "";
  }
  if (durationMs < 1000) {
    return `${durationMs}ms`;
  }
  return `${(durationMs / 1000).toFixed(1)}秒`;
}
