export const defaultUiSettings = {
  showTakeaways: true,
  theme: "light",
  transcriptEnhancementEnabled: true,
  asrModelQuality: "large-v3-turbo",
  transcriptionMode: "fast",
  llmProvider: "openai_compatible",
  openaiBaseUrl: "http://127.0.0.1:8317/v1",
  openaiModel: "gpt-5.4",
  openaiApiKey: "",
  hasOpenaiApiKey: false,
  openaiApiKeyMasked: "",
};

export function createWelcomeChatMessages() {
  return [
    {
      id: "assistant-welcome",
      role: "assistant",
      content:
        "你好！我已经准备好当前知识库。你可以问我视频在讲什么、某个知识点在哪个时间点，或者让我打开概况、导图和视频工具。",
      meta: "Notebook Assistant • Just now",
    },
  ];
}

export function buildChatScopeKey(selectedContextType, seriesId, videoId, selectedToolId) {
  if (selectedContextType === "series") {
    return `series|${seriesId ?? ""}|${selectedToolId ?? "series-home"}`;
  }
  if (selectedContextType === "video") {
    return `video|${seriesId ?? ""}|${videoId ?? ""}|${selectedToolId ?? "studio"}`;
  }
  return null;
}

const CHAT_SESSION_STORAGE_KEY = "video-include.chat-sessions";

export function loadChatSessionIdsByScope() {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const rawValue = window.localStorage.getItem(CHAT_SESSION_STORAGE_KEY);
    if (!rawValue) {
      return {};
    }
    const parsed = JSON.parse(rawValue);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function persistChatSessionIdsByScope(chatSessionIdsByScope) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(CHAT_SESSION_STORAGE_KEY, JSON.stringify(chatSessionIdsByScope ?? {}));
}

export function getChatSessionIdForScope(chatSessionIdsByScope, scopeKey) {
  if (!scopeKey) {
    return null;
  }
  return chatSessionIdsByScope?.[scopeKey] ?? scopeKey;
}

export function setChatSessionIdForScope(chatSessionIdsByScope, scopeKey, sessionId) {
  if (!scopeKey || !sessionId) {
    return { ...(chatSessionIdsByScope ?? {}) };
  }
  return {
    ...(chatSessionIdsByScope ?? {}),
    [scopeKey]: sessionId,
  };
}

export function getChatMessagesForScope(chatThreads, scopeKey) {
  if (!scopeKey) {
    return [];
  }
  return chatThreads?.[scopeKey] ? [...chatThreads[scopeKey]] : createWelcomeChatMessages();
}

export function getContextUsageForScope(contextUsageByScope, scopeKey) {
  if (!scopeKey) {
    return null;
  }
  return contextUsageByScope?.[scopeKey] ?? null;
}

export function setChatMessagesForScope(chatThreads, scopeKey, messages) {
  if (!scopeKey) {
    return { ...(chatThreads ?? {}) };
  }
  return {
    ...(chatThreads ?? {}),
    [scopeKey]: [...messages],
  };
}

export function setContextUsageForScope(contextUsageByScope, scopeKey, usage) {
  if (!scopeKey) {
    return { ...(contextUsageByScope ?? {}) };
  }
  return {
    ...(contextUsageByScope ?? {}),
    [scopeKey]: usage,
  };
}

export function hasRecoveredChatScope(chatRecoveryByScope, scopeKey) {
  if (!scopeKey) {
    return false;
  }
  return Boolean(chatRecoveryByScope?.[scopeKey]);
}

export function setRecoveredChatScope(chatRecoveryByScope, scopeKey, recovered) {
  if (!scopeKey) {
    return { ...(chatRecoveryByScope ?? {}) };
  }
  return {
    ...(chatRecoveryByScope ?? {}),
    [scopeKey]: recovered,
  };
}

export function createInitialWorkspaceState() {
  const chatSessionIdsByScope = loadChatSessionIdsByScope();
  return {
    library: null,
    tools: null,
    summary: null,
    mindmap: null,
    knowledgeCards: null,
    notes: null,
    selectedSeriesId: null,
    selectedVideoId: null,
    selectedContextType: null,
    selectedToolId: "studio",
    selectedChapterId: null,
    selectedNodeId: null,
    previewSeekRequest: null,
    generatingVideoKey: null,
    generatingMindmapKey: null,
    generationProgress: null,
    generationSnapshot: null,
    downloadingModelId: null,
    modelDownloadProgress: null,
    toolsLoading: false,
    summaryLoading: false,
    mindmapLoading: false,
    knowledgeCardsLoading: false,
    knowledgeCardsGenerating: false,
    knowledgeCardsFeedback: null,
    notesLoading: false,
    savingNote: false,
    fasterWhisperModels: [],
    fasterWhisperModelsLoading: false,
    ui: resetUiSettings(),
    chatThreads: {},
    chatRecoveryByScope: {},
    chatScopeKey: null,
    chatBaseScopeKey: null,
    chatSessionIdsByScope,
    chatMessages: [],
    chatPending: false,
    chatRecoveryLoading: false,
    contextUsageByScope: {},
    contextUsage: null,
    contextUsageLoading: false,
    settingsPanelOpen: false,
    error: "",
    loading: true,
  };
}

