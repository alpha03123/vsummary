export const defaultUiSettings = {
  showTakeaways: true,
  theme: "light",
  transcriptEnhancementEnabled: true,
  asrModelQuality: "large-v3-turbo",
  transcriptionMode: "fast",
  ragEmbeddingDevice: "cpu",
  ragMaxHits: 5,
  ragRerankEnabled: true,
  webSearchEnabled: false,
  llmProvider: "openai_compatible",
  openaiBaseUrl: "http://127.0.0.1:8317/v1",
  openaiModel: "gpt-5.4",
  hfEndpoint: "https://hf-mirror.com",
  openaiApiKey: "",
  hasOpenaiApiKey: false,
  openaiApiKeyMasked: "",
  windowTokens: 1000000,
  answerDetailLevel: "medium",
  videoGenerationConcurrency: 1,
};

export function createWelcomeChatMessages() {
  return [
    {
      id: "assistant-welcome",
      role: "assistant",
      content:
        "你好！你可以询问视频有关内容，也可以让我替你记录笔记",
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

export function buildVideoGenerationTaskKey(seriesId, videoId) {
  if (!seriesId || !videoId) {
    return null;
  }
  return `video:${seriesId}/${videoId}`;
}

export function buildSeriesGenerationTaskKey(seriesId) {
  if (!seriesId) {
    return null;
  }
  return `series:${seriesId}`;
}

export function createGenerationTaskRecord({
  taskKey,
  mode,
  seriesId,
  videoId = null,
  snapshot,
  subscriptionActive = false,
}) {
  if (!taskKey) {
    return null;
  }
  return {
    taskKey,
    mode,
    seriesId,
    videoId,
    snapshot,
    subscriptionActive,
  };
}

export function setGenerationTaskForKey(generationTasksByKey, task) {
  if (!task?.taskKey) {
    return { ...(generationTasksByKey ?? {}) };
  }
  return {
    ...(generationTasksByKey ?? {}),
    [task.taskKey]: task,
  };
}

export function getGenerationTaskForKey(generationTasksByKey, taskKey) {
  if (!taskKey) {
    return null;
  }
  return generationTasksByKey?.[taskKey] ?? null;
}

export function getGenerationTaskForSelection(state) {
  if (state?.selectedContextType === "video") {
    return getGenerationTaskForKey(
      state.generationTasksByKey,
      buildVideoGenerationTaskKey(state.selectedSeriesId, state.selectedVideoId),
    );
  }
  if (state?.selectedContextType === "series") {
    return getGenerationTaskForKey(
      state.generationTasksByKey,
      buildSeriesGenerationTaskKey(state.selectedSeriesId),
    );
  }
  return null;
}

export function isGenerationSnapshotActive(snapshot) {
  const status = snapshot?.status;
  return status === "running" || status === "queued" || status === "cancelling";
}

const CHAT_SESSION_STORAGE_KEY = "video-include.chat-sessions";
const DEFAULT_CHAT_SESSION_TITLE = "当前对话";
const NEW_CHAT_SESSION_TITLE_PREFIX = "新对话";

function createChatSessionMeta(sessionId, title, createdAt = Date.now(), updatedAt = createdAt) {
  return {
    id: sessionId,
    title,
    createdAt,
    updatedAt,
  };
}

function normalizeChatSessionMeta(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const id = typeof value.id === "string" && value.id.trim() ? value.id.trim() : "";
  if (!id) {
    return null;
  }
  const title = typeof value.title === "string" && value.title.trim() ? value.title.trim() : DEFAULT_CHAT_SESSION_TITLE;
  const createdAt = typeof value.createdAt === "number" && Number.isFinite(value.createdAt) ? value.createdAt : Date.now();
  const updatedAt = typeof value.updatedAt === "number" && Number.isFinite(value.updatedAt) ? value.updatedAt : createdAt;
  return createChatSessionMeta(id, title, createdAt, updatedAt);
}

function loadChatSessionsState() {
  if (typeof window === "undefined") {
    return {
      activeSessionIdsByScope: {},
      sessionListsByScope: {},
    };
  }
  try {
    const rawValue = window.localStorage.getItem(CHAT_SESSION_STORAGE_KEY);
    if (!rawValue) {
      return {
        activeSessionIdsByScope: {},
        sessionListsByScope: {},
      };
    }
    const parsed = JSON.parse(rawValue);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {
        activeSessionIdsByScope: {},
        sessionListsByScope: {},
      };
    }

    const record = parsed;
    const hasNewShape =
      record.activeSessionIdsByScope &&
      typeof record.activeSessionIdsByScope === "object" &&
      !Array.isArray(record.activeSessionIdsByScope);

    if (!hasNewShape) {
      const activeSessionIdsByScope = Object.fromEntries(
        Object.entries(record).filter(([, value]) => typeof value === "string" && value.trim()),
      );
      return {
        activeSessionIdsByScope,
        sessionListsByScope: {},
      };
    }

    const activeSessionIdsByScope = Object.fromEntries(
      Object.entries(record.activeSessionIdsByScope ?? {}).filter(([, value]) => typeof value === "string" && value.trim()),
    );
    const sessionListsByScope = Object.fromEntries(
      Object.entries(record.sessionListsByScope ?? {}).map(([scopeKey, value]) => {
        const list = Array.isArray(value)
          ? value.map(normalizeChatSessionMeta).filter(Boolean)
          : [];
        return [scopeKey, list];
      }),
    );
    return {
      activeSessionIdsByScope,
      sessionListsByScope,
    };
  } catch {
    return {
      activeSessionIdsByScope: {},
      sessionListsByScope: {},
    };
  }
}

export function loadChatSessionIdsByScope() {
  return loadChatSessionsState().activeSessionIdsByScope;
}

export function loadChatSessionListsByScope() {
  return loadChatSessionsState().sessionListsByScope;
}

export function persistChatSessionIdsByScope(chatSessionIdsByScope, chatSessionListsByScope = {}) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(
    CHAT_SESSION_STORAGE_KEY,
    JSON.stringify({
      activeSessionIdsByScope: chatSessionIdsByScope ?? {},
      sessionListsByScope: chatSessionListsByScope ?? {},
    }),
  );
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

export function getChatSessionListForScope(chatSessionListsByScope, scopeKey) {
  if (!scopeKey) {
    return [];
  }
  return Array.isArray(chatSessionListsByScope?.[scopeKey]) ? [...chatSessionListsByScope[scopeKey]] : [];
}

export function resolveChatSessionsForScope(chatSessionIdsByScope, chatSessionListsByScope, scopeKey) {
  if (!scopeKey) {
    return {
      chatSessionIdsByScope: { ...(chatSessionIdsByScope ?? {}) },
      chatSessionListsByScope: { ...(chatSessionListsByScope ?? {}) },
      activeSessionId: null,
      sessions: [],
    };
  }
  const nextIds = { ...(chatSessionIdsByScope ?? {}) };
  const nextLists = { ...(chatSessionListsByScope ?? {}) };
  const existingList = getChatSessionListForScope(nextLists, scopeKey);
  let sessions = existingList;
  if (!sessions.length) {
    const legacySessionId = typeof nextIds[scopeKey] === "string" && nextIds[scopeKey].trim()
      ? nextIds[scopeKey].trim()
      : scopeKey;
    sessions = [createChatSessionMeta(legacySessionId, DEFAULT_CHAT_SESSION_TITLE)];
    nextLists[scopeKey] = sessions;
  }
  const candidateActiveId = typeof nextIds[scopeKey] === "string" && nextIds[scopeKey].trim()
    ? nextIds[scopeKey].trim()
    : null;
  const activeSessionId = sessions.some((session) => session.id === candidateActiveId)
    ? candidateActiveId
    : sessions[0].id;
  nextIds[scopeKey] = activeSessionId;
  return {
    chatSessionIdsByScope: nextIds,
    chatSessionListsByScope: nextLists,
    activeSessionId,
    sessions,
  };
}

export function createNextChatSessionMeta(chatSessionListsByScope, scopeKey, sessionId) {
  const existingSessions = getChatSessionListForScope(chatSessionListsByScope, scopeKey);
  const title = `${NEW_CHAT_SESSION_TITLE_PREFIX} ${existingSessions.length + 1}`;
  return createChatSessionMeta(sessionId, title);
}

export function appendChatSessionForScope(chatSessionListsByScope, scopeKey, sessionMeta) {
  if (!scopeKey || !sessionMeta) {
    return { ...(chatSessionListsByScope ?? {}) };
  }
  const nextLists = { ...(chatSessionListsByScope ?? {}) };
  const existingSessions = getChatSessionListForScope(nextLists, scopeKey);
  nextLists[scopeKey] = [sessionMeta, ...existingSessions];
  return nextLists;
}

export function removeChatSessionForScope(chatSessionListsByScope, scopeKey, sessionId) {
  if (!scopeKey || !sessionId) {
    return { ...(chatSessionListsByScope ?? {}) };
  }
  const nextLists = { ...(chatSessionListsByScope ?? {}) };
  const existingSessions = getChatSessionListForScope(nextLists, scopeKey);
  nextLists[scopeKey] = existingSessions.filter((session) => session.id !== sessionId);
  return nextLists;
}

export function updateChatSessionMetaForScope(chatSessionListsByScope, scopeKey, sessionId, update) {
  if (!scopeKey || !sessionId) {
    return { ...(chatSessionListsByScope ?? {}) };
  }
  const nextLists = { ...(chatSessionListsByScope ?? {}) };
  const existingSessions = getChatSessionListForScope(nextLists, scopeKey);
  nextLists[scopeKey] = existingSessions.map((session) =>
    session.id !== sessionId
      ? session
      : {
          ...session,
          ...update,
        },
  );
  return nextLists;
}

export function getChatSessionMetaForScope(chatSessionListsByScope, scopeKey, sessionId) {
  return getChatSessionListForScope(chatSessionListsByScope, scopeKey).find((session) => session.id === sessionId) ?? null;
}

export function buildChatSessionTitleFromMessage(message) {
  if (typeof message !== "string") {
    return DEFAULT_CHAT_SESSION_TITLE;
  }
  const normalized = message.trim().replace(/\s+/g, " ");
  if (!normalized) {
    return DEFAULT_CHAT_SESSION_TITLE;
  }
  return normalized.length > 18 ? `${normalized.slice(0, 18)}...` : normalized;
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

export function removeScopedValue(scopeValues, scopeKey) {
  if (!scopeKey) {
    return { ...(scopeValues ?? {}) };
  }
  const nextValues = { ...(scopeValues ?? {}) };
  delete nextValues[scopeKey];
  return nextValues;
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
  const chatSessionListsByScope = loadChatSessionListsByScope();
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
    generatingSeriesId: null,
    generationMode: null,
    generatingMindmapKey: null,
    seriesGenerationQueue: null,
    generationTasksByKey: {},
    generationProgress: null,
    generationSnapshot: null,
    downloadingVideoKey: null,
    videoDownloadProgress: null,
    downloadingModelId: null,
    modelDownloadStatus: null,
    modelDownloadProgress: null,
    modelDownloadErrorModelId: null,
    modelDownloadError: null,
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
    ragModels: [],
    ragModelsLoading: false,
    downloadingRagModelKey: null,
    ui: resetUiSettings(),
    chatThreads: {},
    chatRecoveryByScope: {},
    chatScopeKey: null,
    chatBaseScopeKey: null,
    chatSessionIdsByScope,
    chatSessionListsByScope,
    chatMessages: [],
    chatPending: false,
    chatRecoveryLoading: false,
    contextUsageByScope: {},
    contextUsage: null,
    contextUsageLoading: false,
    knowledgeMemorySnapshot: null,
    settingsPanelOpen: false,
    settingsPanelInitialTab: "general",
    backendReady: false,
    error: "",
    loading: true,
  };
}

export function createWorkspaceLoadedState(library, currentState) {
  const selection = getDefaultSelection(library, currentState.selectedSeriesId, currentState.selectedVideoId);
  if (!selection.seriesId) {
    return createLibraryHomeState(library, currentState);
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

export function createLibraryHomeState(library, currentState) {
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
    ragEmbeddingDevice:
      record.ragEmbeddingDevice === "gpu" || record.ragEmbeddingDevice === "auto"
        ? record.ragEmbeddingDevice
        : "cpu",
    ragMaxHits:
      typeof record.ragMaxHits === "number" && Number.isInteger(record.ragMaxHits) && record.ragMaxHits > 0
        ? record.ragMaxHits
        : 5,
    ragRerankEnabled:
      typeof record.ragRerankEnabled === "boolean" ? record.ragRerankEnabled : true,
    webSearchEnabled:
      typeof record.webSearchEnabled === "boolean" ? record.webSearchEnabled : false,
    llmProvider: record.llmProvider === "openai_compatible" ? record.llmProvider : "openai_compatible",
    openaiBaseUrl:
      typeof record.openaiBaseUrl === "string" && record.openaiBaseUrl.trim()
        ? record.openaiBaseUrl.trim()
        : "http://127.0.0.1:8317/v1",
    openaiModel:
      typeof record.openaiModel === "string" && record.openaiModel.trim()
        ? record.openaiModel.trim()
        : "gpt-5.4",
    hfEndpoint:
      typeof record.hfEndpoint === "string" && record.hfEndpoint.trim()
        ? record.hfEndpoint.trim()
        : "https://hf-mirror.com",
    openaiApiKey: typeof record.openaiApiKey === "string" ? record.openaiApiKey : "",
    hasOpenaiApiKey: typeof record.hasOpenaiApiKey === "boolean" ? record.hasOpenaiApiKey : false,
    openaiApiKeyMasked: typeof record.openaiApiKeyMasked === "string" ? record.openaiApiKeyMasked : "",
    windowTokens:
      typeof record.windowTokens === "number" && Number.isInteger(record.windowTokens) && record.windowTokens > 0
        ? record.windowTokens
        : 1000000,
    answerDetailLevel:
      record.answerDetailLevel === "short" || record.answerDetailLevel === "long"
        ? record.answerDetailLevel
        : "medium",
    videoGenerationConcurrency:
      typeof record.videoGenerationConcurrency === "number"
        && Number.isInteger(record.videoGenerationConcurrency)
        && record.videoGenerationConcurrency > 0
        ? record.videoGenerationConcurrency
        : 1,
  };
}
