import { useEffect, useMemo, useReducer } from "react";

import {
  cancelFasterWhisperModelDownload,
  createVideoNote,
  deleteVideoNote,
  downloadFasterWhisperModel,
  generateVideoKnowledgeCards,
  generateVideoMindmap,
  generateVideoSummary,
  getVideoPreviewUrl,
  loadFasterWhisperModels,
  loadProviderSettings,
  loadVideoKnowledgeCards,
  sendAgentChat,
  loadVideoMindmap,
  loadVideoNotes,
  loadVideoSummary,
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
  createInitialWorkspaceState,
  createMindmapLoadedState,
  createSummaryLoadedState,
  createWorkspaceLoadedState,
  findSeriesById,
  findVideoById,
  getChatMessagesForScope,
  markVideoAsReady,
  normalizeUiSettings,
  resetUiSettings,
  buildChatScopeKey,
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
        notesLoading: false,
        savingNote: false,
        generatingVideoKey: null,
        generatingMindmapKey: null,
        generationProgress: null,
        generationSnapshot: null,
        downloadingModelId: null,
        modelDownloadProgress: null,
        error: action.message,
        fasterWhisperModelsLoading: false,
      };
    case "series_selected": {
      const chatScopeKey = buildChatScopeKey("series", action.seriesId, null, "series-home");
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
        notes: null,
        selectedChapterId: null,
        selectedNodeId: null,
        previewSeekRequest: null,
        generationProgress: null,
        generationSnapshot: null,
        chatMessages: getChatMessagesForScope(state.chatThreads, chatScopeKey),
        chatPending: false,
      };
    }
    case "library_home_entered": {
      const chatScopeKey = buildChatScopeKey("library", null, null, "studio");
      return {
        ...state,
        tools: null,
        selectedSeriesId: null,
        selectedVideoId: null,
        selectedContextType: "library",
        selectedToolId: "studio",
        summary: null,
        mindmap: null,
        knowledgeCards: null,
        notes: null,
        selectedChapterId: null,
        selectedNodeId: null,
        previewSeekRequest: null,
        toolsLoading: false,
        summaryLoading: false,
        mindmapLoading: false,
        generationProgress: null,
        generationSnapshot: null,
        chatMessages: getChatMessagesForScope(state.chatThreads, chatScopeKey),
        chatPending: false,
      };
    }
    case "video_selected": {
      const chatScopeKey = buildChatScopeKey("video", action.seriesId, action.videoId, "studio");
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
        notes: null,
        selectedChapterId: null,
        selectedNodeId: null,
        previewSeekRequest: null,
        generationProgress: null,
        generationSnapshot: null,
        chatMessages: getChatMessagesForScope(state.chatThreads, chatScopeKey),
        chatPending: false,
      };
    }
    case "tool_selected":
      return {
        ...state,
        selectedToolId: action.toolId,
        error: "",
      };
    case "series_context_selected": {
      const chatScopeKey = buildChatScopeKey("series", state.selectedSeriesId, null, "series-home");
      return {
        ...state,
        selectedContextType: "series",
        selectedVideoId: null,
        selectedToolId: "series-home",
        tools: null,
        summary: null,
        mindmap: null,
        knowledgeCards: null,
        notes: null,
        selectedChapterId: null,
        selectedNodeId: null,
        previewSeekRequest: null,
        generationProgress: null,
        generationSnapshot: null,
        chatMessages: getChatMessagesForScope(state.chatThreads, chatScopeKey),
        chatPending: false,
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
        error: "",
      };
    case "knowledge_cards_loaded":
      return {
        ...state,
        knowledgeCards: action.cards,
        knowledgeCardsLoading: false,
      };
    case "knowledge_cards_cleared":
      return {
        ...state,
        knowledgeCards: null,
        knowledgeCardsLoading: false,
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
      return applyChatThreadUpdate(state, [
        ...state.chatMessages,
        {
          id: action.userMessageId,
          role: "user",
          content: action.message,
          meta: "You • Just now",
        },
      ], true);
    case "chat_response_received":
      return applyChatThreadUpdate(state, [
        ...state.chatMessages,
        {
          id: action.assistantMessageId,
          role: "assistant",
          content: action.message,
          meta: action.meta ?? "Notebook Assistant • Just now",
        },
      ], false);
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
    default:
      return state;
  }
}

function applyChatThreadUpdate(state, nextMessages, chatPending) {
  const chatScopeKey = buildChatScopeKey(
    state.selectedContextType,
    state.selectedSeriesId,
    state.selectedVideoId,
    state.selectedToolId,
  );
  return {
    ...state,
    chatPending,
    chatMessages: nextMessages,
    chatThreads: setChatMessagesForScope(state.chatThreads, chatScopeKey, nextMessages),
    error: "",
  };
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
    dispatch({ type: "library_home_entered" });
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

    dispatch({ type: "knowledge_cards_loading_started" });
    try {
      const cards = await generateVideoKnowledgeCards(state.selectedSeriesId, state.selectedVideoId);
      dispatch({ type: "knowledge_cards_loaded", cards });
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
        dispatch({ type: "workspace_settings_loaded", settings: { ...state.ui, ...savedProviderSettings } });
      } else {
        const savedSettings = await updateWorkspaceSettings(nextUi);
        dispatch({ type: "workspace_settings_loaded", settings: savedSettings });
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
    const nextUi = resetUiSettings();
    dispatch({ type: "workspace_settings_loaded", settings: nextUi });

    try {
      const savedSettings = await updateWorkspaceSettings(nextUi);
      dispatch({ type: "workspace_settings_loaded", settings: savedSettings });
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
        transcriptEnhancementEnabled: state.ui.aiTranscriptEnhancement,
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

    const sessionId = buildAgentSessionId(
      state.selectedContextType,
      state.selectedSeriesId,
      state.selectedVideoId,
      state.selectedToolId,
    );

    dispatch({
      type: "chat_request_started",
      userMessageId: `user-${Date.now()}`,
      message: trimmedMessage,
    });

    try {
      const response = await sendAgentChat(sessionId, trimmedMessage, {
        scope_type: state.selectedContextType,
        series_id: activeSeries?.id ?? null,
        series_title: activeSeries?.title ?? null,
        video_id: selectedVideo?.id ?? null,
        video_title: selectedVideo?.title ?? null,
        selected_tool: state.selectedToolId ?? null,
      });
      await applyAgentToolResults(response.tool_results ?? []);
      dispatch({
        type: "chat_response_received",
        assistantMessageId: `assistant-${Date.now()}`,
        message: response.assistant_message,
        meta: response.reason ? `Notebook Assistant • ${response.reason}` : "Notebook Assistant • Just now",
      });
    } catch (error) {
      dispatch({ type: "chat_pending_cleared" });
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "AI 对话失败",
      });
    }
  }

  async function applyAgentToolResults(toolResults) {
    for (const result of toolResults) {
      const payload = result?.payload ?? {};
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
    notes: state.notes,
    activeSeries,
    selectedVideo,
    selectedNode,
    previewUrl,
    previewSeekRequest: state.previewSeekRequest,
    chatMessages: state.chatMessages,
    chatPending: state.chatPending,
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

function buildAgentSessionId(selectedContextType, seriesId, videoId, selectedToolId) {
  return buildChatScopeKey(selectedContextType, seriesId, videoId, selectedToolId);
}

function normalizeAgentToolId(toolId) {
  if (toolId === "video") {
    return "preview";
  }
  if (
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