export function createWorkspaceLoadedState(library, currentState) {
  const selection = getDefaultSelection(library, currentState.selectedSeriesId, currentState.selectedVideoId);
  if (!selection.seriesId) {
    return {
      ...currentState,
      library,
      tools: null,
      summary: null,
      mindmap: null,
      knowledgeCards: null,
      knowledgeCardsFeedback: null,
      notes: null,
      selectedSeriesId: null,
      selectedVideoId: null,
      selectedContextType: null,
      selectedToolId: "studio",
      selectedChapterId: null,
      selectedNodeId: null,
      previewSeekRequest: null,
      toolsLoading: false,
      summaryLoading: false,
      mindmapLoading: false,
      generationProgress: null,
      generationSnapshot: null,
      chatScopeKey: null,
      chatBaseScopeKey: null,
      chatMessages: [],
      chatPending: false,
      chatRecoveryLoading: false,
      contextUsage: null,
      contextUsageLoading: false,
      error: "",
      loading: false,
    };
  }
  return {
    ...currentState,
    library,
    selectedSeriesId: selection.seriesId,
    selectedVideoId: selection.videoId,
    selectedContextType: currentState.selectedContextType,
    error: "",
    loading: false,
  };
}

export function createSummaryLoadedState(summary, currentState) {
  return {
    ...currentState,
    summary,
    summaryLoading: false,
    selectedChapterId: summary?.chapters?.[0]?.id ?? null,
  };
}

export function createMindmapLoadedState(mindmap, currentState) {
  return {
    ...currentState,
    mindmap,
    mindmapLoading: false,
    selectedNodeId: mindmap?.children?.[0]?.id ?? mindmap?.id ?? null,
  };
}

export function getDefaultSelection(library, preferredSeriesId = null, preferredVideoId = null) {
  const series = library?.series ?? [];
  if (!series.length) {
    return { seriesId: null, videoId: null };
  }

  if (!preferredSeriesId) {
    return { seriesId: null, videoId: null };
  }

  const preferredSeries = series.find((item) => item.id === preferredSeriesId);
  if (!preferredSeries) {
    return { seriesId: null, videoId: null };
  }

  const preferredVideo =
    preferredSeries.videos.find((item) => item.id === preferredVideoId) ?? preferredSeries.videos[0] ?? null;

  return {
    seriesId: preferredSeries.id,
    videoId: preferredVideo?.id ?? null,
  };
}

export function findSeriesById(library, seriesId) {
  return library?.series?.find((series) => series.id === seriesId) ?? null;
}

export function findVideoById(library, seriesId, videoId) {
  return findSeriesById(library, seriesId)?.videos.find((video) => video.id === videoId) ?? null;
}

export function markVideoAsReady(library, seriesId, videoId) {
  if (!library) {
    return library;
  }

  return {
    ...library,
    series: library.series.map((series) =>
      series.id !== seriesId
        ? series
        : {
            ...series,
            videos: series.videos.map((video) =>
              video.id !== videoId
                ? video
                : {
                    ...video,
                    processed: true,
                    status: "ready",
                  },
            ),
          },
    ),
  };
}

export function resetUiSettings() {
  return { ...defaultUiSettings };
}

export function normalizeUiSettings(value) {
  const record = value && typeof value === "object" ? value : {};
  return {
    showTakeaways: typeof record.showTakeaways === "boolean" ? record.showTakeaways : true,
    theme: record.theme === "dark" ? "dark" : "light",
    transcriptEnhancementEnabled:
      typeof record.transcriptEnhancementEnabled === "boolean" ? record.transcriptEnhancementEnabled : true,
    asrModelQuality:
      typeof record.asrModelQuality === "string" && record.asrModelQuality.trim()
        ? record.asrModelQuality.trim()
        : "large-v3-turbo",
    transcriptionMode:
      record.transcriptionMode === "accurate" || record.transcriptionMode === "balanced"
        ? record.transcriptionMode
        : "fast",
    llmProvider: record.llmProvider === "openai_compatible" ? record.llmProvider : "openai_compatible",
    openaiBaseUrl:
      typeof record.openaiBaseUrl === "string" && record.openaiBaseUrl.trim()
        ? record.openaiBaseUrl.trim()
        : "http://127.0.0.1:8317/v1",
    openaiModel:
      typeof record.openaiModel === "string" && record.openaiModel.trim()
        ? record.openaiModel.trim()
        : "gpt-5.4",
    openaiApiKey: typeof record.openaiApiKey === "string" ? record.openaiApiKey : "",
    hasOpenaiApiKey: typeof record.hasOpenaiApiKey === "boolean" ? record.hasOpenaiApiKey : false,
    openaiApiKeyMasked: typeof record.openaiApiKeyMasked === "string" ? record.openaiApiKeyMasked : "",
  };
}
